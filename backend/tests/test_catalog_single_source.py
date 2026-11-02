"""Custodia de los catálogos que comparten modelo, servicio y base de datos.

Tres vocabularios estaban escritos a la vez en dos o tres sitios: las formas de
pago del mostrador, los métodos con que se recibe un pago de cuenta y los
estados del equipo. Cada copia es un modo de que la validación del servicio y el
``CHECK`` de la base discrepen —el servicio acepta un valor que el esquema
rechaza, o al revés— sin que ninguna prueba lo note hasta que alguien lo usa.

Hoy el ``CHECK`` se renderiza desde la misma tupla que valida el servicio
(``app.constraints.sql_in_list``), así que la lista vive una sola vez. Esta
custodia fija tres cosas: que el SQL que produce el modelo siga siendo
**byte a byte** el que ya está aplicado en la base —cambiar una tupla cambia el
``CHECK`` y exige una migración, no puede hacerse de pasada—, que el valor de
más en cada vocabulario siga siendo el documentado, y que la lista que ofrece el
panel —el ``Literal`` de la petición, visible en el contrato OpenAPI— sea esa
misma tupla y no una cuarta copia.
"""

from __future__ import annotations

import pytest
from sqlalchemy import CheckConstraint
from sqlmodel import SQLModel

from app.main import app
from app.modules.inventory import models as inventory_models
from app.modules.inventory import service as inventory_service
from app.modules.maintenance import models as maintenance_models
from app.modules.maintenance import service as maintenance_service
from app.modules.memberships import models as membership_models
from app.modules.memberships import service as membership_service

# El SQL exacto que dejaron las migraciones: `20261017_0012` (equipo),
# `20261019_0017` (ventas y devoluciones, que reemplazaron la versión de
# `20261017_0008` y `20261018_0015`) y `20261015_0001` (intentos de pago).
APPLIED_CHECKS: dict[tuple[str, str], str] = {
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
}


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


def test_the_service_uses_the_models_tuple_not_a_copy() -> None:
    """Identidad, no igualdad: una lista reescrita a mano en el servicio se detecta aquí."""
    assert maintenance_service.MANUAL_EQUIPMENT_STATUSES is maintenance_models.LIVE_EQUIPMENT_STATUSES
    assert inventory_service.PAYMENT_METHODS is inventory_models.PAYMENT_METHODS
    assert inventory_service.SALE_PAYMENT_METHODS is inventory_models.SALE_PAYMENT_METHODS
    assert (
        membership_service.MANUAL_MEMBERSHIP_PAYMENT_METHODS
        == tuple(method for method in membership_models.PAYMENT_ATTEMPT_METHODS if method != "spei")
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
