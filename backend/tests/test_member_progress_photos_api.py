from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
import struct
from uuid import uuid4
import zlib

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.main import app, get_session
from app.modules.memberships.models import Member, MemberConsent, Membership, Plan
from app.modules.portal.routines import PROGRESS_PHOTO_CONSENT_TYPE, PROGRESS_PHOTO_CONSENT_VERSION
from app.modules.routines import record_progress_photo
from app.modules.routines.photo_storage import MAX_PROGRESS_PHOTO_BYTES


def _png_bytes() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    pixels = zlib.compress(b"\x00\x20\x40\x60")
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", pixels)
        + chunk(b"IEND", b"")
    )


def _build_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _: object) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _seed_member(session: Session, *, email: str, first_name: str = "Ana"):
    now = datetime.now(timezone.utc)
    member = Member(first_name=first_name, last_name="Demo", email=email, status="active")
    session.add(member)
    session.flush()
    plan = Plan(
        code=f"PLAN-{uuid4().hex[:8].upper()}",
        name="Mensual",
        duration_days=30,
        price_cents=50000,
    )
    session.add(plan)
    session.flush()
    session.add(
        Membership(
            member_id=member.id,
            plan_id=plan.id,
            status="active",
            starts_at=now - timedelta(days=5),
            ends_at=now + timedelta(days=25),
        )
    )
    session.commit()
    return member.id


def _member_headers(client: TestClient, email: str) -> dict[str, str]:
    requested = client.post("/member/auth/request-code", json={"email": email})
    assert requested.status_code == 202, requested.text
    code = requested.json()["preview_code"]
    assert code is not None
    verified = client.post("/member/auth/verify", json={"email": email, "code": code})
    assert verified.status_code == 200, verified.text
    return {"Authorization": f"Bearer {verified.json()['access_token']}"}


