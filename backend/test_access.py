import sys
sys.path.insert(0, r'.\src')

from sqlmodel import create_engine, SQLModel, Session, select
from uuid import uuid4, UUID
from datetime import datetime, timedelta, timezone

from app.modules import identity, memberships, access  # noqa: F401
from app.modules.memberships.models import Plan, Member, Membership, MembershipEvent
from app.modules.access.models import (
    AccessSnapshot, AccessRequest, AccessDirection, AccessReason,
    AccessDecision, AccessWindow
)
from app.modules.access.service import evaluate_access, record_access_event, record_manual_access, _as_utc
from zoneinfo import ZoneInfo

database_url = "sqlite:///./test_gym.db"
engine = create_engine(database_url, echo=False)

# Import all models
SQLModel.metadata.create_all(engine)

with Session(engine) as session:
    from app.modules.memberships.service import assign_membership_plan
    from app.modules.identity.service import ensure_default_access_control, register_user
    from app.modules.identity.models import Employee
    
    ensure_default_access_control(session)
    
    # Create employee with unique number
    employee = Employee(
        id=uuid4(),
        employee_number="EMP999",
        first_name="Test",
        last_name="Member2",
        email="test.access2@example.com",
        phone="5551234568",
        job_title="Socio",
        status="active",
    )
    session.add(employee)
    session.commit()
    
    # Register member
    member = Member(
        id=uuid4(),
        first_name="Test",
        last_name="Member",
        email="test.access@example.com",
        phone="5551234567",
        status="pending",
    )
    session.add(member)
    session.commit()
    
    # Assign membership plan
    basic_plan = session.exec(select(Plan).where(Plan.code == "basic")).first()
    assign_membership_plan(
        session,
        member_id=member.id,
        plan_id=basic_plan.id,
        auto_renew=False,
        actor_id=employee.id,
        note="Test for access evaluation",
    )
    session.commit()
    print("Member and membership created and activated")
    
    # Now test access evaluation
    tz = ZoneInfo("America/Mexico_City")
    now = datetime.now(tz)
    
    # Create snapshot with valid membership
    snapshot = AccessSnapshot(
        member_id=member.id,
        membership_status="active",
        membership_starts_at=_as_utc(now - timedelta(days=1)),
        membership_ends_at=_as_utc(now + timedelta(days=30)),
        blocking_debt=False,
        cached_at=_as_utc(now),
        valid_until=_as_utc(now + timedelta(days=1)),
        allowed_windows=(
            AccessWindow(weekday=0, starts_at=datetime(1, 1, 1, 8, 0).time(),
                        ends_at=datetime(1, 1, 1, 22, 0).time()),
            AccessWindow(weekday=1, starts_at=datetime(1, 1, 1, 8, 0).time(),
                        ends_at=datetime(1, 1, 1, 22, 0).time()),
        ),
        daily_entry_limit=1,
        entries_today=0,
        antipassback_seconds=60,
    )
    session.add(snapshot)
    session.commit()
    print(f"Snapshot created: {snapshot.member_id}")
    
    # Test access request (entry) - within hours
    request = AccessRequest(
        event_id=uuid4(),
        member_id=member.id,
        reader_id="LectorPrincipal",
        direction=AccessDirection.ENTRY,
        occurred_at=_as_utc(now),
        current_occupancy=50,
        max_occupancy=120,
        offline=False,
    )
    
    decision = evaluate_access(
        snapshot,
        request,
        timezone_name="America/Mexico_City",
    )
    
    print(f"Access decision (within hours): authorized={decision.authorized}, reason={decision.reason}")
    
    # Record the access event
    recorded = record_access_event(
        session,
        decision,
        reader_id="LectorPrincipal",
        source="reader",
    )
    print(f"Access event recorded: event_id={recorded.event_id}, authorized={recorded.authorized}")
    session.commit()
    
    # Test a denied access (outside hours) - 23:00 is outside 08:00-22:00
    request_outside = AccessRequest(
        event_id=uuid4(),
        member_id=member.id,
        reader_id="LectorPrincipal",
        direction=AccessDirection.ENTRY,
        occurred_at=_as_utc(now + timedelta(hours=23)),  # 11 PM, outside hours
        current_occupancy=50,
        max_occupancy=120,
        offline=False,
    )
    
    decision_outside = evaluate_access(
        snapshot,
        request_outside,
        timezone_name="America/Mexico_City",
    )
    
    print(f"Outside hours decision: authorized={decision_outside.authorized}, reason={decision_outside.reason}")
    
    # Record the denied event
    recorded_outside = record_access_event(
        session,
        decision_outside,
        reader_id="LectorPrincipal",
        source="reader",
    )
    print(f"Outside hours event recorded: event_id={recorded_outside.event_id}, authorized={recorded_outside.authorized}")
    session.commit()
    
    # Test manual access
    manual = record_manual_access(
        session,
        member_id=member.id,
        note="Visita de prueba",
        reader_id="Recepción",
        occurred_at=now,
    )
    print(f"Manual access recorded: event_id={manual.event_id}, authorized={manual.authorized}")
    session.commit()
    
    # List access events
    from app.modules.access.service import list_access_events
    events_page = list_access_events(
        session,
        page=1,
        page_size=10,
    )
    print(f"\nAccess events list: total={events_page.total}")
    for ev in events_page.items:
        print(f"  - {ev.direction}: {'authorized' if ev.authorized else 'denied'} - {ev.reason} - {ev.source}")
    
print("\nDone!")