"""Custodia de los catálogos que comparten modelo, servicio y base de datos.

Cada vocabulario que estaba escrito a la vez en dos o tres sitios —las formas de
pago del mostrador, los métodos con que se recibe un pago de cuenta, los estados
del equipo, los estados de una línea de estado de cuenta, los tipos de su
bitácora y los nombres de los reportes programados— es un modo de que la
validación del servicio y el ``CHECK`` de la base discrepen —el servicio acepta
un valor que el esquema rechaza, o al revés— sin que ninguna prueba lo note
hasta que alguien lo usa.

Hoy el ``CHECK`` se renderiza desde la misma tupla que valida el servicio
(``app.constraints.sql_in_list``), así que la lista vive una sola vez. Esta
custodia fija cuatro cosas: que el SQL que produce el modelo siga siendo
**byte a byte** el que ya está aplicado en la base —cambiar una tupla cambia el
``CHECK`` y exige una migración, no puede hacerse de pasada—, que el valor de
más o de menos en cada vocabulario siga siendo el documentado, que las etiquetas
y las ramas que consumen esa lista la cubran exactamente, y que la lista que
ofrece el panel —el ``Literal`` de la petición, visible en el contrato
OpenAPI— sea esa misma tupla y no una copia más.

Junto a las listas están las dos cotas numéricas de las clases: la capacidad y
las horas de ventana de cancelación estaban escritas tres veces como ``le=`` en
los modelos de petición y ninguna vez en la base, que solo acotaba por debajo.
Salen ahora del mismo ``MAX_CLASS_CAPACITY`` y ``MAX_CANCEL_WINDOW_HOURS`` del
modelo, el ``CHECK`` que renderizan es el que aplicó ``20261101_0082`` y el
contrato OpenAPI es la prueba de que el panel ofrece esa misma cota.

El índice parcial de reservas vivas (``uq_class_reservations_active``) es el mismo
problema con un predicado en lugar de un ``CHECK``: la lista estaba escrita a mano
dos veces —una por dialecto— y la migración ``20261017_0009`` aplicó solo la de
PostgreSQL, así que la de SQLite podía quedarse con otra lista sin que nada lo
notara. Sale ahora de ``ACTIVE_RESERVATION_STATUSES``, la tupla con la que el
servicio y el portal cuentan las plazas ocupadas; el SQL compilado es idéntico al
aplicado en los dos dialectos, así que no hizo falta migración.
``APPLIED_INDEX_PREDICATES`` fija el texto de ambos y una prueba de comportamiento
comprueba que los tres estados vivos chocan en la base mientras que ``cancelled``
y ``no_show`` dejan volver a reservar.
"""

from __future__ import annotations

import inspect
import re

import pytest
from sqlalchemy import CheckConstraint
from sqlmodel import SQLModel

from app.constraints import sql_in_list
from app.main import app
from app.modules.classes import models as classes_models
from app.modules.classes import service as classes_service
from app.modules.finance import models as finance_models
from app.modules.finance import service as finance_service
from app.modules.inventory import models as inventory_models
from app.modules.inventory import service as inventory_service
from app.modules.maintenance import models as maintenance_models
from app.modules.maintenance import service as maintenance_service
from app.modules.memberships import models as membership_models
from app.modules.memberships import service as membership_service
from app.modules.physio import models as physio_models
from app.modules.portal import classes as portal_classes
from app.modules.reports import models as reports_models
from app.modules.reports import scheduled as scheduled_reports
from app.modules.reports.scheduled_configuration import _REPORT_FIELDS
from app.modules.reports.service import build_report
from app.modules.routines import models as routines_models