def test_member_progress_photos_require_consent_and_stay_private(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROGRESS_PHOTOS_DIR", str(tmp_path / "progress_photos"))
    monkeypatch.setenv("SECRET_KEY", "test-member-photos-secret")
    monkeypatch.setenv("PREVIEW_MODE", "true")
    directory = tmp_path / "progress_photos"
    png = _png_bytes()

    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ana_id = _seed_member(session, email="ana.photos@example.com")
        _seed_member(session, email="beto.photos@example.com", first_name="Beto")

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            ana = _member_headers(client, "ana.photos@example.com")
            beto = _member_headers(client, "beto.photos@example.com")
            photos_url = "/member/progress/photos"

            def upload(
                headers,
                *,
                angle="front",
                content=png,
                content_type="image/png",
                **fields,
            ):
                return client.post(
                    photos_url,
                    headers=headers,
                    data={"angle": angle, **fields},
                    files={"photo": ("progreso.png", content, content_type)},
                )

            # The member routes only accept a member session.
            assert client.get(photos_url).status_code == 401
            assert upload({}).status_code == 401

            listed = client.get(photos_url, headers=ana)
            assert listed.status_code == 200, listed.text
            assert listed.json() == {"items": [], "consent_recorded": False}

            # Consent is a precondition: nothing is written without it.
            assert upload(ana).status_code == 422
            assert not directory.exists()
            assert client.get(photos_url, headers=ana).json()["consent_recorded"] is False

            # A rejected image does not leave a consent behind either.
            assert upload(
                ana, content=b"not really an image", consent="true"
            ).status_code == 422
            assert client.get(photos_url, headers=ana).json()["consent_recorded"] is False
            assert upload(
                ana, content_type="image/gif", consent="true"
            ).status_code == 422
            assert upload(ana, angle="top", consent="true").status_code == 422
            oversized = b"\x89PNG\r\n\x1a\n" + b"0" * (MAX_PROGRESS_PHOTO_BYTES - 7)
            assert upload(ana, content=oversized, consent="true").status_code == 413
            assert not directory.exists()

            # The first accepted upload records the consent and the origin.
            created = upload(
                ana,
                captured_at="2026-10-20T15:30:00+00:00",
                notes="  Primera foto  ",
                consent="true",
            )
            assert created.status_code == 201, created.text
            photo = created.json()
            assert photo["member_id"] == str(ana_id)
            assert photo["angle"] == "front"
            assert photo["notes"] == "Primera foto"
            assert photo["content_type"] == "image/png"
            assert photo["byte_size"] == len(png)
            assert photo["origin"] == "app"
            assert photo["captured_at"].startswith("2026-10-20T15:30:00")
            assert len(list(directory.iterdir())) == 1

            # The consent is stored once, with its own document version.
            assert client.get(photos_url, headers=ana).json()["consent_recorded"] is True
            with Session(engine) as session:
                consents = session.exec(
                    select(MemberConsent).where(
                        MemberConsent.member_id == ana_id,
                        MemberConsent.consent_type == PROGRESS_PHOTO_CONSENT_TYPE,
                    )
                ).all()
            assert len(consents) == 1
            assert consents[0].document_version == PROGRESS_PHOTO_CONSENT_VERSION
            assert consents[0].revoked_at is None

            # Once consented, a later upload does not ask for it again.
            second = upload(ana, angle="side", notes="Otra")
            assert second.status_code == 201, second.text
            with Session(engine) as session:
                assert (
                    len(
                        session.exec(
                            select(MemberConsent).where(
                                MemberConsent.member_id == ana_id,
                                MemberConsent.consent_type == PROGRESS_PHOTO_CONSENT_TYPE,
                            )
                        ).all()
                    )
                    == 1
                )

            # A staff photo of the same member is visible and still marked staff.
            with Session(engine) as staff_session:
                staff_photo = record_progress_photo(
                    staff_session,
                    ana_id,
                    data=png,
                    content_type="image/png",
                    angle="back",
                    notes="En recepción",
                )
            assert staff_photo.origin == "staff"

            listed = client.get(photos_url, headers=ana).json()
            assert [item["id"] for item in listed["items"]] == [
                staff_photo.id.__str__(),
                second.json()["id"],
                photo["id"],
            ]
            assert listed["items"][0]["origin"] == "staff"

            # Another member sees neither the photos nor their files.
            assert client.get(photos_url, headers=beto).json() == {
                "items": [],
                "consent_recorded": False,
            }
            for photo_id in (photo["id"], second.json()["id"], str(staff_photo.id)):
                assert client.delete(
                    f"/member/progress/photos/{photo_id}", headers=beto
                ).status_code == 404

            # The file is served through a signed link, like invoice downloads.
            assert client.get(photo["file_path"]).status_code == 200
            assert client.get(
                f"/member/progress/photos/{photo['id']}/file"
            ).status_code == 422
            assert client.get(
                f"/member/progress/photos/{photo['id']}/file?exp=0&sig={'0' * 64}"
            ).status_code == 403
            assert client.get(
                f"/member/progress/photos/{photo['id']}/file"
                f"?exp={photo['file_path'].split('exp=')[1].split('&')[0]}&sig={'0' * 64}"
            ).status_code == 403
            assert client.get(
                photo["file_path"].replace(photo["id"], str(uuid4()))
            ).status_code == 403

            # The owner downloads the bytes with the same safe headers.
            downloaded = client.get(photo["file_path"])
            assert downloaded.status_code == 200
            assert downloaded.content == png
            assert downloaded.headers["content-type"] == "image/png"
            assert downloaded.headers["cache-control"] == "private, no-store"
            assert downloaded.headers["x-content-type-options"] == "nosniff"
            assert "foto-progreso-2026-10-20-front.png" in downloaded.headers[
                "content-disposition"
            ]

            # Deleting removes the row and the file; a second delete is a 404.
            assert client.delete(
                f"/member/progress/photos/{photo['id']}", headers=ana
            ).status_code == 204
            assert client.delete(
                f"/member/progress/photos/{photo['id']}", headers=ana
            ).status_code == 404
            assert client.get(photo["file_path"]).status_code == 404
            assert len(list(directory.iterdir())) == 2
            assert [item["id"] for item in client.get(photos_url, headers=ana).json()["items"]] == [
                str(staff_photo.id),
                second.json()["id"],
            ]

            # The member can also delete a photo the staff uploaded.
            assert client.delete(
                f"/member/progress/photos/{staff_photo.id}", headers=ana
            ).status_code == 204
            assert len(list(directory.iterdir())) == 1
    finally:
        app.dependency_overrides.clear()
