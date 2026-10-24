import sys
sys.path.insert(0, r'.\src')

# Import all models first so SQLModel knows about them
from app.modules import identity, memberships, access, staffing  # noqa: F401
from sqlmodel import create_engine, SQLModel, Session, select
from uuid import uuid4

database_url = "sqlite:///./test_gym.db"
engine = create_engine(database_url, echo=False)

# Create all tables first
SQLModel.metadata.create_all(engine)

with Session(engine) as session:
    from app.modules.memberships.models import Plan
    from app.modules.identity.service import ensure_default_access_control
    
    # Seed default roles first
    ensure_default_access_control(session)
    
    # Create sample plans - all must have duration_days > 0 per model constraint
    plans_data = [
        {"code": "basic", "name": "Básico", "duration_days": 30, "price_cents": 35000, "currency": "MXN", "is_active": True},
        {"code": "premium", "name": "Premium", "duration_days": 30, "price_cents": 55000, "currency": "MXN", "is_active": True},
        {"code": "anual", "name": "Anual", "duration_days": 365, "price_cents": 550000, "currency": "MXN", "is_active": True},
        # "Por Visitas" has duration 1 day per visit, price per visit
        {"code": "visitas", "name": "Por Visitas", "duration_days": 1, "price_cents": 2000, "currency": "MXN", "is_active": True},
    ]
    
    for p in plans_data:
        # Check if plan already exists
        stmt = select(Plan).where(Plan.code == p["code"])
        existing = session.exec(stmt).first()
        if existing:
            continue
        plan = Plan(
            id=uuid4(),
            code=p["code"],
            name=p["name"],
            duration_days=p["duration_days"],
            price_cents=p["price_cents"],
            currency=p["currency"],
            is_active=p["is_active"],
        )
        session.add(plan)
    
    session.commit()
    
    # List plans
    plans = session.exec(select(Plan)).all()
    print(f"Plans created: {len(plans)}")
    for p in plans:
        print(f"  - {p.code}: {p.name} - {p.duration_days} días - ${p.price_cents} {p.currency}")
    
print("Done!")