import sys
sys.path.insert(0, r'.\src')

# Import all models first so SQLModel knows about them
from app.modules import identity, memberships, access, staffing  # noqa: F401
from sqlmodel import create_engine, SQLModel, Session, select
from uuid import uuid4, UUID

database_url = "sqlite:///./test_gym.db"
engine = create_engine(database_url, echo=False)

# Create all tables first
SQLModel.metadata.create_all(engine)

with Session(engine) as session:
    from app.modules.memberships.models import Plan, Member, Membership, MembershipEvent
    from app.modules.identity.service import ensure_default_access_control, register_user
    from app.modules.identity.models import Employee
    from pwdlib import PasswordHash
    
    # Bootstrap the initial access control
    ensure_default_access_control(session)
    
    # Create a test employee
    employee = Employee(
        id=uuid4(),
        employee_number="EMP001",
        first_name="Test",
        last_name="Member",
        email="test.member@example.com",
        phone="5551234567",
        job_title="Socio",
        status="active",
    )
    session.add(employee)
    session.commit()
    print(f"Employee created: {employee.employee_number}")
    
    # Create an app user linked to employee
    user = register_user(
        session,
        email="test.member@example.com",
        password="TestPassword123",
        employee_id=employee.id,
        role_codes=(),  # No roles yet
    )
    print(f"User created: {user.email}")
    
    # Create a Member (socio) - this is the key test
    # Member starts as "pending"
    member = Member(
        id=uuid4(),
        first_name="Test",
        last_name="Member",
        email="test.member@example.com",
        phone="5551234567",
        status="pending",
    )
    session.add(member)
    session.commit()
    print(f"Member created: {member.id}, status: {member.status}")
    
    # Now assign a plan using the no-charge shortcut
    from app.modules.memberships.service import assign_membership_plan
    
    # Get the basic plan
    basic_plan = session.exec(select(Plan).where(Plan.code == "basic")).first()
    print(f"Basic plan: {basic_plan.code}, {basic_plan.name}, {basic_plan.duration_days} days, ${basic_plan.price_cents}")
    
    # Assign membership plan (no-charge shortcut)
    try:
        state = assign_membership_plan(
            session,
            member_id=member.id,
            plan_id=basic_plan.id,
            auto_renew=False,
            actor_id=user.id,
            note="Test membership assignment",
        )
        print(f"Membership assigned successfully!")
        print(f"  Status: {state.status}")
        print(f"  Plan: {state.plan_name}")
        print(f"  Starts at: {state.starts_at}")
        print(f"  Ends at: {state.ends_at}")
        print(f"  Auto-renew: {state.auto_renew}")
        print(f"  Previous status: {state.previous_status}")
        print(f"  Plan changed: {state.plan_changed}")
        
        # Check the membership was created
        membership = session.get(Membership, state.membership_id)
        if membership:
            print(f"  Membership ID: {membership.id}")
            print(f"  Membership status: {membership.status}")
        
        # Check the member status was updated
        session.refresh(member)
        print(f"  Member status after: {member.status}")
        
        # Check the membership event
        events = session.exec(
            select(MembershipEvent).where(MembershipEvent.membership_id == state.membership_id)
        ).all()
        print(f"  Membership events: {len(events)}")
        for e in events:
            md = e.event_metadata or {}
            print(f"    - {e.event_type}: from={e.from_status} to={e.to_status}, metadata={md}")
        
    except Exception as e:
        print(f"Error assigning membership: {e}")
        import traceback
        traceback.print_exc()
    
print("\nDone!")