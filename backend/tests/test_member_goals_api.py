from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.main import app, get_session
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.memberships.models import Member
from app.modules.routines import record_measurement
from app.timezone import club_date


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
    member = Member(first_name=first_name, last_name="Demo", email=email, status="active")
    session.add(member)
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


def test_member_manages_own_goals(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-member-goals-secret")
    monkeypatch.setenv("PREVIEW_MODE", "true")

    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    today = club_date(datetime.now(timezone.utc))
    with Session(engine) as session:
        ensure_default_access_control(session)
        register_user(
            session,
            email="owner@example.com",
            password="owner-strong-password",
            role_codes=("owner",),
        )
        ana_id = _seed_member(session, email="ana@example.com")
        _seed_member(session, email="beto@example.com", first_name="Beto")
        record_measurement(session, ana_id, weight_kg=70)

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            ana_headers = _member_headers(client, "ana@example.com")
            beto_headers = _member_headers(client, "beto@example.com")

            owner_login = client.post(
                "/auth/login",
                json={"email": "owner@example.com", "password": "owner-strong-password"},
            )
            assert owner_login.status_code == 200
            staff_headers = {"Authorization": f"Bearer {owner_login.json()['access_token']}"}

            goals_url = "/member/progress/goals"

            # The member creates a goal; the baseline is the last measurement.
            created = client.post(
                goals_url,
                headers=ana_headers,
                json={
                    "metric": "weight_kg",
                    "direction": "decrease",
                    "target_value": 65,
                    "target_date": (today + timedelta(days=30)).isoformat(),
                    "notes": "  Meta de otoño  ",
                },
            )
            assert created.status_code == 201, created.text
            goal = created.json()
            assert goal["origin"] == "app"
            assert goal["status"] == "active"
            assert goal["baseline_value"] == 70
            assert goal["current_value"] == 70
            assert goal["progress_percent"] == 0
            assert goal["notes"] == "Meta de otoño"

            # One active goal per metric; invalid targets and dates are rejected.
            duplicate = client.post(
                goals_url,
                headers=ana_headers,
                json={"metric": "weight_kg", "direction": "decrease", "target_value": 64},
            )
            assert duplicate.status_code == 409
            past_date = client.post(
                goals_url,
                headers=ana_headers,
                json={
                    "metric": "waist_cm",
                    "direction": "decrease",
                    "target_value": 80,
                    "target_date": (today - timedelta(days=1)).isoformat(),
                },
            )
            assert past_date.status_code == 422
            invalid_fat = client.post(
                goals_url,
                headers=ana_headers,
                json={"metric": "body_fat_percent", "direction": "decrease", "target_value": 120},
            )
            assert invalid_fat.status_code == 422
            unknown_metric = client.post(
                goals_url,
                headers=ana_headers,
                json={"metric": "height_cm", "direction": "decrease", "target_value": 170},
            )
            assert unknown_metric.status_code == 422

            # The staff token cannot use member routes.
            assert client.post(
                goals_url,
                headers=staff_headers,
                json={"metric": "waist_cm", "direction": "decrease", "target_value": 80},
            ).status_code == 401

            # A goal created in the panel is not the member's to cancel.
            staff_goal = client.post(
                f"/admin/routines/members/{ana_id}/goals",
                headers=staff_headers,
                json={"metric": "waist_cm", "direction": "decrease", "target_value": 80},
            )
            assert staff_goal.status_code == 201, staff_goal.text
            assert staff_goal.json()["origin"] == "staff"
            assert client.post(
                f"/member/progress/goals/{staff_goal.json()['id']}/cancel",
                headers=ana_headers,
            ).status_code == 409

            # A foreign goal is invisible to the member.
            assert client.post(
                f"/member/progress/goals/{goal['id']}/cancel",
                headers=beto_headers,
            ).status_code == 404

            # Progress is computed against the frozen baseline.
            measured = client.post(
                "/member/progress/measurements",
                headers=ana_headers,
                json={"weight_kg": 69.5},
            )
            assert measured.status_code == 201, measured.text
            progress = client.get("/member/progress", headers=ana_headers).json()
            listed = next(item for item in progress["goals"] if item["id"] == goal["id"])
            assert listed["origin"] == "app"
            assert listed["current_value"] == 69.5
            assert listed["progress_percent"] == 10

            # Cancelling frees the metric; a closed goal cannot be cancelled again.
            cancelled = client.post(
                f"/member/progress/goals/{goal['id']}/cancel",
                headers=ana_headers,
            )
            assert cancelled.status_code == 200, cancelled.text
            assert cancelled.json()["status"] == "cancelled"
            assert cancelled.json()["cancelled_at"] is not None
            assert client.post(
                f"/member/progress/goals/{goal['id']}/cancel",
                headers=ana_headers,
            ).status_code == 409

            # With the metric free, a target the latest measurement already
            # meets is rejected.
            already_met = client.post(
                goals_url,
                headers=ana_headers,
                json={"metric": "weight_kg", "direction": "decrease", "target_value": 70},
            )
            assert already_met.status_code == 422

            replacement = client.post(
                goals_url,
                headers=ana_headers,
                json={"metric": "weight_kg", "direction": "decrease", "target_value": 64},
            )
            assert replacement.status_code == 201, replacement.text
            assert replacement.json()["baseline_value"] == 69.5

            # Reaching the target closes the goal automatically.
            client.post("/member/progress/measurements", headers=ana_headers, json={"weight_kg": 63.5})
            progress = client.get("/member/progress", headers=ana_headers).json()
            achieved = next(
                item for item in progress["goals"] if item["id"] == replacement.json()["id"]
            )
            assert achieved["status"] == "achieved"
            assert achieved["achieved_value"] == 63.5
            assert achieved["progress_percent"] == 100

            # The panel sees both channels on the same goal history.
            staff_goals = client.get(
                f"/admin/routines/members/{ana_id}/goals",
                headers=staff_headers,
            ).json()
            by_id = {item["id"]: item for item in staff_goals}
            assert by_id[goal["id"]]["origin"] == "app"
            assert by_id[replacement.json()["id"]]["origin"] == "app"
            assert by_id[staff_goal.json()["id"]]["origin"] == "staff"
    finally:
        app.dependency_overrides.clear()
