from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.main import app, get_session
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.maintenance.service import create_equipment, set_equipment_status


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


def _login_staff(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_device(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post("/admin/kiosk/devices", headers=headers, json={"label": "Recepción"})
    assert response.status_code == 201, response.text
    return response.json()


def test_kiosk_equipment_notices_list_only_unavailable(monkeypatch) -> None:
    monkeypatch.setenv("PREVIEW_MODE", "true")
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ensure_default_access_control(session)
        register_user(
            session,
            email="owner@example.com",
            password="owner-strong-password",
            role_codes=("owner",),
        )
        treadmill = create_equipment(
            session, name="Caminadora", category="Cardio", location="Área cardio"
        )
        bike = create_equipment(
            session,
            name="Bicicleta fija",
            category="Cardio",
            location="Área cardio",
        )
        press = create_equipment(session, name="Prensa", category="Fuerza")
        set_equipment_status(session, bike.id, status="maintenance")
        set_equipment_status(session, press.id, status="out_of_service")
        treadmill_id = treadmill.id

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            owner = _login_staff(client, "owner@example.com", "owner-strong-password")
            device = _create_device(client, owner)
            kiosk_headers = {"X-Kiosk-Token": device["token"]}

            assert client.get("/kiosk/equipment").status_code == 401
            assert client.get(
                "/kiosk/equipment", headers={"X-Kiosk-Token": "not-a-token"}
            ).status_code == 401

            response = client.get("/kiosk/equipment", headers=kiosk_headers)
            assert response.status_code == 200, response.text
            items = response.json()["items"]
            assert [item["name"] for item in items] == ["Prensa", "Bicicleta fija"]
            assert items[0] == {
                "name": "Prensa",
                "location": None,
                "status": "out_of_service",
                "status_label": "Fuera de servicio",
            }
            assert items[1]["status"] == "maintenance"
            assert items[1]["status_label"] == "En mantenimiento"
            assert items[1]["location"] == "Área cardio"
            assert all(item["name"] != "Caminadora" for item in items)

            with Session(engine) as session:
                set_equipment_status(session, treadmill_id, status="inspection")

            assert client.get("/kiosk/equipment", headers=kiosk_headers).json()["items"][
                0
            ]["name"] == "Prensa"

            assert client.post(
                f"/admin/kiosk/devices/{device['id']}/revoke", headers=owner
            ).status_code == 200
            assert client.get("/kiosk/equipment", headers=kiosk_headers).status_code == 401
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()