# El SQL exacto que dejaron las migraciones: `20261017_0012` (equipo),
# `20261019_0017` (ventas y devoluciones, que reemplazaron la versión de
# `20261017_0008` y `20261018_0015`), `20261015_0001` (intentos de pago),
# `20261025_0027` (conciliación bancaria), `20261101_0079`/`20261101_0080`
# (reportes programados), `20261101_0082` (topes de clase) y
# `20261102_0083`–`20261102_0086` (topes de fisioterapia, rutinas y medidas).
APPLIED_CHECKS: dict[tuple[str, str], str] = {
    (
        "class_rooms",
        "ck_class_rooms_capacity_max",
    ): "capacity <= 500",
    (
        "class_sessions",
        "ck_class_sessions_capacity_max",
    ): "capacity <= 500",
    (
        "class_sessions",
        "ck_class_sessions_window_max",
    ): "cancel_window_hours <= 168",
    (
        "physio_services",
        "ck_physio_services_duration_max",
    ): "duration_minutes <= 480",
    (
        "physio_offers",
        "ck_physio_offers_sessions_max",
    ): "sessions <= 52",
    (
        "physio_offers",
        "ck_physio_offers_validity_max",
    ): "validity_days <= 366",
    (
        "routine_items",
        "ck_routine_items_sets_max",
    ): "sets <= 50",
    (
        "routine_items",
        "ck_routine_items_rest_max",
    ): "rest_seconds IS NULL OR rest_seconds <= 1800",
    (
        "body_measurements",
        "ck_body_measurements_weight_max",
    ): "weight_kg IS NULL OR weight_kg <= 500",
    (
        "body_measurements",
        "ck_body_measurements_waist_max",
    ): "waist_cm IS NULL OR waist_cm <= 400",
    (
        "body_measurements",
        "ck_body_measurements_chest_max",
    ): "chest_cm IS NULL OR chest_cm <= 400",
    (
        "class_sessions",
        "ck_class_sessions_status",
    ): "status IN ('scheduled', 'cancelled')",
    (
        "class_sessions",
        "ck_class_sessions_access_type",
    ): "access_type IN ('included', 'premium')",
    (
        "class_reservations",
        "ck_class_reservations_status",
    ): "status IN ('waitlist', 'reserved', 'attended', 'no_show', 'cancelled')",
    (
        "class_reservations",
        "ck_class_reservations_origin",
    ): "origin IN ('app', 'reception', 'web')",
    (
        "equipment",
        "ck_equipment_status",
    ): "status IN ('operational', 'maintenance', 'out_of_service', 'inspection', 'retired')",
    (
        "sales",
        "ck_sales_payment_method",
    ): "payment_method IN ('cash', 'card', 'transfer', 'account')",
    (
        "sale_returns",
        "ck_sale_returns_method",
    ): "refund_method IN ('cash', 'card', 'transfer', 'account')",
    (
        "member_account_payments",
        "ck_member_account_payments_method",
    ): "method IN ('cash', 'card', 'transfer')",
    (
        "payment_attempts",
        "ck_payment_attempts_method",
    ): "method IN ('card', 'spei', 'cash', 'transfer')",
    (
        "bank_accounts",
        "ck_bank_accounts_status",
    ): "status IN ('active', 'inactive')",
    (
        "bank_movements",
        "ck_bank_movements_status",
    ): "status IN ('pending', 'reconciled', 'difference', 'reviewing')",
    (
        "bank_movement_events",
        "ck_bank_movement_events_type",
    ): "event_type IN ('imported', 'matched', 'unmatched', 'flagged', 'reopened')",
    (
        "scheduled_report_deliveries",
        "ck_scheduled_report_deliveries_report_name",
    ): "report_name IN ('overview', 'revenue', 'memberships', 'operations', 'maintenance', 'inventory')",
    (
        "scheduled_report_deliveries",
        "ck_scheduled_report_deliveries_frequency",
    ): "frequency IN ('daily', 'weekly', 'monthly')",
}


# El predicado del índice parcial se aplicó en `20261017_0009` solo para
# PostgreSQL; el de SQLite lo añade el modelo para que las pruebas vean la misma
# unicidad. Se fijan los dos: si uno se queda atrás, la base de producción y la de
# pruebas dejan de rechazar lo mismo.
APPLIED_INDEX_PREDICATES: dict[tuple[str, str], str] = {
    (
        "class_reservations",
        "uq_class_reservations_active",
    ): "status IN ('waitlist', 'reserved', 'attended')",
}


def _index_predicates(table: str, name: str) -> dict[str, str]:
    indexes = [index for index in SQLModel.metadata.tables[table].indexes if index.name == name]
    assert len(indexes) == 1, f"{table} no tiene exactamente un índice llamado {name}"
    index = indexes[0]
    assert index.unique, f"{name} dejó de ser único: el predicado por sí solo no impide la segunda reserva"
    return {
        dialect: str(index.dialect_options[dialect]["where"])
        for dialect in ("postgresql", "sqlite")
    }


