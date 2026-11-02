"""El techo de capacidad y de ventana de cancelación también está en la base.

Hasta `20261101_0082` el esquema solo acotaba por debajo (`capacity > 0`,
`cancel_window_hours >= 0`): el `500` y el `168` vivían únicamente en los modelos
de petición, escritos tres veces y dos veces, y ninguna en el servicio. Un
llamador que no pasara por la petición —el seed, un script, un CLI futuro— podía
guardar una sala de dos mil personas o una ventana de un año sin que nadie
protestara, y las capas podían separar su número sin que ninguna prueba lo notara.

Las cuatro pruebas recorren la frontera **por los dos lados** (500 entra, 501 no)
en las tres capas que hoy la conocen: la petición HTTP, que responde `422` sin
llegar al servicio; el servicio, que responde `InvalidClassData` y no escribe
nada; y la base, que rechaza con `IntegrityError` al que usa el ORM sin pasar por
las dos anteriores. La última comprueba que el valor por defecto de la columna
tampoco es una copia suelta del número del modelo.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.main import app, get_session
from app.modules.classes import (
    InvalidClassData,
    create_class_room,
    create_class_session,
    update_class_session,
)
from app.modules.classes.models import (
    DEFAULT_CANCEL_WINDOW_HOURS,
    MAX_CANCEL_WINDOW_HOURS,
    MAX_CLASS_CAPACITY,
    ClassRoom,
    ClassSession,
    ClassType,
)
from app.modules.identity.service import ensure_default_access_control, register_user

FUTURE = datetime(2030, 1, 15, 18, 0, tzinfo=timezone.utc)


def _engine_with_schema():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _manager_client(engine) -> tuple[TestClient, dict[str, str]]:
    def dependency() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = dependency
    client = TestClient(app)
    with Session(engine) as session:
        ensure_default_access_control(session)
        register_user(
            session,
            email="manager@example.com",
            password="manager-strong-password",
            role_codes=("manager",),
        )
    login = client.post(
        "/auth/login",
        json={"email": "manager@example.com", "password": "manager-strong-password"},
    )
    assert login.status_code == 200, login.text
    return client, {"Authorization": f"Bearer {login.json()['access_token']}"}


def _class_type(session: Session) -> ClassType:
    class_type = ClassType(name=f"Funcional {uuid4().hex[:6]}")
    session.add(class_type)
    session.commit()
    session.refresh(class_type)
    return class_type


def _session_row(class_type_id, *, title: str, **values) -> ClassSession:
    return ClassSession(
        title=title,
        class_type_id=class_type_id,
        starts_at=FUTURE,
        ends_at=FUTURE + timedelta(hours=1),
        **values,
    )


def _count(session: Session, model) -> int:
    return session.exec(select(func.count()).select_from(model)).one()[0]


def test_the_panel_rejects_a_capacity_above_its_own_ceiling() -> None:
    """La petición rechaza el mismo número que la base: 500 entra, 501 no."""
    engine = _engine_with_schema()
    try:
        client, headers = _manager_client(engine)

        at_ceiling = client.post(
            "/admin/classes/rooms",
            headers=headers,
            json={"name": "Salón grande", "capacity": MAX_CLASS_CAPACITY},
        )
        assert at_ceiling.status_code == 201, at_ceiling.text
        over_ceiling = client.post(
            "/admin/classes/rooms",
            headers=headers,
            json={"name": "Galpón", "capacity": MAX_CLASS_CAPACITY + 1},
        )
        assert over_ceiling.status_code == 422, over_ceiling.text
        assert over_ceiling.json()["detail"][0]["loc"] == ["body", "capacity"]

        created = client.post("/admin/classes/types", headers=headers, json={"name": "Spinning"})
        assert created.status_code == 201, created.text
        payload = {
            "title": "Spinning 6am",
            "class_type_id": created.json()["id"],
            "starts_at": FUTURE.isoformat(),
            "ends_at": (FUTURE + timedelta(hours=1)).isoformat(),
            "capacity": MAX_CLASS_CAPACITY + 1,
            "cancel_window_hours": MAX_CANCEL_WINDOW_HOURS,
        }
        refused = client.post("/admin/classes/sessions", headers=headers, json=payload)
        assert refused.status_code == 422, refused.text

        payload["capacity"] = MAX_CLASS_CAPACITY
        accepted = client.post("/admin/classes/sessions", headers=headers, json=payload)
        assert accepted.status_code == 201, accepted.text
        session_id = accepted.json()["id"]

        moved = client.patch(
            f"/admin/classes/sessions/{session_id}",
            headers=headers,
            json={"capacity": MAX_CLASS_CAPACITY + 1},
        )
        assert moved.status_code == 422, moved.text
        long_window = client.patch(
            f"/admin/classes/sessions/{session_id}",
            headers=headers,
            json={"cancel_window_hours": MAX_CANCEL_WINDOW_HOURS + 1},
        )
        assert long_window.status_code == 422, long_window.text

        untouched = client.get("/admin/classes/sessions", headers=headers).json()["items"][0]
        assert untouched["capacity"] == MAX_CLASS_CAPACITY
        assert untouched["cancel_window_hours"] == MAX_CANCEL_WINDOW_HOURS
        with Session(engine) as session:
            assert _count(session, ClassRoom) == 1
    finally:
        app.dependency_overrides.clear()


def test_the_service_refuses_the_same_numbers_and_writes_nothing() -> None:
    """Quien llama al servicio sin pasar por la petición recibe el motivo, no un 500."""
    engine = _engine_with_schema()
    with Session(engine) as session:
        class_type = _class_type(session)

        with pytest.raises(InvalidClassData, match="no puede superar"):
            create_class_room(session, name="Galpón", capacity=MAX_CLASS_CAPACITY + 1)
        session.rollback()
        assert _count(session, ClassRoom) == 0
        with pytest.raises(InvalidClassData, match="capacidad de la clase"):
            create_class_session(
                session,
                title="Sesión enorme",
                class_type_id=class_type.id,
                starts_at=FUTURE,
                ends_at=FUTURE + timedelta(hours=1),
                capacity=MAX_CLASS_CAPACITY + 1,
            )
        session.rollback()

        with pytest.raises(InvalidClassData, match="ventana de cancelación"):
            create_class_session(
                session,
                title="Sesión sin plazo",
                class_type_id=class_type.id,
                starts_at=FUTURE,
                ends_at=FUTURE + timedelta(hours=1),
                capacity=10,
                cancel_window_hours=MAX_CANCEL_WINDOW_HOURS + 1,
            )
        session.rollback()
        assert _count(session, ClassSession) == 0

        room = create_class_room(session, name="Salón A", capacity=MAX_CLASS_CAPACITY)
        live = create_class_session(
            session,
            title="Spinning 6am",
            class_type_id=class_type.id,
            starts_at=FUTURE,
            ends_at=FUTURE + timedelta(hours=1),
            capacity=MAX_CLASS_CAPACITY,
            cancel_window_hours=MAX_CANCEL_WINDOW_HOURS,
        )
        assert room.capacity == MAX_CLASS_CAPACITY
        assert live.cancel_window_hours == MAX_CANCEL_WINDOW_HOURS

        with pytest.raises(InvalidClassData, match="capacidad de la clase"):
            update_class_session(session, live.id, capacity=MAX_CLASS_CAPACITY + 1)
        with pytest.raises(InvalidClassData, match="ventana de cancelación"):
            update_class_session(
                session, live.id, cancel_window_hours=MAX_CANCEL_WINDOW_HOURS + 1
            )
        session.rollback()
        refreshed = session.get(ClassSession, live.id)
        assert refreshed is not None
        assert refreshed.capacity == MAX_CLASS_CAPACITY
        assert refreshed.cancel_window_hours == MAX_CANCEL_WINDOW_HOURS


def test_a_direct_writer_is_stopped_by_the_schema() -> None:
    """Sin servicio de por medio, el `CHECK` es la última guarda que queda."""
    engine = _engine_with_schema()
    with Session(engine) as session:
        class_type = _class_type(session)

        session.add(ClassRoom(name="Galpón", capacity=MAX_CLASS_CAPACITY + 1))
        with pytest.raises(IntegrityError, match="ck_class_rooms_capacity_max"):
            session.commit()
        session.rollback()
        assert (
            session.exec(
                select(func.count()).select_from(ClassRoom).where(ClassRoom.name == "Galpón")
            ).one()[0]
            == 0
        )

        session.add(
            _session_row(
                class_type.id, title="Sesión enorme", capacity=MAX_CLASS_CAPACITY + 1
            )
        )
        with pytest.raises(IntegrityError, match="ck_class_sessions_capacity_max"):
            session.commit()
        session.rollback()

        session.add(
            _session_row(
                class_type.id,
                title="Sesión sin plazo",
                capacity=10,
                cancel_window_hours=MAX_CANCEL_WINDOW_HOURS + 1,
            )
        )
        with pytest.raises(IntegrityError, match="ck_class_sessions_window_max"):
            session.commit()
        session.rollback()
        assert _count(session, ClassSession) == 0

        session.add(
            _session_row(
                class_type.id,
                title="Sesión al tope",
                capacity=MAX_CLASS_CAPACITY,
                cancel_window_hours=MAX_CANCEL_WINDOW_HOURS,
            )
        )
        session.commit()


def test_the_column_default_is_the_models_default() -> None:
    """Un `INSERT` que no nombre la columna recibe el mismo 4 que el modelo de Python."""
    server_default = ClassSession.__table__.c.cancel_window_hours.server_default
    assert str(server_default.arg.text) == str(DEFAULT_CANCEL_WINDOW_HOURS)
