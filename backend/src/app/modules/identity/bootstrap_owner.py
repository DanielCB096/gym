from getpass import getpass
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlmodel import Session

from app.modules.identity.service import IdentityError, bootstrap_initial_owner


def main() -> None:
    load_dotenv()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL must point to a migrated database")

    email = input("Correo del dueño inicial: ").strip()
    password = getpass("Contraseña inicial (mínimo 12 caracteres): ")
    confirmation = getpass("Confirma la contraseña: ")
    if password != confirmation:
        raise SystemExit("Las contraseñas no coinciden")

    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            user = bootstrap_initial_owner(session, email=email, password=password)
            print(f"Cuenta inicial creada: {user.email}")
    except IdentityError as error:
        raise SystemExit(str(error)) from error
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()