@pytest.mark.parametrize(("table", "name"), sorted(APPLIED_INDEX_PREDICATES))
def test_derived_index_predicate_still_matches_the_applied_sql(table: str, name: str) -> None:
    for dialect, predicate in _index_predicates(table, name).items():
        assert predicate == APPLIED_INDEX_PREDICATES[(table, name)], (
            f"El predicado de {dialect} del índice {name} cambió de texto. Se renderiza desde "
            "ACTIVE_RESERVATION_STATUSES, así que la tupla cambió: hace falta una migración "
            "para la base existente y actualizar aquí el SQL aplicado."
        )


def test_the_active_reservation_index_reads_the_tuple_the_service_counts() -> None:
    """El índice y el conteo de plazas tienen que llamar «viva» a la misma fila."""
    expected = f"status IN {sql_in_list(classes_models.ACTIVE_RESERVATION_STATUSES)}"
    for dialect, predicate in _index_predicates(
        "class_reservations", "uq_class_reservations_active"
    ).items():
        assert predicate == expected, (
            f"el predicado de {dialect} dice {predicate!r} y la tupla del servicio rinde {expected!r}."
        )


def _check_sql(table: str, name: str) -> str:
    constraints = [
        constraint
        for constraint in SQLModel.metadata.tables[table].constraints
        if isinstance(constraint, CheckConstraint) and constraint.name == name
    ]
    assert len(constraints) == 1, f"{table} no tiene exactamente un CHECK llamado {name}"
    return str(constraints[0].sqltext)


@pytest.mark.parametrize(("table", "name"), sorted(APPLIED_CHECKS))
def test_derived_check_still_matches_the_applied_sql(table: str, name: str) -> None:
    assert _check_sql(table, name) == APPLIED_CHECKS[(table, name)], (
        f"El CHECK {name} de {table} cambió de texto. El vocabulario se renderiza desde la "
        "tupla del modelo, así que esto significa que la lista cambió: hace falta una "
        "migración para la base existente, y actualizar aquí el SQL aplicado."
    )


def test_class_status_checks_are_derived_from_their_model_catalogs() -> None:
    class_checks = (
        ("class_sessions", "ck_class_sessions_status", "status", classes_models.SESSION_STATUSES),
        ("class_sessions", "ck_class_sessions_access_type", "access_type", classes_models.ACCESS_TYPES),
        (
            "class_reservations",
            "ck_class_reservations_status",
            "status",
            classes_models.RESERVATION_STATUSES,
        ),
        (
            "class_reservations",
            "ck_class_reservations_origin",
            "origin",
            classes_models.RESERVATION_ORIGINS,
        ),
    )
    for table, name, column, values in class_checks:
        assert _check_sql(table, name) == f"{column} IN {sql_in_list(values)}"


def test_the_service_uses_the_models_tuple_not_a_copy() -> None:
    """Identidad, no igualdad: una lista reescrita a mano en el servicio se detecta aquí."""
    assert maintenance_service.MANUAL_EQUIPMENT_STATUSES is maintenance_models.LIVE_EQUIPMENT_STATUSES
    assert inventory_service.PAYMENT_METHODS is inventory_models.PAYMENT_METHODS
    assert inventory_service.SALE_PAYMENT_METHODS is inventory_models.SALE_PAYMENT_METHODS
    assert (
        membership_service.MANUAL_MEMBERSHIP_PAYMENT_METHODS
        == tuple(method for method in membership_models.PAYMENT_ATTEMPT_METHODS if method != "spei")
    )
    assert (
        finance_service.FLAGGABLE_BANK_MOVEMENT_STATUSES
        is finance_models.FLAGGABLE_BANK_MOVEMENT_STATUSES
    )
    for module in (classes_service, portal_classes):
        assert module.ACTIVE_RESERVATION_STATUSES is classes_models.ACTIVE_RESERVATION_STATUSES
        assert module.SEATED_RESERVATION_STATUSES is classes_models.SEATED_RESERVATION_STATUSES


def test_the_bank_labels_cover_exactly_the_movement_statuses() -> None:
    """La bandeja traduce cada estado con `STATUS_LABELS`; una clave de más o de menos se ve aquí."""
    assert tuple(finance_service.STATUS_LABELS) == finance_models.BANK_MOVEMENT_STATUSES


def test_the_report_labels_cover_exactly_the_catalog() -> None:
    """El asunto del correo, el nombre del archivo y la frecuencia escrita salen de la misma lista."""
    assert tuple(scheduled_reports.REPORT_LABELS) == reports_models.REPORT_NAMES
    assert tuple(scheduled_reports.REPORT_FILENAME_LABELS) == reports_models.REPORT_NAMES
    assert tuple(scheduled_reports.FREQUENCY_LABELS) == reports_models.REPORT_FREQUENCIES


