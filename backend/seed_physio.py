"""Seed the preview database with a physiotherapy catalog.

Run it from the ``backend`` directory with the virtualenv Python:

    .\\.venv\\Scripts\\python.exe seed_physio.py

The script is idempotent: it only creates the services and packs that are
missing. It goes through the module service so the discount snapshot and the
validations behave exactly as they do in the panel.
"""

import sys

sys.path.insert(0, r".\src")

from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

from app.modules import access, classes, identity, inventory, memberships, physio  # noqa: E402,F401
from app.modules.physio import service as physio_service  # noqa: E402
from app.modules.physio.models import PhysioOffer, PhysioService  # noqa: E402

DATABASE_URL = "sqlite:///./gym_preview.db"

SERVICES = [
    ("DESCARGA", "Descarga muscular", "Masaje de descarga para piernas y espalda.", 30, 40000),
    ("VALORACION", "Valoración básica", "Revisión de molestias sin diagnóstico médico.", 45, 60000),
    ("RECUPERACION", "Terapia de recuperación", "Trabajo guiado de movilidad y estiramiento.", 60, 80000),
]

# (service_code, name, sessions, price_cents, validity_days)
OFFERS = [
    ("DESCARGA", "Paquete de 2 descargas", 2, 64000, 31),
    ("RECUPERACION", "Paquete de 2 recuperaciones", 2, 128000, 31),
]


def main() -> None:
    engine = create_engine(DATABASE_URL, echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        services = {
            row.code: row for row in session.exec(select(PhysioService)).all()
        }
        created_services = 0
        for code, name, description, duration, price in SERVICES:
            if code in services:
                continue
            item = physio_service.create_physio_service(
                session,
                code=code,
                name=name,
                description=description,
                duration_minutes=duration,
                price_cents=price,
            )
            services[code] = session.get(PhysioService, item.id)
            created_services += 1

        offers = {
            row.name.lower(): row for row in session.exec(select(PhysioOffer)).all()
        }
        created_offers = 0
        for service_code, name, sessions, price, validity in OFFERS:
            if name.lower() in offers:
                continue
            service = services.get(service_code)
            if service is None:
                print(f"Service {service_code} not found: skipping {name}")
                continue
            physio_service.create_physio_offer(
                session,
                service_id=service.id,
                name=name,
                sessions=sessions,
                price_cents=price,
                validity_days=validity,
            )
            created_offers += 1

        print(f"Services created: {created_services} (total {len(SERVICES)})")
        print(f"Offers created: {created_offers} (total {len(OFFERS)})")
        print("Done!")


if __name__ == "__main__":
    main()