def test_every_report_has_its_own_recipient_column() -> None:
    """`_REPORT_FIELDS` se deriva de la tupla; si la columna no existe, el alta del destinatario revienta."""
    columns = SQLModel.metadata.tables["scheduled_report_recipients"].columns
    assert _REPORT_FIELDS == {name: f"{name}_enabled" for name in reports_models.REPORT_NAMES}
    for report_name, column_name in _REPORT_FIELDS.items():
        assert column_name in columns, (
            f"{report_name} está en el catálogo pero {column_name} no es una columna de "
            "scheduled_report_recipients: hace falta su migración."
        )


def test_the_builder_handles_every_report_name() -> None:
    """`build_report` encadena `if report == "…"`: un nombre sin rama pasa el `CHECK` y falla al enviar."""
    branches = re.findall(r'^    if report == "([a-z_]+)":$', inspect.getsource(build_report), re.MULTILINE)
    assert branches, "build_report cambió de forma y esta custodia dejó de leerlo"
    assert tuple(branches) == reports_models.REPORT_NAMES, (
        "la tupla y las ramas del constructor de reportes ya no coinciden."
    )


def test_each_vocabulary_gains_only_the_documented_value() -> None:
    """Cada catálogo extendido añade exactamente el valor que explica su comentario."""
    assert (
        set(maintenance_models.EQUIPMENT_STATUSES) - set(maintenance_models.LIVE_EQUIPMENT_STATUSES)
        == {"retired"}
    )
    assert set(inventory_models.SALE_PAYMENT_METHODS) - set(inventory_models.PAYMENT_METHODS) == {"account"}
    assert (
        set(membership_models.PAYMENT_ATTEMPT_METHODS)
        - set(membership_service.MANUAL_MEMBERSHIP_PAYMENT_METHODS)
        == {"spei"}
    )
    assert (
        set(finance_models.BANK_MOVEMENT_STATUSES)
        - set(finance_models.FLAGGABLE_BANK_MOVEMENT_STATUSES)
        == {"reconciled"}
    )
    # El historial de una reserva son los dos estados que no ocupan plaza; de las
    # vivas, la lista de espera es la única que aún no tiene asiento.
    assert (
        set(classes_models.RESERVATION_STATUSES) - set(classes_models.ACTIVE_RESERVATION_STATUSES)
        == {"no_show", "cancelled"}
    )
    assert (
        set(classes_models.ACTIVE_RESERVATION_STATUSES)
        - set(classes_models.SEATED_RESERVATION_STATUSES)
        == {"waitlist"}
    )


# La última copia del vocabulario vive en `main.py`, en los `Literal` de los
# modelos de petición: el panel valida ahí antes de llegar al servicio, así que
# un valor que falte o sobre en esa lista es una puerta que el operador no puede
# usar aunque el catálogo la permita. Se comprueba por el contrato OpenAPI para
# no tocar las rutas.
ROUTE_ENUMS: dict[tuple[str, str], set[str]] = {
    ("SetEquipmentStatusRequest", "status"): set(maintenance_models.LIVE_EQUIPMENT_STATUSES),
    ("CreateSaleRequest", "payment_method"): set(inventory_models.SALE_PAYMENT_METHODS),
    ("CreateSaleReturnRequest", "refund_method"): set(inventory_models.SALE_PAYMENT_METHODS),
    ("CreateMemberAccountPaymentRequest", "method"): set(inventory_models.PAYMENT_METHODS),
    ("BankMovementFlagRequest", "status"): set(finance_models.FLAGGABLE_BANK_MOVEMENT_STATUSES),
    ("BankMovementMatchRequest", "source"): set(finance_models.BANK_MOVEMENT_SOURCES),
}


def _enum_values(schema: dict) -> set[str]:
    if "enum" in schema:
        return set(schema["enum"])
    for branch in schema.get("anyOf", []):
        if "enum" in branch:
            return set(branch["enum"])
    raise AssertionError("la propiedad no declara ninguna lista de valores")


def test_the_panel_payload_enums_are_the_same_lists() -> None:
    components = app.openapi()["components"]["schemas"]
    for (model, prop), expected in ROUTE_ENUMS.items():
        offered = _enum_values(components[model]["properties"][prop])
        assert offered == expected, (
            f"{model}.{prop} ofrece {sorted(offered)} y el catálogo del modelo es {sorted(expected)}: "
            "el panel y el servicio no validan la misma lista."
        )


def test_the_panel_offers_exactly_the_schedulable_reports() -> None:
    """La lista de reportes del panel es un arreglo del `Literal`, con su tope: las dos cosas se comparan."""
    reports = app.openapi()["components"]["schemas"]["ScheduledReportRecipientRequest"]["properties"][
        "reports"
    ]
    offered = _enum_values(reports["items"])
    assert offered == set(reports_models.REPORT_NAMES), (
        f"el panel ofrece {sorted(offered)} y el catálogo es {sorted(reports_models.REPORT_NAMES)}."
    )
    assert reports["maxItems"] == len(reports_models.REPORT_NAMES), (
        "el tope del arreglo se escribió a mano y ya no coincide con la tupla: "
        "el operador no puede marcar todos los reportes a la vez."
    )


# Las cotas de clase son el mismo problema con números en lugar de palabras:
# `le=500` estaba escrito tres veces —sala, sesión nueva y sesión editada—,
# `le=168` dos, y la base solo acotaba por debajo, así que un llamador que no
# pasara por la petición no tenía techo. El tope vive ahora en el modelo, el
# `CHECK` lo renderiza (y `APPLIED_CHECKS` exige su migración) y la petición lo
# importa; comparar las dos puntas del contrato es lo que prueba que el panel
# sigue ofreciendo el número del modelo y no una copia.
ROUTE_BOUNDS: dict[tuple[str, str], tuple[int, int]] = {
    ("RoutineLineRequest", "sets"): (1, routines_models.MAX_ROUTINE_ITEM_SETS),
    ("RoutineLineRequest", "rest_seconds"): (
        0,
        routines_models.MAX_ROUTINE_ITEM_REST_SECONDS,
    ),
    ("CreatePhysioServiceRequest", "duration_minutes"): (
        1,
        physio_models.MAX_DURATION_MINUTES,
    ),
    ("UpdatePhysioServiceRequest", "duration_minutes"): (
        1,
        physio_models.MAX_DURATION_MINUTES,
    ),
    ("CreatePhysioOfferRequest", "sessions"): (1, physio_models.MAX_SESSIONS),
    ("UpdatePhysioOfferRequest", "sessions"): (1, physio_models.MAX_SESSIONS),
    ("CreatePhysioOfferRequest", "validity_days"): (
        1,
        physio_models.MAX_VALIDITY_DAYS,
    ),
    ("UpdatePhysioOfferRequest", "validity_days"): (
        1,
        physio_models.MAX_VALIDITY_DAYS,
    ),
    ("RecordMeasurementRequest", "weight_kg"): (
        None,
        routines_models.MAX_BODY_WEIGHT_KG,
    ),
    ("RecordMeasurementRequest", "waist_cm"): (
        None,
        routines_models.MAX_BODY_MEASUREMENT_CM,
    ),
    ("RecordMeasurementRequest", "chest_cm"): (
        None,
        routines_models.MAX_BODY_MEASUREMENT_CM,
    ),
    ("CreateClassRoomRequest", "capacity"): (1, classes_models.MAX_CLASS_CAPACITY),
    ("CreateClassSessionRequest", "capacity"): (1, classes_models.MAX_CLASS_CAPACITY),
    ("UpdateClassSessionRequest", "capacity"): (1, classes_models.MAX_CLASS_CAPACITY),
    ("CreateClassSessionRequest", "cancel_window_hours"): (
        0,
        classes_models.MAX_CANCEL_WINDOW_HOURS,
    ),
    ("UpdateClassSessionRequest", "cancel_window_hours"): (
        0,
        classes_models.MAX_CANCEL_WINDOW_HOURS,
    ),
}


def _bounds(schema: dict) -> tuple[int | None, int | None]:
    for candidate in [schema, *schema.get("anyOf", [])]:
        if "minimum" in candidate or "maximum" in candidate:
            return candidate.get("minimum"), candidate.get("maximum")
    raise AssertionError("la propiedad no declara ninguna cota numérica")


def test_the_panel_payload_bounds_are_the_model_ceilings() -> None:
    components = app.openapi()["components"]["schemas"]
    for (model, prop), expected in ROUTE_BOUNDS.items():
        offered = _bounds(components[model]["properties"][prop])
        assert offered == expected, (
            f"{model}.{prop} declara {offered} y el modelo del dominio acota en {expected}: "
            "el panel y la base ya no rechazan lo mismo."
        )
