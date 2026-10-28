from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import csv
import io
import json
import os
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

from app.modules.access.models import (
    AccessDirection,
    AccessMemberNotFound,
    AccessRequest,
    AccessSnapshot,
    AccessWindow,
)
from app.modules.access.offline_store import SQLiteAccessStore
from app.modules.access.service import (
    access_event_item,
    access_today_summary,
    list_access_events,
    record_access_event,
    record_manual_access,
)
from app.modules.classes import (
    ClassRoomItem,
    ClassRoomNotFound,
    ClassSessionItem,
    ClassSessionNotFound,
    ClassTypeItem,
    ClassTypeNotFound,
    ClassesError,
    DuplicateClassRoom,
    DuplicateClassType,
    DuplicateReservation,
    InstructorItem,
    InstructorNotFound,
    InvalidClassData,
    InvalidReservationState,
    InvalidSessionState,
    MemberNotAvailable,
    ReservationItem,
    ReservationNotFound,
    SessionFull,
    UNSET,
    cancel_class_session,
    cancel_reservation,
    create_class_room,
    create_class_session,
    create_class_type,
    list_class_rooms,
    list_class_sessions,
    list_class_types,
    list_instructors,
    list_session_reservations,
    mark_attendance,
    reserve_seat,
    update_class_session,
)
from app.modules.routines import (
    AssignmentDetail,
    AssignmentItem,
    AssignmentNotFound,
    DuplicateActiveGoal,
    DuplicateAssignment,
    DuplicateExercise,
    DuplicateRoutineExercise,
    EmptyRoutine,
    ExerciseItem,
    ExerciseNotFound,
    ExercisePage,
    ExerciseUnavailable,
    GoalNotFound,
    InvalidAssignmentState,
    InvalidGoalData,
    InvalidGoalState,
    InvalidMeasurement,
    InvalidProgressPhoto,
    InvalidRoutineData,
    InvalidRoutineState,
    InvalidWorkoutData,
    InvalidWorkoutState,
    MeasurementItem,
    MemberGoalItem,
    MemberNotEligible,
    MemberProgress,
    ModuleOverview,
    ProgressPhotoItem,
    ProgressPhotoNotFound,
    ProgressPhotoTooLarge,
    RoutineDetail,
    RoutineItemInput,
    RoutineItemView,
    RoutineLine,
    RoutineNotFound,
    RoutineRevisionItem,
    RoutinesError,
    UNSET as ROUTINES_UNSET,
    WorkoutItem,
    WorkoutNotFound,
    WorkoutSetInput,
    archive_routine,
    cancel_assignment,
    cancel_member_goal,
    complete_assignment,
    create_assignment,
    create_exercise,
    create_member_goal,
    create_routine,
    delete_progress_photo,
    get_assignment,
    get_routine,
    list_assignments,
    list_exercises,
    list_measurements,
    list_member_goals,
    list_progress_photos,
    list_routines,
    list_workouts,
    log_workout,
    member_progress,
    module_overview,
    progress_photo_file,
    record_measurement,
    record_progress_photo,
    replace_routine_items,
    review_workout,
    update_exercise,
    update_member_goal,
    update_routine,
)
from app.modules.routines.photo_storage import MAX_PROGRESS_PHOTO_BYTES
from app.modules.maintenance import (
    AreaServiceStatus,
    ChecklistItem,
    ChecklistPage,
    DuplicateSerial,
    EquipmentChoice,
    EquipmentDetail,
    EquipmentItem,
    EquipmentNotFound,
    EquipmentPage,
    EquipmentSummary,
    InvalidChecklistData,
    InvalidEquipmentData,
    InvalidEquipmentState,
    InvalidRecordData,
    InvalidTicketData,
    InvalidTicketState,
    LinkedExercise,
    MaintenanceError,
    MaintenanceOverview,
    MaintenanceRecordItem,
    RecordPage,
    TicketDetail,
    TicketItem,
    TicketNotFound,
    TicketPage,
    TicketSummary,
    UNSET as MAINTENANCE_UNSET,
    cancel_ticket,
    create_equipment,
    create_ticket,
    equipment_choices,
    get_equipment,
    get_ticket,
    list_checklists,
    list_equipment,
    list_records,
    list_tickets,
    module_overview as maintenance_overview,
    record_checklist,
    record_maintenance,
    resolve_ticket,
    retire_equipment,
    service_status,
    set_equipment_status,
    start_ticket,
    update_equipment,
    update_ticket,
)
from app.modules.identity import models as identity_models
from app.modules.identity.models import AuthEvent, Employee
from app.modules.inventory import (
    AccountAging,
    CashSessionAlreadyOpen,
    CashSessionNotFound,
    CashSessionView,
    CreditLimitExceeded,
    DifferenceExplanationRequired,
    DuplicateProductBarcode,
    DuplicateProductSku,
    DuplicateSupplierName,
    InsufficientStock,
    InvalidAccountPayment,
    InvalidCart,
    InvalidCashSessionState,
    InvalidCreditLimit,
    InvalidProductData,
    InvalidPurchaseOrderData,
    InvalidPurchaseOrderState,
    InvalidReturn,
    InvalidStatementFormat,
    InvalidStatementPurpose,
    InvalidSupplierData,
    InventoryError,
    MemberAccountEntry,
    MemberAccountPage,
    MemberAccountPaymentView,
    MemberAccountStatement,
    MemberAccountSummary,
    MemberUnavailable,
    NoOpenCashSession,
    NoOutstandingBalance,
    OfflineSaleEntry,
    OfflineSaleResult,
    PaymentExceedsBalance,
    ProductItem,
    ProductNotFound,
    ProductUnavailable,
    PurchaseOrderLine,
    PurchaseOrderNotFound,
    PurchaseOrderOverReceive,
    PurchaseOrderPage,
    PurchaseOrderSummary,
    PurchaseOrderView,
    ReturnExceedsSold,
    SaleItemNotFound,
    SaleItemView,
    SaleNotFound,
    SaleReturnView,
    StatementDeliveryFailed,
    StatementDeliveryList,
    StatementDeliveryNotFound,
    StatementDeliveryRetryNotAllowed,
    StatementDeliveryView,
    StatementEmailNotConfigured,
    StatementRecipientMissing,
    StatementReminderBatch,
    StatementReminderNotAllowed,
    SupplierItem,
    SupplierNotFound,
    SupplierPage,
    build_member_account_statement_csv,
    build_member_account_statement_pdf,
    cancel_purchase_order,
    close_cash_session,
    create_product,
    create_purchase_order,
    create_supplier,
    current_cash_session,
    get_purchase_order,
    list_cash_sessions,
    list_member_account_statement_deliveries,
    list_member_accounts,
    list_products,
    list_purchase_orders,
    list_sale_returns,
    list_sales,
    list_suppliers,
    member_account_statement,
    open_cash_session,
    receive_purchase_order,
    register_member_account_payment,
    register_sale,
    register_sale_return,
    register_stock_movement,
    retry_member_account_statement_delivery,
    send_member_account_reminders,
    send_member_account_statement,
    send_purchase_order,
    statement_filename,
    sync_offline_sales,
    update_member_credit_limit,
    update_product,
    update_supplier,
)
from app.modules.identity.service import (
    AuthenticatedUser,
    AuthenticationFailed,
    IdentityError,
    ImmutableRole,
    InvalidSession,
    LastOwnerRequired,
    PermissionDenied,
    PermissionNotFound,
    RoleNotFound,
    SessionNotFound,
    UserUnavailable,
    assign_role,
    authenticate_session,
    authenticate_user,
    bootstrap_initial_owner,
    ensure_default_access_control,
    grant_role_permission,
    list_active_sessions,
    list_roles_and_permissions,
    list_users,
    register_user,
    require_permission,
    revoke_role,
    revoke_role_permission,
    revoke_session,
    revoke_session_by_id,
    set_user_status,
)
from app.modules.memberships import models as membership_models
from app.modules.memberships.gateway import ChargeOutcome, ChargeStatus, VerifiedWebhook
from app.modules.memberships.models import Member, MemberConsent, Membership, PaymentMethod, Plan, utc_now
from app.modules.memberships.service import (
    BillingError,
    CancellationReasonRequired,
    CashSessionRequired,
    DuplicateMemberEmail,
    IdempotencyConflict,
    InvalidMemberData,
    InvalidMembershipPayment,
    InvalidMembershipTransition,
    MemberNotFound,
    MembershipNotFound,
    MembershipPaymentNotAllowed,
    MembershipState,
    PlanUnavailable,
    assign_membership_plan,
    cancel_membership,
    collect_membership_payment,
    freeze_membership,
    list_member_overview,
    member_directory_summary,
    process_verified_webhook,
    register_member,
    resume_membership,
    retry_failed_charge,
    start_first_charge,
    update_member,
)
from app.modules.notifications import (
    MemberNotificationItem,
    NotificationError,
    StaffNotificationItem,
    list_member_notifications,
    list_staff_notifications,
    mark_all_notifications_read,
    mark_all_staff_notifications_read,
    mark_notification_read,
    mark_staff_notification_read,
    unread_notification_count,
    unread_staff_notification_count,
)
from app.modules.portal.classes import (
    MemberClassItem,
    MemberClassNotAllowed,
    MemberReservationSummary,
    cancel_member_reservation,
    list_member_classes,
    reserve_member_class,
)
from app.modules.portal.routines import (
    InvalidProgressPhotoLink,
    MemberAssignmentSummary,
    MemberProgressPhotos,
    MemberProgressView,
    MemberRoutineDetail,
    MemberRoutineList,
    ProgressPhotoConsentRequired,
    cancel_member_goal_from_app,
    create_member_goal_from_app,
    delete_member_progress_photo,
    get_member_progress,
    get_member_routine,
    list_member_progress_photos,
    list_member_routines,
    log_member_workout,
    progress_photo_link,
    record_member_measurement,
    record_member_progress_photo,
    verify_progress_photo_link,
)
from app.modules.portal.invoices import (
    BillableOriginItem,
    InvalidDownloadLink,
    MemberInvoiceItem,
    download_member_invoice,
    list_billable_origins,
    list_member_invoices,
    member_fiscal_profile,
    request_member_invoice,
    verify_download_link,
)
from app.modules.portal.payments import (
    MemberPaymentItem,
    get_member_account,
    list_member_payments,
)
from app.modules.portal.service import (
    AuthenticatedMember,
    InvalidMemberCode,
    InvalidMemberSession,
    MemberAuthUnavailable,
    MemberDeliveryFailed,
    MemberPortalError,
    MemberProfile,
    authenticate_member_session,
    member_profile,
    request_login_code,
    revoke_member_session,
    verify_login_code,
)
from app.modules.staffing.models import StaffAttendance, StaffShift
from app.modules.staffing.service import (
    AttendanceAlreadyRecorded,
    AttendanceEventConflict,
    AttendanceNotAllowed,
    InvalidAttendanceTime,
    ShiftNotAvailable,
    ShiftOverlap,
    clock_in,
    clock_out,
    create_shift,
    list_shifts_with_attendance,
)
from app.modules.billing import (
    # The memberships module already exposes a ``BillingError`` base class in
    # this file; keep the CFDI one under its own name so both handlers coexist.
    BillingError as CfdiError,
    BillingMemberNotFound,
    CancellationNotAllowed,
    FiscalDataInvalid,
    FiscalProfileView,
    GlobalInvoiceNoEligibleSales,
    GlobalInvoicePeriodConflict,
    InvoiceDeliveryFailed,
    InvoiceEmailNotConfigured,
    InvoiceIdempotencyConflict,
    InvoiceNotFound,
    InvoiceNumberingError,
    InvoiceStateError,
    OriginAlreadyInvoiced,
    OriginNotFound,
    OriginNotInvoiceable,
    PacRejected,
    PacUnavailable,
    PaymentComplementNotFound,
    cancel_invoice,
    cancel_payment_complement,
    create_credit_note,
    create_global_invoice,
    create_invoice,
    create_payment_complement,
    get_fiscal_profile,
    get_invoice,
    get_payment_complement,
    invoice_pdf,
    invoice_summary,
    invoice_xml,
    list_global_invoice_eligibility,
    list_invoices,
    list_origin_options,
    list_ppd_receivables,
    payment_complement_pdf,
    payment_complement_xml,
    refresh_cancellation_status,
    save_fiscal_profile,
    send_invoice_email,
    stamp_invoice,
    stamp_payment_complement,
)
from app.modules.finance import (
    BankAccountNotFound,
    BankMovementNotFound,
    BankMovementStateError,
    CandidateUnavailable,
    DuplicateBankAccount,
    FinanceError,
    InvalidBankData,
    InvalidImportBatch,
    InvalidMatch,
    MatchCandidateNotFound,
    create_bank_account,
    flag_bank_movement,
    get_bank_movement,
    import_bank_movements,
    list_bank_accounts,
    list_bank_movements,
    match_bank_movement,
    unmatch_bank_movement,
    update_bank_account_status,
)
from app.modules.reports import (
    InvalidReportPeriod,
    InventoryReport,
    MaintenanceReport,
    MembershipReport,
    OperationsReport,
    OverviewReport,
    ReportError,
    ReportPeriod,
    RevenueReport,
    UnknownReport,
    build_export,
    build_report,
    resolve_period,
)
from app.timezone import DEFAULT_TIMEZONE

PreviewOutcome = Literal["succeeded", "failed", "unknown", "processing"]
PREVIEW_MODE = os.getenv("PREVIEW_MODE", "").lower() == "true"
CORS_ORIGINS = tuple(
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
)
DATABASE_URL = os.getenv("DATABASE_URL")
if PREVIEW_MODE and not DATABASE_URL:
    DATABASE_URL = "sqlite:///./gym_preview.db"

engine: Engine | None = None
if DATABASE_URL:
    connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
    engine = create_engine(DATABASE_URL, connect_args=connect_args)

access_store = (
    SQLiteAccessStore(os.getenv("ACCESS_OUTBOX_PATH", "./access_outbox.sqlite3"))
    if PREVIEW_MODE
    else None
)


class PreviewGateway:
    def __init__(self, outcome: PreviewOutcome) -> None:
        self.outcome = ChargeStatus(outcome)

    def charge(self, attempt: membership_models.PaymentAttempt, payment_method: PaymentMethod) -> ChargeOutcome:
        del payment_method
        provider_reference = None if self.outcome == ChargeStatus.UNKNOWN else f"preview_{attempt.id}"
        failure_code = "preview_declined" if self.outcome == ChargeStatus.FAILED else None
        if self.outcome == ChargeStatus.UNKNOWN:
            failure_code = "preview_timeout"
        return ChargeOutcome(
            status=self.outcome,
            provider_reference=provider_reference,
            failure_code=failure_code,
            occurred_at=utc_now(),
        )


class PreviewSeedResponse(BaseModel):
    member_id: UUID
    plan_id: UUID
    payment_method_id: UUID
    amount_cents: int
    currency: str


class FirstChargeRequest(BaseModel):
    member_id: UUID
    plan_id: UUID
    payment_method_id: UUID
    idempotency_key: str = Field(min_length=1, max_length=128)
    outcome: PreviewOutcome = "succeeded"


class RetryRequest(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=128)
    outcome: PreviewOutcome = "succeeded"


class WebhookRequest(BaseModel):
    provider_event_id: str = Field(min_length=1, max_length=160)
    outcome: PreviewOutcome = "succeeded"


class PreviewAccessWindow(BaseModel):
    weekday: int = Field(ge=0, le=6)
    starts_at: time
    ends_at: time


class PreviewAccessSnapshotRequest(BaseModel):
    valid_for_seconds: int = Field(default=300, ge=1, le=3600)
    blocking_debt: bool = False
    allowed_windows: list[PreviewAccessWindow] | None = None
    daily_entry_limit: int | None = Field(default=None, ge=1)
    entries_today: int = Field(default=0, ge=0)


class PreviewAccessCheckRequest(BaseModel):
    event_id: UUID
    member_id: UUID
    reader_id: str = Field(min_length=1, max_length=100)
    direction: AccessDirection
    occurred_at: datetime
    current_occupancy: int = Field(ge=0)
    max_occupancy: int = Field(ge=1)
    offline: bool = True


class PreviewOutboxAckRequest(BaseModel):
    event_ids: list[UUID] = Field(min_length=1, max_length=500)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class UserResponse(BaseModel):
    id: UUID
    email: str
    employee_id: UUID | None
    roles: list[str]
    permissions: list[str]


class CreatedUserResponse(BaseModel):
    id: UUID
    email: str
    employee_id: UUID | None
    roles: list[str]


class UserOverviewResponse(BaseModel):
    id: UUID
    email: str
    status: str
    employee_id: UUID | None
    employee_name: str | None
    roles: list[str]
    last_login_at: datetime | None


class SessionOverviewResponse(BaseModel):
    id: UUID
    user_id: UUID
    email: str
    employee_name: str | None
    created_at: datetime
    expires_at: datetime
    last_seen_at: datetime | None
    is_current: bool


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_at: datetime
    user: UserResponse


class MemberCodeRequest(BaseModel):
    email: EmailStr


class MemberCodeRequestResponse(BaseModel):
    status: Literal["accepted"] = "accepted"
    expires_in: int
    preview_code: str | None = None


class MemberVerifyRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class MemberSessionSummaryResponse(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    email: str | None
    status: str


class MemberSessionMembershipResponse(BaseModel):
    plan_name: str
    status: str
    starts_at: datetime
    ends_at: datetime
    auto_renew: bool
    days_remaining: int


class MemberAuthResponse(BaseModel):
    access_token: str
    token_type: str
    expires_at: datetime
    member: MemberSessionSummaryResponse


class MemberPortalProfileResponse(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    status: str
    member_since: datetime
    membership: MemberSessionMembershipResponse | None
    balance_cents: int
    access_enabled: bool


class MemberClassReservationResponse(BaseModel):
    id: UUID
    session_id: UUID
    status: str
    waitlist_position: int | None
    late_cancellation: bool
    created_at: datetime


class MemberClassResponse(BaseModel):
    id: UUID
    title: str
    class_type_name: str
    room_name: str | None
    instructor_name: str | None
    starts_at: datetime
    ends_at: datetime
    capacity: int
    access_type: str
    extra_price_cents: int
    waitlist_enabled: bool
    cancel_window_hours: int
    notes: str | None
    reserved_count: int
    waitlist_count: int
    spots_left: int
    can_reserve: bool
    blocked_reason: str | None
    reservation: MemberClassReservationResponse | None


class MemberClassDirectoryResponse(BaseModel):
    items: list[MemberClassResponse]
    total: int
    page: int
    page_size: int
    pages: int


class CreateEmployeeRequest(BaseModel):
    employee_number: str = Field(min_length=1, max_length=40)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=30)
    job_title: str = Field(min_length=1, max_length=100)


class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=1024)
    employee_id: UUID | None = None
    role_codes: list[str] = Field(default_factory=list, max_length=10)


class RoleAssignmentRequest(BaseModel):
    role_code: str = Field(min_length=1, max_length=50)


class UpdateUserStatusRequest(BaseModel):
    status: Literal["active", "disabled"]


class RolePermissionRequest(BaseModel):
    permission_code: str = Field(min_length=1, max_length=100)


class ScheduleShiftRequest(BaseModel):
    starts_at: datetime
    ends_at: datetime


class AttendanceMarkRequest(BaseModel):
    shift_id: UUID
    request_id: UUID


class ProductResponse(BaseModel):
    id: UUID
    sku: str
    name: str
    category: str
    barcode: str | None
    price_cents: int
    cost_cents: int | None
    stock_min: int
    is_active: bool
    stock: int
    state: str
    updated_at: datetime


class ProductSummaryResponse(BaseModel):
    total: int
    active: int
    low_stock: int
    out_of_stock: int
    inactive: int


class ProductDirectoryResponse(BaseModel):
    items: list[ProductResponse]
    total: int
    page: int
    page_size: int
    pages: int
    summary: ProductSummaryResponse
    categories: list[str]


class CreateProductRequest(BaseModel):
    sku: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=160)
    category: str | None = Field(default=None, max_length=80)
    barcode: str | None = Field(default=None, max_length=64)
    price_cents: int = Field(ge=0)
    cost_cents: int | None = Field(default=None, ge=0)
    stock_min: int = Field(default=0, ge=0)
    initial_stock: int = Field(default=0, ge=0)


class UpdateProductRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    category: str | None = Field(default=None, max_length=80)
    barcode: str | None = Field(default=None, max_length=64)
    price_cents: int = Field(ge=0)
    cost_cents: int | None = Field(default=None, ge=0)
    stock_min: int = Field(default=0, ge=0)
    is_active: bool = True


class StockMovementRequest(BaseModel):
    movement_type: Literal["intake", "adjustment", "waste"]
    quantity: int
    reason: str | None = Field(default=None, max_length=200)


class SaleLineResponse(BaseModel):
    sale_item_id: UUID
    product_id: UUID
    product_name: str
    sku: str
    quantity: int
    unit_price_cents: int
    line_total_cents: int
    refunded_quantity: int
    returnable_quantity: int


class SaleResponse(BaseModel):
    id: UUID
    folio: str
    status: str
    payment_method: str
    member_id: UUID | None
    member_name: str | None
    cashier_id: UUID | None
    cashier_email: str | None
    subtotal_cents: int
    discount_cents: int
    tax_cents: int
    total_cents: int
    refunded_cents: int
    note: str | None
    sold_at: datetime
    cash_session_id: UUID | None
    origin: str
    client_reference: str | None
    lines: list[SaleLineResponse]


class SaleSummaryResponse(BaseModel):
    count: int
    total_cents: int
    cash_cents: int
    card_cents: int
    transfer_cents: int
    account_cents: int
    refunds_cents: int
    refunded_count: int


class SaleDirectoryResponse(BaseModel):
    items: list[SaleResponse]
    total: int
    page: int
    page_size: int
    pages: int
    summary: SaleSummaryResponse


class SaleReturnLineResponse(BaseModel):
    sale_item_id: UUID
    product_id: UUID
    product_name: str
    sku: str
    quantity: int
    unit_price_cents: int
    line_refund_cents: int
    disposition: str


class SaleReturnResponse(BaseModel):
    id: UUID
    folio: str
    sale_id: UUID
    sale_folio: str
    cash_session_id: UUID | None
    member_id: UUID | None
    member_name: str | None
    actor_id: UUID | None
    actor_email: str | None
    refund_method: str
    total_refund_cents: int
    reason: str
    returned_at: datetime
    lines: list[SaleReturnLineResponse]


class SaleReturnSummaryResponse(BaseModel):
    count: int
    total_refund_cents: int
    cash_refund_cents: int
    card_refund_cents: int
    transfer_refund_cents: int
    account_refund_cents: int


class SaleReturnDirectoryResponse(BaseModel):
    items: list[SaleReturnResponse]
    total: int
    page: int
    page_size: int
    pages: int
    summary: SaleReturnSummaryResponse


class SaleItemRequest(BaseModel):
    product_id: UUID
    quantity: int = Field(ge=1)


class CreateSaleRequest(BaseModel):
    items: list[SaleItemRequest] = Field(min_length=1)
    payment_method: Literal["cash", "card", "transfer", "account"]
    member_id: UUID | None = None
    note: str | None = Field(default=None, max_length=200)


class OfflineSaleRequest(BaseModel):
    client_reference: str = Field(min_length=1, max_length=64)
    items: list[SaleItemRequest] = Field(min_length=1)
    payment_method: Literal["cash", "card", "transfer", "account"]
    member_id: UUID | None = None
    note: str | None = Field(default=None, max_length=200)
    sold_at: datetime


class SyncOfflineSalesRequest(BaseModel):
    sales: list[OfflineSaleRequest] = Field(min_length=1, max_length=100)


class OfflineSaleResultResponse(BaseModel):
    client_reference: str
    status: Literal["created", "duplicate", "rejected"]
    sale: SaleResponse | None
    error: str | None


class OfflineSaleSyncResponse(BaseModel):
    results: list[OfflineSaleResultResponse]
    created: int
    duplicates: int
    rejected: int


class SaleReturnLineRequest(BaseModel):
    sale_item_id: UUID
    quantity: int = Field(ge=1)
    disposition: Literal["restock", "write_off"] = "restock"


class CreateSaleReturnRequest(BaseModel):
    items: list[SaleReturnLineRequest] = Field(min_length=1)
    refund_method: Literal["cash", "card", "transfer", "account"] | None = None
    reason: str = Field(min_length=1, max_length=200)


class CashSessionResponse(BaseModel):
    id: UUID
    status: str
    opened_by: UUID | None
    opened_by_email: str | None
    opened_at: datetime
    opening_cash_cents: int
    closed_by: UUID | None
    closed_by_email: str | None
    closed_at: datetime | None
    expected_cash_cents: int
    counted_cash_cents: int | None
    difference_cents: int | None
    notes: str | None
    sales_count: int
    total_sales_cents: int
    cash_sales_cents: int
    card_sales_cents: int
    transfer_sales_cents: int
    account_sales_cents: int
    refunds_count: int
    total_refunds_cents: int
    cash_refunds_cents: int
    account_refunds_cents: int
    account_payments_count: int
    account_payments_cents: int
    cash_account_payments_cents: int
    membership_payments_count: int
    membership_payments_cents: int
    cash_membership_payments_cents: int


class OpenCashSessionRequest(BaseModel):
    opening_cash_cents: int = Field(default=0, ge=0)


class CloseCashSessionRequest(BaseModel):
    counted_cash_cents: int = Field(ge=0)
    notes: str | None = Field(default=None, max_length=500)


class MemberAccountEntryResponse(BaseModel):
    kind: str
    occurred_at: datetime
    description: str
    reference: str
    method: str | None
    amount_cents: int
    balance_cents: int


class AccountAgingResponse(BaseModel):
    current_cents: int
    days_31_60_cents: int
    days_61_90_cents: int
    over_90_cents: int


class MemberAccountSummaryResponse(BaseModel):
    member_id: UUID
    member_name: str
    email: str | None
    phone: str | None
    member_status: str
    charges_cents: int
    credits_cents: int
    payments_cents: int
    balance_cents: int
    credit_limit_cents: int | None
    credit_available_cents: int | None
    over_limit: bool
    aging: AccountAgingResponse
    charges_count: int
    payments_count: int
    last_activity_at: datetime | None
    oldest_charge_at: datetime | None


class MemberAccountDirectoryResponse(BaseModel):
    items: list[MemberAccountSummaryResponse]
    total: int
    page: int
    page_size: int
    pages: int
    total_receivable_cents: int
    total_credit_cents: int
    members_with_balance: int
    aging: AccountAgingResponse
    over_limit_members: int
    as_of: date


class MemberAccountStatementResponse(BaseModel):
    summary: MemberAccountSummaryResponse
    entries: list[MemberAccountEntryResponse]
    as_of: date


class SendMemberAccountStatementRequest(BaseModel):
    format: Literal["pdf", "csv"] = "pdf"
    recipient: EmailStr | None = None


class StatementDeliveryResponse(BaseModel):
    id: UUID
    member_id: UUID
    actor_id: UUID | None
    actor_email: str | None
    recipient: str
    format: str
    purpose: str
    status: str
    as_of: date
    error: str | None
    retry_of_id: UUID | None
    created_at: datetime


class StatementDeliveryPageResponse(BaseModel):
    items: list[StatementDeliveryResponse]
    total: int
    page: int
    page_size: int
    pages: int


class SendStatementRemindersRequest(BaseModel):
    member_ids: list[UUID] = Field(min_length=1, max_length=50)
    format: Literal["pdf", "csv"] = "pdf"


class StatementReminderResultResponse(BaseModel):
    member_id: UUID
    member_name: str | None
    status: str
    reason: str | None
    balance_cents: int
    overdue_cents: int
    delivery: StatementDeliveryResponse | None


class StatementReminderBatchResponse(BaseModel):
    requested: int
    sent: int
    simulated: int
    skipped: int
    failed: int
    results: list[StatementReminderResultResponse]


class MemberAccountPaymentResponse(BaseModel):
    id: UUID
    member_id: UUID
    member_name: str | None
    cash_session_id: UUID | None
    actor_id: UUID | None
    actor_email: str | None
    method: str
    amount_cents: int
    note: str | None
    paid_at: datetime
    balance_cents: int


class CreateMemberAccountPaymentRequest(BaseModel):
    amount_cents: int = Field(gt=0)
    method: Literal["cash", "card", "transfer"]
    note: str | None = Field(default=None, max_length=200)


class UpdateMemberCreditLimitRequest(BaseModel):
    credit_limit_cents: int | None = Field(ge=0)


class SupplierResponse(BaseModel):
    id: UUID
    name: str
    contact_name: str | None
    phone: str | None
    email: str | None
    notes: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SupplierDirectoryResponse(BaseModel):
    items: list[SupplierResponse]
    total: int
    page: int
    page_size: int
    pages: int


class CreateSupplierRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    contact_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=500)


class UpdateSupplierRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    contact_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=500)
    is_active: bool = True


class PurchaseOrderLineResponse(BaseModel):
    item_id: UUID
    product_id: UUID
    product_name: str
    sku: str
    quantity: int
    received_quantity: int
    pending_quantity: int
    unit_cost_cents: int
    line_total_cents: int


class PurchaseOrderResponse(BaseModel):
    id: UUID
    folio: str
    supplier_id: UUID
    supplier_name: str
    status: str
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    expected_at: date | None
    notes: str | None
    created_by: UUID | None
    created_by_email: str | None
    received_by: UUID | None
    received_by_email: str | None
    created_at: datetime
    sent_at: datetime | None
    received_at: datetime | None
    cancelled_at: datetime | None
    lines: list[PurchaseOrderLineResponse]


class PurchaseOrderSummaryResponse(BaseModel):
    count: int
    created: int
    sent: int
    received: int
    cancelled: int
    total_cents: int


class PurchaseOrderDirectoryResponse(BaseModel):
    items: list[PurchaseOrderResponse]
    total: int
    page: int
    page_size: int
    pages: int
    summary: PurchaseOrderSummaryResponse


class PurchaseOrderItemRequest(BaseModel):
    product_id: UUID
    quantity: int = Field(ge=1)
    unit_cost_cents: int = Field(ge=0)


class CreatePurchaseOrderRequest(BaseModel):
    supplier_id: UUID
    items: list[PurchaseOrderItemRequest] = Field(min_length=1)
    expected_at: date | None = None
    notes: str | None = Field(default=None, max_length=200)


class ReceivePurchaseOrderLineRequest(BaseModel):
    item_id: UUID
    quantity: int = Field(ge=1)


class ReceivePurchaseOrderRequest(BaseModel):
    items: list[ReceivePurchaseOrderLineRequest] = Field(min_length=1)


class ClassTypeResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    is_active: bool
    created_at: datetime


class CreateClassTypeRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=400)


class ClassRoomResponse(BaseModel):
    id: UUID
    name: str
    capacity: int
    is_active: bool
    created_at: datetime


class CreateClassRoomRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    capacity: int = Field(ge=1, le=500)


class InstructorResponse(BaseModel):
    id: UUID
    name: str
    job_title: str


class ClassSessionResponse(BaseModel):
    id: UUID
    title: str
    class_type_id: UUID
    class_type_name: str
    room_id: UUID | None
    room_name: str | None
    instructor_id: UUID | None
    instructor_name: str | None
    starts_at: datetime
    ends_at: datetime
    capacity: int
    status: str
    access_type: str
    extra_price_cents: int
    waitlist_enabled: bool
    cancel_window_hours: int
    notes: str | None
    reserved_count: int
    waitlist_count: int
    spots_left: int
    created_at: datetime
    updated_at: datetime
    cancelled_at: datetime | None


class ClassSessionSummaryResponse(BaseModel):
    total: int
    scheduled: int
    cancelled: int
    upcoming: int
    reserved_total: int
    waitlist_total: int


class ClassSessionDirectoryResponse(BaseModel):
    items: list[ClassSessionResponse]
    total: int
    page: int
    page_size: int
    pages: int
    summary: ClassSessionSummaryResponse


class CreateClassSessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    class_type_id: UUID
    starts_at: datetime
    ends_at: datetime
    capacity: int = Field(ge=1, le=500)
    room_id: UUID | None = None
    instructor_id: UUID | None = None
    access_type: Literal["included", "premium"] = "included"
    extra_price_cents: int = Field(default=0, ge=0)
    waitlist_enabled: bool = True
    cancel_window_hours: int = Field(default=4, ge=0, le=168)
    notes: str | None = Field(default=None, max_length=500)


class UpdateClassSessionRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    capacity: int | None = Field(default=None, ge=1, le=500)
    room_id: UUID | None = None
    instructor_id: UUID | None = None
    access_type: Literal["included", "premium"] | None = None
    extra_price_cents: int | None = Field(default=None, ge=0)
    waitlist_enabled: bool | None = None
    cancel_window_hours: int | None = Field(default=None, ge=0, le=168)
    notes: str | None = Field(default=None, max_length=500)


class ReserveSeatRequest(BaseModel):
    member_id: UUID
    origin: Literal["app", "reception", "web"] = "reception"
    note: str | None = Field(default=None, max_length=200)


class ReservationResponse(BaseModel):
    id: UUID
    session_id: UUID
    member_id: UUID
    member_name: str
    member_email: str | None
    status: str
    origin: str
    waitlist_position: int | None
    late_cancellation: bool
    note: str | None
    created_at: datetime
    cancelled_at: datetime | None
    marked_at: datetime | None


class ClassRosterResponse(BaseModel):
    session: ClassSessionResponse
    reservations: list[ReservationResponse]


class MarkAttendanceRequest(BaseModel):
    attended: bool


class ExerciseResponse(BaseModel):
    id: UUID
    name: str
    muscle_group: str
    category: str
    equipment_name: str | None
    equipment_id: UUID | None
    equipment_status: str | None
    description: str | None
    video_url: str | None
    image_url: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ExerciseDirectoryResponse(BaseModel):
    items: list[ExerciseResponse]
    total: int
    page: int
    page_size: int
    pages: int
    muscle_groups: list[str]
    categories: list[str]


class CreateExerciseRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    muscle_group: str = Field(min_length=1, max_length=60)
    category: str = Field(min_length=1, max_length=60)
    equipment_name: str | None = Field(default=None, max_length=120)
    equipment_id: UUID | None = None
    description: str | None = Field(default=None, max_length=2000)
    video_url: str | None = Field(default=None, max_length=300)
    image_url: str | None = Field(default=None, max_length=300)


class UpdateExerciseRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    muscle_group: str | None = Field(default=None, min_length=1, max_length=60)
    category: str | None = Field(default=None, min_length=1, max_length=60)
    equipment_name: str | None = None
    equipment_id: UUID | None = None
    description: str | None = None
    video_url: str | None = None
    image_url: str | None = None
    is_active: bool | None = None


class RoutineLineRequest(BaseModel):
    exercise_id: UUID
    sets: int = Field(ge=1, le=50)
    reps: str = Field(min_length=1, max_length=20)
    rest_seconds: int | None = Field(default=None, ge=0, le=1800)
    load_note: str | None = Field(default=None, max_length=60)
    notes: str | None = Field(default=None, max_length=200)


class RoutineLineResponse(BaseModel):
    id: UUID
    exercise_id: UUID
    exercise_name: str
    muscle_group: str
    category: str
    equipment_status: str | None
    position: int
    sets: int
    reps: str
    rest_seconds: int | None
    load_note: str | None
    notes: str | None


class RoutineRevisionResponse(BaseModel):
    version: int
    reason: str | None
    item_count: int
    changed_by: UUID | None
    created_at: datetime


class RoutineResponse(BaseModel):
    id: UUID
    name: str
    trainer_id: UUID | None
    trainer_name: str | None
    objective: str | None
    notes: str | None
    status: str
    version: int
    item_count: int
    active_assignments: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class RoutineDetailResponse(BaseModel):
    routine: RoutineResponse
    items: list[RoutineLineResponse]
    revisions: list[RoutineRevisionResponse]


class RoutineSummaryResponse(BaseModel):
    total: int
    active: int
    draft: int
    archived: int


class RoutineDirectoryResponse(BaseModel):
    items: list[RoutineResponse]
    total: int
    page: int
    page_size: int
    pages: int
    summary: RoutineSummaryResponse


class CreateRoutineRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    trainer_id: UUID | None = None
    objective: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    items: list[RoutineLineRequest] = Field(min_length=1)


class UpdateRoutineRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    trainer_id: UUID | None = None
    objective: str | None = None
    notes: str | None = None
    status: Literal["draft", "active", "archived"] | None = None


class ReplaceRoutineItemsRequest(BaseModel):
    items: list[RoutineLineRequest] = Field(min_length=1)
    reason: str | None = Field(default=None, max_length=300)


class AssignmentResponse(BaseModel):
    id: UUID
    routine_id: UUID
    routine_name: str
    routine_version: int
    member_id: UUID
    member_name: str
    member_email: str | None
    trainer_id: UUID | None
    trainer_name: str | None
    start_date: date
    end_date: date | None
    frequency_per_week: int | None
    status: str
    notes: str | None
    workouts_logged: int
    last_workout_at: date | None
    created_at: datetime
    ended_at: datetime | None


class AssignmentDetailResponse(BaseModel):
    assignment: AssignmentResponse
    routine_version: int
    plan: list[RoutineLineResponse]


class AssignmentSummaryResponse(BaseModel):
    total: int
    active: int
    completed: int
    cancelled: int


class AssignmentDirectoryResponse(BaseModel):
    items: list[AssignmentResponse]
    total: int
    page: int
    page_size: int
    pages: int
    summary: AssignmentSummaryResponse


class CreateAssignmentRequest(BaseModel):
    routine_id: UUID
    member_id: UUID
    start_date: date
    end_date: date | None = None
    frequency_per_week: int | None = Field(default=None, ge=1, le=7)
    trainer_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)


class WorkoutSetResponse(BaseModel):
    exercise_id: UUID
    exercise_name: str
    position: int
    set_number: int
    reps: int
    weight_kg: float | None


class WorkoutResponse(BaseModel):
    id: UUID
    assignment_id: UUID
    member_id: UUID
    routine_id: UUID
    routine_version: int
    performed_at: date
    duration_minutes: int | None
    perceived_effort: int | None
    notes: str | None
    status: str
    origin: str
    reviewed_at: datetime | None
    created_at: datetime
    sets: list[WorkoutSetResponse]


class WorkoutSetRequest(BaseModel):
    exercise_id: UUID
    set_number: int = Field(ge=1, le=20)
    reps: int = Field(ge=1, le=100)
    weight_kg: float | None = Field(default=None, ge=0, le=1000)


class LogWorkoutRequest(BaseModel):
    performed_at: date
    duration_minutes: int | None = Field(default=None, ge=0, le=600)
    perceived_effort: int | None = Field(default=None, ge=1, le=10)
    notes: str | None = Field(default=None, max_length=2000)
    sets: list[WorkoutSetRequest] = Field(default_factory=list, max_length=60)


class MeasurementResponse(BaseModel):
    id: UUID
    member_id: UUID
    measured_at: datetime
    weight_kg: float | None
    waist_cm: float | None
    chest_cm: float | None
    body_fat_percent: float | None
    notes: str | None
    origin: str
    created_at: datetime


class RecordMeasurementRequest(BaseModel):
    measured_at: datetime | None = None
    weight_kg: float | None = Field(default=None, gt=0, le=500)
    waist_cm: float | None = Field(default=None, gt=0, le=400)
    chest_cm: float | None = Field(default=None, gt=0, le=400)
    body_fat_percent: float | None = Field(default=None, ge=0, le=100)
    notes: str | None = Field(default=None, max_length=300)


class MemberProgressResponse(BaseModel):
    member_id: UUID
    member_name: str
    active_assignments: int
    workouts_total: int
    workouts_last_30_days: int
    last_workout_at: date | None
    latest_measurement: MeasurementResponse | None
    measurements: list[MeasurementResponse]


class MemberGoalResponse(BaseModel):
    id: UUID
    member_id: UUID
    metric: str
    direction: str
    target_value: float
    baseline_value: float | None
    baseline_measured_at: datetime | None
    target_date: date | None
    notes: str | None
    status: str
    origin: str
    current_value: float | None
    current_measured_at: datetime | None
    progress_percent: int | None
    achieved: bool
    achieved_value: float | None
    achieved_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CreateMemberGoalRequest(BaseModel):
    metric: Literal["weight_kg", "waist_cm", "chest_cm", "body_fat_percent"]
    direction: Literal["decrease", "increase"]
    target_value: float = Field(gt=0, le=1000)
    target_date: date | None = None
    notes: str | None = Field(default=None, max_length=300)


class UpdateMemberGoalRequest(BaseModel):
    target_value: float | None = Field(default=None, gt=0, le=1000)
    target_date: date | None = None
    notes: str | None = Field(default=None, max_length=300)


class ProgressPhotoResponse(BaseModel):
    id: UUID
    member_id: UUID
    angle: str
    captured_at: datetime
    notes: str | None
    content_type: str
    byte_size: int
    origin: str
    created_at: datetime
    # Signed, short-lived path for the member app; the panel streams the file
    # through its own authenticated route instead.
    file_path: str | None = None


class MemberProgressPhotosResponse(BaseModel):
    items: list[ProgressPhotoResponse]
    consent_recorded: bool


class RoutinesOverviewResponse(BaseModel):
    exercises: int
    routines_active: int
    routines_archived: int
    assignments_active: int
    workouts_last_7_days: int


class MemberRoutineAssignmentResponse(BaseModel):
    id: UUID
    routine_id: UUID
    routine_name: str
    routine_version: int
    trainer_name: str | None
    start_date: date
    end_date: date | None
    frequency_per_week: int | None
    status: str
    notes: str | None
    workouts_logged: int
    last_workout_at: date | None
    created_at: datetime
    ended_at: datetime | None


class MemberRoutineListResponse(BaseModel):
    items: list[MemberRoutineAssignmentResponse]
    total: int
    active: int
    completed: int
    cancelled: int


class MemberRoutineDetailResponse(BaseModel):
    assignment: MemberRoutineAssignmentResponse
    objective: str | None
    plan: list[RoutineLineResponse]
    workouts: list[WorkoutResponse]


class MemberPortalProgressResponse(BaseModel):
    workouts_total: int
    workouts_last_30_days: int
    last_workout_at: date | None
    latest_measurement: MeasurementResponse | None
    measurements: list[MeasurementResponse]
    goals: list[MemberGoalResponse]


class MemberPaymentResponse(BaseModel):
    id: UUID
    amount_cents: int
    currency: str
    method: str
    paid_at: datetime
    period_starts_at: datetime | None
    period_ends_at: datetime | None
    plan_name: str | None
    note: str | None


class MemberPaymentPageResponse(BaseModel):
    items: list[MemberPaymentResponse]
    total: int
    page: int
    page_size: int
    pages: int
    total_paid_cents: int


class MemberAccountResponse(BaseModel):
    charges_cents: int
    credits_cents: int
    payments_cents: int
    balance_cents: int
    charges_count: int
    payments_count: int
    last_activity_at: datetime | None
    oldest_charge_at: datetime | None
    as_of: date
    entries: list[MemberAccountEntryResponse]
    entries_total: int


class FiscalDataRequest(BaseModel):
    """CFDI receptor data, shared by the staff and member invoice requests."""

    rfc: str = Field(min_length=12, max_length=13)
    legal_name: str = Field(min_length=2, max_length=254)
    tax_regime: str = Field(min_length=3, max_length=3)
    postal_code: str = Field(min_length=5, max_length=5)
    cfdi_use: str = Field(default="G03", min_length=3, max_length=3)
    email: EmailStr | None = None


class MemberFiscalProfileResponse(BaseModel):
    member_id: UUID
    rfc: str
    legal_name: str
    tax_regime: str
    postal_code: str
    cfdi_use: str
    email: str | None
    updated_at: datetime


class MemberFiscalProfileEnvelopeResponse(BaseModel):
    profile: MemberFiscalProfileResponse | None


class MemberInvoiceResponse(BaseModel):
    id: UUID
    series: str
    folio: int
    folio_label: str
    status: str
    origin_type: str
    origin_reference: str
    currency: str
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    payment_form: str
    payment_method: str
    uuid: str | None
    is_simulated: bool
    issued_at: datetime | None
    stamped_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    pdf_path: str | None
    xml_path: str | None


class MemberInvoicePageResponse(BaseModel):
    items: list[MemberInvoiceResponse]
    total: int
    page: int
    page_size: int
    pages: int


class MemberBillableOriginResponse(BaseModel):
    origin_type: str
    origin_id: UUID
    reference: str
    occurred_at: datetime
    total_cents: int
    description: str
    payment_method: str


class MemberBillableOriginPageResponse(BaseModel):
    items: list[MemberBillableOriginResponse]
    total: int
    page: int
    page_size: int
    pages: int


class MemberInvoiceCreateRequest(BaseModel):
    origin_type: Literal["sale", "membership_payment"]
    origin_id: UUID
    idempotency_key: str = Field(min_length=1, max_length=128)
    payment_form: str | None = Field(default=None, min_length=2, max_length=2)
    payment_method: Literal["PUE", "PPD"] | None = None
    receptor: FiscalDataRequest


class MemberInvoiceRequestResponse(BaseModel):
    invoice: MemberInvoiceResponse
    idempotent_replay: bool


class MemberNotificationResponse(BaseModel):
    id: UUID
    kind: str
    title: str
    body: str
    ref_id: UUID | None
    created_at: datetime
    read_at: datetime | None


class MemberNotificationPageResponse(BaseModel):
    items: list[MemberNotificationResponse]
    total: int
    page: int
    page_size: int
    pages: int
    unread_total: int


class MemberNotificationCountResponse(BaseModel):
    unread: int


class MemberNotificationReadAllResponse(BaseModel):
    updated: int


class StaffNotificationResponse(BaseModel):
    id: UUID
    kind: str
    title: str
    body: str
    ref_id: UUID | None
    created_at: datetime
    read_at: datetime | None


class StaffNotificationPageResponse(BaseModel):
    items: list[StaffNotificationResponse]
    total: int
    page: int
    page_size: int
    pages: int
    unread_total: int


class StaffNotificationCountResponse(BaseModel):
    unread: int


class StaffNotificationReadAllResponse(BaseModel):
    updated: int


class EquipmentResponse(BaseModel):
    id: UUID
    name: str
    category: str
    brand: str | None
    model: str | None
    serial_number: str | None
    location: str | None
    acquired_on: date | None
    useful_life_months: int | None
    purchase_cost_cents: int
    status: str
    next_preventive_due: date | None
    notes: str | None
    retired_at: datetime | None
    open_tickets: int
    last_maintenance_at: datetime | None
    created_at: datetime
    updated_at: datetime


class EquipmentChoiceResponse(BaseModel):
    id: UUID
    name: str
    location: str | None
    status: str


class EquipmentSummaryResponse(BaseModel):
    total: int
    operational: int
    maintenance: int
    out_of_service: int
    inspection: int
    retired: int


class EquipmentDirectoryResponse(BaseModel):
    items: list[EquipmentResponse]
    total: int
    page: int
    page_size: int
    pages: int
    summary: EquipmentSummaryResponse
    categories: list[str]
    locations: list[str]


class LinkedExerciseResponse(BaseModel):
    id: UUID
    name: str
    muscle_group: str


class TicketResponse(BaseModel):
    id: UUID
    code: str
    equipment_id: UUID
    equipment_name: str
    equipment_status: str
    kind: str
    severity: str
    title: str
    description: str | None
    status: str
    reported_by: UUID | None
    reporter_email: str | None
    reported_at: datetime
    assigned_to: UUID | None
    assignee_name: str | None
    assigned_at: datetime | None
    scheduled_for: date | None
    started_at: datetime | None
    resolved_at: datetime | None
    resolution_notes: str | None
    cost_cents: int
    blocked_equipment: bool
    created_at: datetime
    updated_at: datetime


class TicketSummaryResponse(BaseModel):
    total: int
    open: int
    assigned: int
    in_progress: int
    resolved: int
    cancelled: int
    critical_open: int


class TicketDirectoryResponse(BaseModel):
    items: list[TicketResponse]
    total: int
    page: int
    page_size: int
    pages: int
    summary: TicketSummaryResponse


class MaintenanceRecordResponse(BaseModel):
    id: UUID
    equipment_id: UUID
    equipment_name: str
    ticket_id: UUID | None
    kind: str
    summary: str
    notes: str | None
    performed_at: datetime
    cost_cents: int
    technician_id: UUID | None
    technician_name: str | None
    created_at: datetime


class MaintenanceRecordDirectoryResponse(BaseModel):
    items: list[MaintenanceRecordResponse]
    total: int
    page: int
    page_size: int
    pages: int
    total_cost_cents: int


class TicketDetailResponse(BaseModel):
    ticket: TicketResponse
    record: MaintenanceRecordResponse | None


class EquipmentDetailResponse(BaseModel):
    equipment: EquipmentResponse
    tickets: list[TicketResponse]
    records: list[MaintenanceRecordResponse]
    exercises: list[LinkedExerciseResponse]


class ChecklistResponse(BaseModel):
    id: UUID
    area: str
    result: str
    observations: str | None
    performed_at: datetime
    performed_by: UUID | None
    performer_email: str | None
    created_at: datetime


class ChecklistDirectoryResponse(BaseModel):
    items: list[ChecklistResponse]
    total: int
    page: int
    page_size: int
    pages: int


class AreaServiceStatusResponse(BaseModel):
    area: str
    total: int
    operational: int
    maintenance: int
    out_of_service: int
    inspection: int
    retired: int
    availability: str


class MaintenanceOverviewResponse(BaseModel):
    equipment_total: int
    operational: int
    maintenance: int
    out_of_service: int
    tickets_open: int
    tickets_critical: int
    preventives_due: int
    records_last_30_days: int


class CreateEquipmentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    category: str = Field(min_length=1, max_length=60)
    brand: str | None = Field(default=None, max_length=80)
    model: str | None = Field(default=None, max_length=80)
    serial_number: str | None = Field(default=None, max_length=80)
    location: str | None = Field(default=None, max_length=80)
    acquired_on: date | None = None
    useful_life_months: int | None = Field(default=None, ge=1, le=1200)
    purchase_cost_cents: int = Field(default=0, ge=0)
    notes: str | None = Field(default=None, max_length=2000)
    next_preventive_due: date | None = None


class UpdateEquipmentRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    category: str | None = Field(default=None, min_length=1, max_length=60)
    brand: str | None = None
    model: str | None = None
    serial_number: str | None = None
    location: str | None = None
    acquired_on: date | None = None
    useful_life_months: int | None = Field(default=None, ge=1, le=1200)
    purchase_cost_cents: int | None = Field(default=None, ge=0)
    notes: str | None = None
    next_preventive_due: date | None = None


class SetEquipmentStatusRequest(BaseModel):
    status: Literal["operational", "maintenance", "out_of_service", "inspection"]


class CreateTicketRequest(BaseModel):
    equipment_id: UUID
    title: str = Field(min_length=1, max_length=160)
    kind: Literal["corrective", "preventive"] = "corrective"
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    description: str | None = Field(default=None, max_length=2000)
    assigned_to: UUID | None = None
    scheduled_for: date | None = None
    block_equipment: bool | None = None


class UpdateTicketRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    kind: Literal["corrective", "preventive"] | None = None
    severity: Literal["low", "medium", "high", "critical"] | None = None
    assigned_to: UUID | None = None
    scheduled_for: date | None = None
    cost_cents: int | None = Field(default=None, ge=0)


class ResolveTicketRequest(BaseModel):
    resolution_notes: str = Field(min_length=1, max_length=2000)
    cost_cents: int | None = Field(default=None, ge=0)
    next_due_on: date | None = None
    technician_id: UUID | None = None
    performed_at: datetime | None = None


class CancelTicketRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class RecordMaintenanceRequest(BaseModel):
    kind: Literal["preventive", "corrective", "inspection", "cleaning", "calibration"]
    summary: str = Field(min_length=1, max_length=200)
    performed_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)
    cost_cents: int = Field(default=0, ge=0)
    technician_id: UUID | None = None
    next_due_on: date | None = None
    ticket_id: UUID | None = None


class RecordChecklistRequest(BaseModel):
    area: str = Field(min_length=1, max_length=80)
    result: Literal["ok", "observation", "pending"]
    observations: str | None = Field(default=None, max_length=2000)
    performed_at: datetime | None = None


# Reportes (analítica de solo lectura sobre los datos ya registrados).


class ReportPeriodResponse(BaseModel):
    date_from: date
    date_to: date
    days: int
    timezone: str


class ReportCountRowResponse(BaseModel):
    label: str
    count: int


class ReportAmountRowResponse(BaseModel):
    label: str
    count: int
    amount_cents: int


class ReportRevenueDayResponse(BaseModel):
    day: date
    pos_cents: int
    membership_cents: int
    total_cents: int
    sales_count: int
    refunds_cents: int


class ReportAccessDayResponse(BaseModel):
    day: date
    total: int
    denied: int


class ReportClassDayResponse(BaseModel):
    day: date
    sessions: int
    attended: int


class ReportEventDayResponse(BaseModel):
    day: date
    activations: int
    terminations: int


class ReportPlanRowResponse(BaseModel):
    plan_id: UUID
    name: str
    price_cents: int
    duration_days: int
    active_count: int
    monthly_cents: int
    recurring: bool


class ReportProductRowResponse(BaseModel):
    product_id: UUID
    name: str
    sku: str
    quantity: int
    amount_cents: int


class ReportEquipmentRowResponse(BaseModel):
    equipment_id: UUID
    name: str
    category: str
    location: str | None
    status: str
    records_count: int
    cost_cents: int
    open_tickets: int


class ReportMovementRowResponse(BaseModel):
    label: str
    movements: int
    units: int


class ReportInventoryProductRowResponse(BaseModel):
    product_id: UUID
    name: str
    sku: str
    category: str
    quantity: int
    cost_cents: int
    price_cents: int
    cost_value_cents: int
    retail_value_cents: int


class ReportOverviewResponse(BaseModel):
    period: ReportPeriodResponse
    pos_cents: int
    pos_gross_cents: int
    refunds_cents: int
    refunds_count: int
    membership_cents: int
    sales_count: int
    average_ticket_cents: int
    payments_count: int
    mrr_expected_cents: int
    maintenance_cost_cents: int
    maintenance_records: int
    access_total: int
    access_denied: int
    access_manual: int
    class_sessions: int
    class_capacity: int
    class_attended: int
    class_no_show: int
    class_occupancy_percent: int
    workouts: int
    measurements: int
    members_by_status: list[ReportCountRowResponse]
    memberships_by_status: list[ReportCountRowResponse]
    new_members: int
    members_expiring: int
    equipment_by_status: list[ReportCountRowResponse]
    equipment_total: int
    tickets_open: int
    tickets_critical: int
    revenue_by_day: list[ReportRevenueDayResponse]
    access_by_day: list[ReportAccessDayResponse]


class ReportPpdAgingResponse(BaseModel):
    current_cents: int
    days_31_60_cents: int
    days_61_90_cents: int
    over_90_cents: int


class ReportPpdReceivablesResponse(BaseModel):
    as_of: date
    invoices: int
    total_cents: int
    paid_cents: int
    outstanding_cents: int
    aging: ReportPpdAgingResponse
    oldest_stamped_at: datetime | None
    stamped_complements: int
    stamped_complement_cents: int
    requested_complements: int
    requested_complement_cents: int
    failed_complements: int
    failed_complement_cents: int


class RevenueReportResponse(BaseModel):
    period: ReportPeriodResponse
    pos_cents: int
    pos_gross_cents: int
    refunds_cents: int
    refunds_count: int
    membership_cents: int
    sales_count: int
    average_ticket_cents: int
    payments_count: int
    by_day: list[ReportRevenueDayResponse]
    pos_by_method: list[ReportAmountRowResponse]
    membership_by_method: list[ReportAmountRowResponse]
    by_category: list[ReportAmountRowResponse]
    top_products: list[ReportProductRowResponse]
    cash_sessions_opened: int
    cash_sessions_closed: int
    cash_difference_cents: int
    ppd_receivables: ReportPpdReceivablesResponse


class MembershipReportResponse(BaseModel):
    period: ReportPeriodResponse
    members_total: int
    members_by_status: list[ReportCountRowResponse]
    memberships_by_status: list[ReportCountRowResponse]
    by_plan: list[ReportPlanRowResponse]
    mrr_expected_cents: int
    payments_cents: int
    payments_count: int
    events: list[ReportCountRowResponse]
    events_by_day: list[ReportEventDayResponse]
    new_members: int
    members_expiring: int


class OperationsReportResponse(BaseModel):
    period: ReportPeriodResponse
    access_total: int
    access_authorized: int
    access_denied: int
    access_manual: int
    access_by_day: list[ReportAccessDayResponse]
    access_by_hour: list[ReportCountRowResponse]
    class_sessions: int
    class_capacity: int
    class_reserved: int
    class_attended: int
    class_no_show: int
    class_waitlist: int
    class_cancelled: int
    class_occupancy_percent: int
    classes_by_day: list[ReportClassDayResponse]
    workouts: int
    workout_minutes: int
    measurements: int
    workouts_by_day: list[ReportCountRowResponse]


class MaintenanceReportResponse(BaseModel):
    period: ReportPeriodResponse
    cost_cents: int
    records_count: int
    by_kind: list[ReportAmountRowResponse]
    by_equipment: list[ReportEquipmentRowResponse]
    tickets_created: int
    tickets_by_status: list[ReportCountRowResponse]
    tickets_by_severity: list[ReportCountRowResponse]
    equipment_by_status: list[ReportCountRowResponse]
    preventives_due: int


class InventoryReportResponse(BaseModel):
    period: ReportPeriodResponse
    products_total: int
    products_active: int
    products_inactive: int
    stock_units: int
    stock_value_cents: int
    retail_value_cents: int
    low_stock: int
    out_of_stock: int
    by_category: list[ReportAmountRowResponse]
    by_product: list[ReportInventoryProductRowResponse]
    suppliers_total: int
    suppliers_active: int
    open_orders: int
    open_orders_value_cents: int
    movements_count: int
    movements_by_type: list[ReportMovementRowResponse]
    units_in: int
    units_out: int
    orders_created: int
    orders_by_status: list[ReportCountRowResponse]
    orders_value_cents: int
    orders_received: int
    orders_received_value_cents: int
    by_supplier: list[ReportAmountRowResponse]


class MemberResponse(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    status: str
    membership_status: str | None
    plan_name: str | None
    membership_starts_at: datetime | None
    membership_ends_at: datetime | None
    auto_renew: bool | None


class MemberSummaryResponse(BaseModel):
    active: int
    expiring_soon: int
    frozen: int
    pending: int


class MemberPlanOptionResponse(BaseModel):
    id: UUID
    name: str


class MemberDirectoryResponse(BaseModel):
    items: list[MemberResponse]
    total: int
    page: int
    page_size: int
    pages: int
    summary: MemberSummaryResponse
    plans: list[MemberPlanOptionResponse]


class CreateMemberRequest(BaseModel):
    first_name: str
    last_name: str
    email: str | None = None
    phone: str | None = None
    privacy_notice_accepted: bool = False


class CreatedMemberResponse(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    status: str
    consent_recorded: bool


class UpdateMemberRequest(BaseModel):
    first_name: str
    last_name: str
    email: str | None = None
    phone: str | None = None


class MemberContactResponse(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    status: str


class PlanResponse(BaseModel):
    id: UUID
    name: str
    duration_days: int
    price_cents: int
    currency: str


class AssignPlanRequest(BaseModel):
    plan_id: UUID
    auto_renew: bool = False
    note: str | None = None


class CancelMembershipRequest(BaseModel):
    reason: str


class MembershipStateResponse(BaseModel):
    membership_id: UUID
    member_id: UUID
    plan_id: UUID
    plan_name: str
    status: str
    starts_at: datetime
    ends_at: datetime
    auto_renew: bool
    previous_status: str | None
    plan_changed: bool


class CollectMembershipPaymentRequest(BaseModel):
    plan_id: UUID | None = None
    payment_method: Literal["cash", "card", "transfer"]
    idempotency_key: str = Field(min_length=8, max_length=128)
    note: str | None = Field(default=None, max_length=200)
    auto_renew: bool | None = None


class MembershipPaymentResponse(BaseModel):
    payment_id: UUID
    payment_attempt_id: UUID
    membership_id: UUID
    member_id: UUID
    plan_id: UUID
    plan_name: str
    amount_cents: int
    currency: str
    method: str
    paid_at: datetime
    cash_session_id: UUID
    period_starts_at: datetime
    period_ends_at: datetime
    membership_status: str
    auto_renew: bool
    renewed: bool
    idempotent_replay: bool


class AccessEventResponse(BaseModel):
    id: UUID
    event_id: UUID
    member_id: UUID | None
    member_name: str | None
    member_email: str | None
    plan_name: str | None
    reader_id: str
    direction: str
    authorized: bool
    reason: str
    note: str | None
    source: str
    occurred_at: datetime
    offline: bool


class AccessEventSummaryResponse(BaseModel):
    total: int
    authorized: int
    denied: int
    manual: int


class AccessEventDirectoryResponse(BaseModel):
    items: list[AccessEventResponse]
    total: int
    page: int
    page_size: int
    pages: int
    summary: AccessEventSummaryResponse


class ManualAccessRequest(BaseModel):
    member_id: UUID
    note: str | None = Field(default=None, max_length=200)
    reader_id: str = Field(default="Recepción", min_length=1, max_length=80)


class DashboardMembersResponse(BaseModel):
    total: int
    active: int
    expiring_soon: int
    frozen: int
    pending: int


class DashboardAccessResponse(BaseModel):
    entries_today: int
    denied_today: int


class DashboardResponse(BaseModel):
    as_of: datetime
    members: DashboardMembersResponse
    access: DashboardAccessResponse


class BootstrapOwnerRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=1024)


def get_session():
    if engine is None:
        raise HTTPException(status_code=503, detail="DATABASE_URL is not configured")
    with Session(engine) as session:
        yield session


SessionDependency = Annotated[Session, Depends(get_session)]
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: SessionDependency,
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return authenticate_session(session, credentials.credentials)
    except InvalidSession as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error


def require_api_permission(permission_code: str):
    def dependency(principal: Annotated[AuthenticatedUser, Depends(get_current_principal)]) -> AuthenticatedUser:
        try:
            return require_permission(principal, permission_code)
        except PermissionDenied as error:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions") from error

    return dependency


def get_current_member(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: SessionDependency,
) -> AuthenticatedMember:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return authenticate_member_session(session, credentials.credentials)
    except InvalidMemberSession as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired member session",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error


@asynccontextmanager
async def lifespan(_: FastAPI):
    if PREVIEW_MODE:
        if engine is None or not DATABASE_URL or not DATABASE_URL.startswith("sqlite"):
            raise RuntimeError("Preview mode requires a SQLite DATABASE_URL")
        SQLModel.metadata.create_all(engine)
        with Session(engine) as preview_session:
            ensure_default_access_control(preview_session)
    yield


app = FastAPI(
    title="Gym Manager API",
    version="0.1.0",
    description=(
        "API preview for the membership and first-payment slice. "
        "Payment outcomes are simulated and no real gateway is contacted."
    ),
    lifespan=lifespan,
)

# Bearer-only clients (the member app) do not rely on cookies, so credentials
# stay disabled and every origin must be listed explicitly in CORS_ORIGINS.
if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(CORS_ORIGINS),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )


@app.get("/health", tags=["system"])
def health() -> dict[str, str | bool]:
    return {"status": "ok", "preview_mode": PREVIEW_MODE}


@app.post("/auth/login", response_model=LoginResponse, tags=["authentication"])
def login(request: LoginRequest, session: SessionDependency) -> LoginResponse:
    try:
        result = authenticate_user(session, email=request.email, password=request.password)
    except AuthenticationFailed as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    return LoginResponse(
        access_token=result.access_token,
        token_type=result.token_type,
        expires_at=result.expires_at,
        user=_principal_response(result.user),
    )


@app.get("/auth/me", response_model=UserResponse, tags=["authentication"])
def auth_me(principal: Annotated[AuthenticatedUser, Depends(get_current_principal)]) -> UserResponse:
    return _principal_response(principal)


@app.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, tags=["authentication"])
def logout(
    principal: Annotated[AuthenticatedUser, Depends(get_current_principal)],
    session: SessionDependency,
) -> None:
    revoke_session(session, principal)


@app.post(
    "/member/auth/request-code",
    response_model=MemberCodeRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["member authentication"],
)
def request_member_code(request: MemberCodeRequest, session: SessionDependency) -> MemberCodeRequestResponse:
    try:
        result = request_login_code(session, email=request.email)
    except MemberAuthUnavailable as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except MemberDeliveryFailed as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo enviar el código de acceso. Intenta de nuevo.",
        ) from error
    return MemberCodeRequestResponse(expires_in=result.expires_in, preview_code=result.preview_code)


@app.post(
    "/member/auth/verify",
    response_model=MemberAuthResponse,
    tags=["member authentication"],
)
def verify_member_code(request: MemberVerifyRequest, session: SessionDependency) -> MemberAuthResponse:
    try:
        result = verify_login_code(session, email=request.email, code=request.code)
    except InvalidMemberCode as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Código inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    except MemberAuthUnavailable as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    return MemberAuthResponse(
        access_token=result.access_token,
        token_type=result.token_type,
        expires_at=result.expires_at,
        member=_member_summary_response(result.member),
    )


@app.get("/member/me", response_model=MemberPortalProfileResponse, tags=["member self-service"])
def member_me(
    member: Annotated[AuthenticatedMember, Depends(get_current_member)],
    session: SessionDependency,
) -> MemberPortalProfileResponse:
    try:
        profile = member_profile(session, member.member_id)
    except MemberPortalError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return _member_profile_response(profile)


@app.post(
    "/member/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["member authentication"],
)
def member_logout(
    member: Annotated[AuthenticatedMember, Depends(get_current_member)],
    session: SessionDependency,
) -> None:
    revoke_member_session(session, member)


@app.get(
    "/member/classes",
    response_model=MemberClassDirectoryResponse,
    tags=["member self-service"],
)
def member_classes(
    member: Annotated[AuthenticatedMember, Depends(get_current_member)],
    session: SessionDependency,
    days: Annotated[int, Query(ge=1, le=60)] = 14,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 25,
) -> MemberClassDirectoryResponse:
    try:
        directory = list_member_classes(
            session,
            member.member_id,
            days=days,
            page=page,
            page_size=page_size,
        )
    except MemberPortalError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ClassesError as error:
        raise _classes_http_error(error) from error
    return MemberClassDirectoryResponse(
        items=[_member_class_response(item) for item in directory.items],
        total=directory.total,
        page=directory.page,
        page_size=directory.page_size,
        pages=directory.pages,
    )


@app.post(
    "/member/classes/sessions/{session_id}/reservations",
    response_model=MemberClassReservationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["member self-service"],
)
def reserve_member_class_endpoint(
    session_id: UUID,
    member: Annotated[AuthenticatedMember, Depends(get_current_member)],
    session: SessionDependency,
) -> MemberClassReservationResponse:
    try:
        reservation = reserve_member_class(session, member.member_id, session_id)
    except MemberPortalError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ClassesError as error:
        raise _classes_http_error(error) from error
    return _member_reservation_response(reservation)


@app.post(
    "/member/classes/reservations/{reservation_id}/cancel",
    response_model=MemberClassReservationResponse,
    tags=["member self-service"],
)
def cancel_member_reservation_endpoint(
    reservation_id: UUID,
    member: Annotated[AuthenticatedMember, Depends(get_current_member)],
    session: SessionDependency,
) -> MemberClassReservationResponse:
    try:
        reservation = cancel_member_reservation(session, member.member_id, reservation_id)
    except MemberPortalError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ClassesError as error:
        raise _classes_http_error(error) from error
    return _member_reservation_response(reservation)


@app.get(
    "/member/routines",
    response_model=MemberRoutineListResponse,
    tags=["member self-service"],
)
def member_routines(
    member: Annotated[AuthenticatedMember, Depends(get_current_member)],
    session: SessionDependency,
) -> MemberRoutineListResponse:
    try:
        directory = list_member_routines(session, member.member_id)
    except MemberPortalError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return MemberRoutineListResponse(
        items=[_member_assignment_response(item) for item in directory.items],
        total=directory.total,
        active=directory.active,
        completed=directory.completed,
        cancelled=directory.cancelled,
    )


@app.get(
    "/member/routines/{assignment_id}",
    response_model=MemberRoutineDetailResponse,
    tags=["member self-service"],
)
def member_routine_detail(
    assignment_id: UUID,
    member: Annotated[AuthenticatedMember, Depends(get_current_member)],
    session: SessionDependency,
) -> MemberRoutineDetailResponse:
    try:
        detail = get_member_routine(session, member.member_id, assignment_id)
    except MemberPortalError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return MemberRoutineDetailResponse(
        assignment=_member_assignment_response(detail.assignment),
        objective=detail.objective,
        plan=[_routine_line_response(item) for item in detail.plan],
        workouts=[_workout_response(item) for item in detail.workouts],
    )


@app.get(
    "/member/progress",
    response_model=MemberPortalProgressResponse,
    tags=["member self-service"],
)
def member_progress_endpoint(
    member: Annotated[AuthenticatedMember, Depends(get_current_member)],
    session: SessionDependency,
) -> MemberPortalProgressResponse:
    try:
        progress = get_member_progress(session, member.member_id)
    except MemberPortalError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return _member_progress_response(progress)


@app.post(
    "/member/routines/{assignment_id}/workouts",
    response_model=WorkoutResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["member self-service"],
)
def member_log_workout(
    assignment_id: UUID,
    request: LogWorkoutRequest,
    member: Annotated[AuthenticatedMember, Depends(get_current_member)],
    session: SessionDependency,
) -> WorkoutResponse:
    try:
        item = log_member_workout(
            session,
            member.member_id,
            assignment_id,
            performed_at=request.performed_at,
            duration_minutes=request.duration_minutes,
            perceived_effort=request.perceived_effort,
            notes=request.notes,
            sets=_workout_set_inputs(request.sets),
        )
    except MemberPortalError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return _workout_response(item)


@app.post(
    "/member/progress/measurements",
    response_model=MeasurementResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["member self-service"],
)
def member_record_measurement(
    request: RecordMeasurementRequest,
    member: Annotated[AuthenticatedMember, Depends(get_current_member)],
    session: SessionDependency,
) -> MeasurementResponse:
    try:
        item = record_member_measurement(
            session,
            member.member_id,
            measured_at=request.measured_at,
            weight_kg=request.weight_kg,
            waist_cm=request.waist_cm,
            chest_cm=request.chest_cm,
            body_fat_percent=request.body_fat_percent,
            notes=request.notes,
        )
    except MemberPortalError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return _measurement_response(item)


@app.post(
    "/member/progress/goals",
    response_model=MemberGoalResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["member self-service"],
)
def member_create_goal(
    request: CreateMemberGoalRequest,
    member: Annotated[AuthenticatedMember, Depends(get_current_member)],
    session: SessionDependency,
) -> MemberGoalResponse:
    try:
        item = create_member_goal_from_app(
            session,
            member.member_id,
            metric=request.metric,
            direction=request.direction,
            target_value=request.target_value,
            target_date=request.target_date,
            notes=request.notes,
        )
    except MemberPortalError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return _goal_response(item)


@app.post(
    "/member/progress/goals/{goal_id}/cancel",
    response_model=MemberGoalResponse,
    tags=["member self-service"],
)
def member_cancel_goal(
    goal_id: UUID,
    member: Annotated[AuthenticatedMember, Depends(get_current_member)],
    session: SessionDependency,
) -> MemberGoalResponse:
    try:
        item = cancel_member_goal_from_app(session, member.member_id, goal_id)
    except MemberPortalError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return _goal_response(item)


@app.get(
    "/member/progress/photos",
    response_model=MemberProgressPhotosResponse,
    tags=["member self-service"],
)
def member_progress_photos(
    member: Annotated[AuthenticatedMember, Depends(get_current_member)],
    session: SessionDependency,
) -> MemberProgressPhotosResponse:
    try:
        photos = list_member_progress_photos(session, member.member_id)
    except MemberPortalError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return _member_progress_photos_response(photos)


@app.post(
    "/member/progress/photos",
    response_model=ProgressPhotoResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["member self-service"],
)
async def member_upload_progress_photo(
    member: Annotated[AuthenticatedMember, Depends(get_current_member)],
    session: SessionDependency,
    photo: Annotated[UploadFile, File(description="Imagen JPEG, PNG o WebP de hasta 8 MB")],
    angle: Annotated[str, Form()],
    captured_at: Annotated[datetime | None, Form()] = None,
    notes: Annotated[str | None, Form()] = None,
    consent: Annotated[bool, Form()] = False,
) -> ProgressPhotoResponse:
    content_type = photo.content_type
    data = await photo.read(MAX_PROGRESS_PHOTO_BYTES + 1)
    await photo.close()
    try:
        item = record_member_progress_photo(
            session,
            member.member_id,
            data=data,
            content_type=content_type,
            angle=angle,
            captured_at=captured_at,
            notes=notes,
            consent=consent,
        )
    except ProgressPhotoConsentRequired as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    except MemberPortalError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return _progress_photo_response(
        item, file_path=progress_photo_link(item.id)
    )


@app.get("/member/progress/photos/{photo_id}/file", tags=["member self-service"])
def member_progress_photo_file_endpoint(
    photo_id: UUID,
    session: SessionDependency,
    exp: Annotated[int, Query(ge=0)],
    sig: Annotated[str, Query(min_length=64, max_length=64)],
) -> FileResponse:
    try:
        verify_progress_photo_link(photo_id, exp, sig)
    except InvalidProgressPhotoLink as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(error)
        ) from error
    try:
        stored = progress_photo_file(session, photo_id)
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    filename = (
        f"foto-progreso-{stored.photo.captured_at.date().isoformat()}-"
        f"{stored.photo.angle}{stored.path.suffix}"
    )
    return FileResponse(
        stored.path,
        media_type=stored.photo.content_type,
        filename=filename,
        content_disposition_type="inline",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.delete(
    "/member/progress/photos/{photo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["member self-service"],
)
def member_delete_progress_photo(
    photo_id: UUID,
    member: Annotated[AuthenticatedMember, Depends(get_current_member)],
    session: SessionDependency,
) -> Response:
    try:
        delete_member_progress_photo(session, member.member_id, photo_id)
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get(
    "/member/payments",
    response_model=MemberPaymentPageResponse,
    tags=["member self-service"],
)
def member_payments(
    member: Annotated[AuthenticatedMember, Depends(get_current_member)],
    session: SessionDependency,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> MemberPaymentPageResponse:
    try:
        history = list_member_payments(
            session, member.member_id, page=page, page_size=page_size
        )
    except MemberPortalError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return MemberPaymentPageResponse(
        items=[_member_payment_response(item) for item in history.items],
        total=history.total,
        page=history.page,
        page_size=history.page_size,
        pages=history.pages,
        total_paid_cents=history.total_paid_cents,
    )


@app.get(
    "/member/account",
    response_model=MemberAccountResponse,
    tags=["member self-service"],
)
def member_account(
    member: Annotated[AuthenticatedMember, Depends(get_current_member)],
    session: SessionDependency,
) -> MemberAccountResponse:
    try:
        account = get_member_account(session, member.member_id)
    except MemberPortalError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return MemberAccountResponse(
        charges_cents=account.charges_cents,
        credits_cents=account.credits_cents,
        payments_cents=account.payments_cents,
        balance_cents=account.balance_cents,
        charges_count=account.charges_count,
        payments_count=account.payments_count,
        last_activity_at=account.last_activity_at,
        oldest_charge_at=account.oldest_charge_at,
        as_of=account.as_of,
        entries=[_member_account_entry_response(entry) for entry in account.entries],
        entries_total=account.entries_total,
    )


@app.get(
    "/member/invoices",
    response_model=MemberInvoicePageResponse,
    tags=["member self-service"],
)
def member_invoices(
    member: Annotated[AuthenticatedMember, Depends(get_current_member)],
    session: SessionDependency,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> MemberInvoicePageResponse:
    try:
        listing = list_member_invoices(
            session, member.member_id, page=page, page_size=page_size
        )
    except MemberPortalError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    return MemberInvoicePageResponse(
        items=[_member_invoice_response(item) for item in listing.items],
        total=listing.total,
        page=listing.page,
        page_size=listing.page_size,
        pages=listing.pages,
    )


@app.get(
    "/member/invoices/origins",
    response_model=MemberBillableOriginPageResponse,
    tags=["member self-service"],
)
def member_billable_origins(
    member: Annotated[AuthenticatedMember, Depends(get_current_member)],
    session: SessionDependency,
    origin_type: Annotated[
        Literal["sale", "membership_payment"] | None, Query()
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> MemberBillableOriginPageResponse:
    try:
        listing = list_billable_origins(
            session,
            member.member_id,
            origin_type=origin_type,
            page=page,
            page_size=page_size,
        )
    except MemberPortalError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    return MemberBillableOriginPageResponse(
        items=[_member_billable_origin_response(item) for item in listing.items],
        total=listing.total,
        page=listing.page,
        page_size=listing.page_size,
        pages=listing.pages,
    )


@app.get(
    "/member/fiscal-profile",
    response_model=MemberFiscalProfileEnvelopeResponse,
    tags=["member self-service"],
)
def member_fiscal_profile_detail(
    member: Annotated[AuthenticatedMember, Depends(get_current_member)],
    session: SessionDependency,
) -> MemberFiscalProfileEnvelopeResponse:
    try:
        profile = member_fiscal_profile(session, member.member_id)
    except MemberPortalError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    return MemberFiscalProfileEnvelopeResponse(
        profile=(
            _member_fiscal_profile_response(profile) if profile is not None else None
        )
    )


@app.post(
    "/member/invoices",
    response_model=MemberInvoiceRequestResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["member self-service"],
)
def member_request_invoice(
    payload: MemberInvoiceCreateRequest,
    member: Annotated[AuthenticatedMember, Depends(get_current_member)],
    session: SessionDependency,
) -> MemberInvoiceRequestResponse:
    receptor = payload.receptor
    try:
        invoice, created = request_member_invoice(
            session,
            member.member_id,
            origin_type=payload.origin_type,
            origin_id=payload.origin_id,
            rfc=receptor.rfc,
            legal_name=receptor.legal_name,
            tax_regime=receptor.tax_regime,
            postal_code=receptor.postal_code,
            cfdi_use=receptor.cfdi_use,
            email=str(receptor.email) if receptor.email is not None else None,
            payment_form=payload.payment_form,
            payment_method=payload.payment_method,
            idempotency_key=payload.idempotency_key,
        )
    except MemberPortalError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    except CfdiError as error:
        _raise_cfdi_error(error)
    return MemberInvoiceRequestResponse(
        invoice=_member_invoice_response(invoice),
        idempotent_replay=not created,
    )


@app.get("/member/invoices/{invoice_id}/pdf", tags=["member self-service"])
def member_invoice_pdf(
    invoice_id: UUID,
    session: SessionDependency,
    exp: Annotated[int, Query(ge=0)],
    sig: Annotated[str, Query(min_length=64, max_length=64)],
) -> Response:
    try:
        verify_download_link(invoice_id, "pdf", exp, sig)
    except InvalidDownloadLink as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(error)
        ) from error
    try:
        filename, content = download_member_invoice(session, invoice_id, "pdf")
    except CfdiError as error:
        _raise_cfdi_error(error)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@app.get("/member/invoices/{invoice_id}/xml", tags=["member self-service"])
def member_invoice_xml(
    invoice_id: UUID,
    session: SessionDependency,
    exp: Annotated[int, Query(ge=0)],
    sig: Annotated[str, Query(min_length=64, max_length=64)],
) -> Response:
    try:
        verify_download_link(invoice_id, "xml", exp, sig)
    except InvalidDownloadLink as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(error)
        ) from error
    try:
        filename, content = download_member_invoice(session, invoice_id, "xml")
    except CfdiError as error:
        _raise_cfdi_error(error)
    return Response(
        content=content,
        media_type="application/xml; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@app.get(
    "/member/notifications",
    response_model=MemberNotificationPageResponse,
    tags=["member self-service"],
)
def member_notifications(
    member: Annotated[AuthenticatedMember, Depends(get_current_member)],
    session: SessionDependency,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> MemberNotificationPageResponse:
    try:
        inbox = list_member_notifications(
            session, member.member_id, page=page, page_size=page_size
        )
    except NotificationError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return MemberNotificationPageResponse(
        items=[_member_notification_response(item) for item in inbox.items],
        total=inbox.total,
        page=inbox.page,
        page_size=inbox.page_size,
        pages=inbox.pages,
        unread_total=inbox.unread_total,
    )


@app.get(
    "/member/notifications/unread-count",
    response_model=MemberNotificationCountResponse,
    tags=["member self-service"],
)
def member_notifications_unread(
    member: Annotated[AuthenticatedMember, Depends(get_current_member)],
    session: SessionDependency,
) -> MemberNotificationCountResponse:
    return MemberNotificationCountResponse(unread=unread_notification_count(session, member.member_id))


@app.post(
    "/member/notifications/{notification_id}/read",
    response_model=MemberNotificationResponse,
    tags=["member self-service"],
)
def member_notification_read(
    notification_id: UUID,
    member: Annotated[AuthenticatedMember, Depends(get_current_member)],
    session: SessionDependency,
) -> MemberNotificationResponse:
    try:
        item = mark_notification_read(session, member.member_id, notification_id)
    except NotificationError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return _member_notification_response(item)


@app.post(
    "/member/notifications/read-all",
    response_model=MemberNotificationReadAllResponse,
    tags=["member self-service"],
)
def member_notifications_read_all(
    member: Annotated[AuthenticatedMember, Depends(get_current_member)],
    session: SessionDependency,
) -> MemberNotificationReadAllResponse:
    return MemberNotificationReadAllResponse(
        updated=mark_all_notifications_read(session, member.member_id)
    )


@app.get(
    "/admin/notifications",
    response_model=StaffNotificationPageResponse,
    tags=["staff self-service"],
)
def staff_notifications(
    principal: Annotated[AuthenticatedUser, Depends(get_current_principal)],
    session: SessionDependency,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> StaffNotificationPageResponse:
    inbox = list_staff_notifications(session, principal.user_id, page=page, page_size=page_size)
    return StaffNotificationPageResponse(
        items=[_staff_notification_response(item) for item in inbox.items],
        total=inbox.total,
        page=inbox.page,
        page_size=inbox.page_size,
        pages=inbox.pages,
        unread_total=inbox.unread_total,
    )


@app.get(
    "/admin/notifications/unread-count",
    response_model=StaffNotificationCountResponse,
    tags=["staff self-service"],
)
def staff_notifications_unread(
    principal: Annotated[AuthenticatedUser, Depends(get_current_principal)],
    session: SessionDependency,
) -> StaffNotificationCountResponse:
    return StaffNotificationCountResponse(
        unread=unread_staff_notification_count(session, principal.user_id)
    )


@app.post(
    "/admin/notifications/{notification_id}/read",
    response_model=StaffNotificationResponse,
    tags=["staff self-service"],
)
def staff_notification_read(
    notification_id: UUID,
    principal: Annotated[AuthenticatedUser, Depends(get_current_principal)],
    session: SessionDependency,
) -> StaffNotificationResponse:
    try:
        item = mark_staff_notification_read(session, principal.user_id, notification_id)
    except NotificationError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return _staff_notification_response(item)


@app.post(
    "/admin/notifications/read-all",
    response_model=StaffNotificationReadAllResponse,
    tags=["staff self-service"],
)
def staff_notifications_read_all(
    principal: Annotated[AuthenticatedUser, Depends(get_current_principal)],
    session: SessionDependency,
) -> StaffNotificationReadAllResponse:
    return StaffNotificationReadAllResponse(
        updated=mark_all_staff_notifications_read(session, principal.user_id)
    )


@app.get("/admin/roles", tags=["staff administration"])
def get_roles_and_permissions(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("roles.manage"))],
) -> list[dict[str, object]]:
    return list_roles_and_permissions(session)


@app.get("/admin/staff", tags=["staff administration"])
def list_staff(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("staff.read"))],
) -> list[dict[str, object]]:
    employees = session.exec(select(Employee).order_by(Employee.last_name, Employee.first_name)).all()
    return [
        {
            "id": employee.id,
            "employee_number": employee.employee_number,
            "first_name": employee.first_name,
            "last_name": employee.last_name,
            "email": employee.email,
            "phone": employee.phone,
            "job_title": employee.job_title,
            "status": employee.status,
            "hired_at": employee.hired_at,
        }
        for employee in employees
    ]


@app.get("/admin/staff/shifts", tags=["staff administration"])
def list_staff_shifts(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("attendance.read"))],
    employee_id: Annotated[UUID | None, Query()] = None,
    days: Annotated[int, Query(ge=1, le=60)] = 14,
) -> list[dict[str, object]]:
    now = utc_now()
    rows = list_shifts_with_attendance(
        session,
        employee_id=employee_id,
        from_at=now - timedelta(days=days),
        to_at=now + timedelta(days=days),
    )
    return [_shift_payload(shift, attendance) for shift, attendance in rows]


@app.post(
    "/admin/staff/{employee_id}/shifts",
    status_code=status.HTTP_201_CREATED,
    tags=["staff administration"],
)
def schedule_staff_shift(
    employee_id: UUID,
    request: ScheduleShiftRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("attendance.manage"))],
) -> dict[str, object]:
    if request.starts_at.tzinfo is None or request.ends_at.tzinfo is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Shift timestamps must include a timezone",
        )
    try:
        shift = create_shift(
            session,
            employee_id=employee_id,
            starts_at=request.starts_at,
            ends_at=request.ends_at,
            created_by=principal.user_id,
        )
    except InvalidAttendanceTime as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    except (ShiftOverlap, ShiftNotAvailable) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return _shift_payload(shift, None)


@app.get("/staff/attendance", tags=["staff self-service"])
def my_attendance(
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("attendance.self"))],
    days: Annotated[int, Query(ge=1, le=60)] = 14,
) -> dict[str, object]:
    if principal.employee_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The account is not linked to an employee",
        )
    now = utc_now()
    rows = list_shifts_with_attendance(
        session,
        employee_id=principal.employee_id,
        from_at=now - timedelta(days=days),
        to_at=now + timedelta(days=days),
    )
    return {
        "employee_id": principal.employee_id,
        "items": [_shift_payload(shift, attendance) for shift, attendance in rows],
    }


@app.post("/staff/attendance/clock-in", tags=["staff self-service"])
def self_clock_in(
    request: AttendanceMarkRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("attendance.self"))],
) -> dict[str, object]:
    return _self_attendance_mark(session, principal, request, clock_in)


@app.post("/staff/attendance/clock-out", tags=["staff self-service"])
def self_clock_out(
    request: AttendanceMarkRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("attendance.self"))],
) -> dict[str, object]:
    return _self_attendance_mark(session, principal, request, clock_out)


def _self_attendance_mark(
    session: Session,
    principal: AuthenticatedUser,
    request: AttendanceMarkRequest,
    action: Callable[..., StaffAttendance],
) -> dict[str, object]:
    if principal.employee_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The account is not linked to an employee",
        )
    try:
        attendance = action(
            session,
            shift_id=request.shift_id,
            actor_id=principal.user_id,
            request_id=request.request_id,
            source="staff_app",
            enforce_employee_id=principal.employee_id,
        )
    except AttendanceNotAllowed as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except (ShiftNotAvailable, AttendanceAlreadyRecorded, AttendanceEventConflict) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except InvalidAttendanceTime as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    return _attendance_payload(attendance)


def _shift_payload(shift: StaffShift, attendance: StaffAttendance | None) -> dict[str, object]:
    return {
        "id": shift.id,
        "employee_id": shift.employee_id,
        "starts_at": shift.starts_at,
        "ends_at": shift.ends_at,
        "status": shift.status,
        "attendance": _attendance_payload(attendance) if attendance is not None else None,
    }


def _attendance_payload(attendance: StaffAttendance) -> dict[str, object]:
    return {
        "id": attendance.id,
        "shift_id": attendance.shift_id,
        "employee_id": attendance.employee_id,
        "status": attendance.status,
        "check_in_at": attendance.check_in_at,
        "check_in_source": attendance.check_in_source,
        "check_out_at": attendance.check_out_at,
        "check_out_source": attendance.check_out_source,
    }


@app.get("/admin/users", response_model=list[UserOverviewResponse], tags=["staff administration"])
def list_users_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("roles.manage"))],
) -> list[UserOverviewResponse]:
    return [
        UserOverviewResponse(
            id=user.id,
            email=user.email,
            status=user.status,
            employee_id=user.employee_id,
            employee_name=user.employee_name,
            roles=list(user.roles),
            last_login_at=user.last_login_at,
        )
        for user in list_users(session)
    ]


@app.get("/admin/sessions", response_model=list[SessionOverviewResponse], tags=["staff administration"])
def list_sessions_endpoint(
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("sessions.manage"))],
) -> list[SessionOverviewResponse]:
    return [
        SessionOverviewResponse(
            id=item.id,
            user_id=item.user_id,
            email=item.email,
            employee_name=item.employee_name,
            created_at=item.created_at,
            expires_at=item.expires_at,
            last_seen_at=item.last_seen_at,
            is_current=item.is_current,
        )
        for item in list_active_sessions(session, current_session_id=principal.session_id)
    ]


@app.delete(
    "/admin/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["staff administration"],
)
def revoke_user_session(
    session_id: UUID,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("sessions.manage"))],
) -> None:
    try:
        revoke_session_by_id(session, session_id, actor_id=principal.user_id)
    except SessionNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except IdentityError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@app.get("/admin/members", response_model=MemberDirectoryResponse, tags=["member administration"])
def list_members(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("members.read"))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    search: Annotated[str | None, Query(max_length=120)] = None,
    sort: Annotated[Literal["name", "plan", "renewal"], Query()] = "name",
    direction: Annotated[Literal["asc", "desc"], Query()] = "asc",
    state: Annotated[Literal["active", "expiring_soon", "frozen", "pending"] | None, Query()] = None,
    plan_id: Annotated[UUID | None, Query()] = None,
) -> MemberDirectoryResponse:
    directory = list_member_overview(
        session,
        page=page,
        page_size=page_size,
        search=search,
        sort=sort,
        direction=direction,
        state=state,
        plan_id=plan_id,
    )
    return MemberDirectoryResponse(
        items=[
            MemberResponse(
                id=overview.id,
                first_name=overview.first_name,
                last_name=overview.last_name,
                email=overview.email,
                phone=overview.phone,
                status=overview.status,
                membership_status=overview.membership_status,
                plan_name=overview.plan_name,
                membership_starts_at=overview.membership_starts_at,
                membership_ends_at=overview.membership_ends_at,
                auto_renew=overview.auto_renew,
            )
            for overview in directory.items
        ],
        total=directory.total,
        page=directory.page,
        page_size=directory.page_size,
        pages=directory.pages,
        summary=MemberSummaryResponse(
            active=directory.summary.active,
            expiring_soon=directory.summary.expiring_soon,
            frozen=directory.summary.frozen,
            pending=directory.summary.pending,
        ),
        plans=[
            MemberPlanOptionResponse(id=option.id, name=option.name)
            for option in directory.plans
        ],
    )


@app.post(
    "/admin/members",
    response_model=CreatedMemberResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["member administration"],
)
def create_member(
    request: CreateMemberRequest,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("members.manage"))],
) -> CreatedMemberResponse:
    try:
        member = register_member(
            session,
            first_name=request.first_name,
            last_name=request.last_name,
            email=request.email,
            phone=request.phone,
            privacy_notice_accepted=request.privacy_notice_accepted,
        )
    except InvalidMemberData as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    except DuplicateMemberEmail as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return CreatedMemberResponse(
        id=member.id,
        first_name=member.first_name,
        last_name=member.last_name,
        email=member.email,
        phone=member.phone,
        status=member.status,
        consent_recorded=member.consent_recorded,
    )


_BILLING_ERROR_STATUS: tuple[tuple[type[BillingError], int], ...] = (
    (InvalidMemberData, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (CancellationReasonRequired, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (InvalidMembershipPayment, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (DuplicateMemberEmail, status.HTTP_409_CONFLICT),
    (InvalidMembershipTransition, status.HTTP_409_CONFLICT),
    (CashSessionRequired, status.HTTP_409_CONFLICT),
    (MembershipPaymentNotAllowed, status.HTTP_409_CONFLICT),
    (IdempotencyConflict, status.HTTP_409_CONFLICT),
    (MemberNotFound, status.HTTP_404_NOT_FOUND),
    (PlanUnavailable, status.HTTP_404_NOT_FOUND),
    (MembershipNotFound, status.HTTP_404_NOT_FOUND),
)


def _billing_http_error(error: BillingError) -> HTTPException:
    for error_type, code in _BILLING_ERROR_STATUS:
        if isinstance(error, error_type):
            return HTTPException(status_code=code, detail=str(error))
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))


def _membership_state_response(state: MembershipState) -> MembershipStateResponse:
    return MembershipStateResponse(
        membership_id=state.membership_id,
        member_id=state.member_id,
        plan_id=state.plan_id,
        plan_name=state.plan_name,
        status=state.status,
        starts_at=state.starts_at,
        ends_at=state.ends_at,
        auto_renew=state.auto_renew,
        previous_status=state.previous_status,
        plan_changed=state.plan_changed,
    )


@app.get("/admin/plans", response_model=list[PlanResponse], tags=["member administration"])
def list_plans(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("members.read"))],
) -> list[PlanResponse]:
    plans = session.exec(
        select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.name, Plan.id)
    ).all()
    return [
        PlanResponse(
            id=plan.id,
            name=plan.name,
            duration_days=plan.duration_days,
            price_cents=plan.price_cents,
            currency=plan.currency,
        )
        for plan in plans
    ]


@app.patch(
    "/admin/members/{member_id}",
    response_model=MemberContactResponse,
    tags=["member administration"],
)
def update_member_endpoint(
    member_id: UUID,
    request: UpdateMemberRequest,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("members.manage"))],
) -> MemberContactResponse:
    try:
        member = update_member(
            session,
            member_id,
            first_name=request.first_name,
            last_name=request.last_name,
            email=request.email,
            phone=request.phone,
        )
    except BillingError as error:
        raise _billing_http_error(error) from error
    return MemberContactResponse(
        id=member.id,
        first_name=member.first_name,
        last_name=member.last_name,
        email=member.email,
        phone=member.phone,
        status=member.status,
    )


@app.post(
    "/admin/members/{member_id}/membership",
    response_model=MembershipStateResponse,
    tags=["member administration"],
)
def assign_member_plan(
    member_id: UUID,
    request: AssignPlanRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("members.manage"))],
) -> MembershipStateResponse:
    try:
        state = assign_membership_plan(
            session,
            member_id=member_id,
            plan_id=request.plan_id,
            auto_renew=request.auto_renew,
            actor_id=principal.user_id,
            note=request.note,
        )
    except BillingError as error:
        raise _billing_http_error(error) from error
    return _membership_state_response(state)


@app.post(
    "/admin/members/{member_id}/membership/payments",
    response_model=MembershipPaymentResponse,
    tags=["member administration"],
)
def collect_member_membership_payment(
    member_id: UUID,
    request: CollectMembershipPaymentRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("members.manage"))],
) -> MembershipPaymentResponse:
    try:
        result = collect_membership_payment(
            session,
            member_id=member_id,
            plan_id=request.plan_id,
            payment_method=request.payment_method,
            idempotency_key=request.idempotency_key,
            note=request.note,
            auto_renew=request.auto_renew,
            actor_id=principal.user_id,
        )
    except BillingError as error:
        raise _billing_http_error(error) from error
    return MembershipPaymentResponse(
        payment_id=result.payment_id,
        payment_attempt_id=result.payment_attempt_id,
        membership_id=result.membership_id,
        member_id=result.member_id,
        plan_id=result.plan_id,
        plan_name=result.plan_name,
        amount_cents=result.amount_cents,
        currency=result.currency,
        method=result.method,
        paid_at=result.paid_at,
        cash_session_id=result.cash_session_id,
        period_starts_at=result.period_starts_at,
        period_ends_at=result.period_ends_at,
        membership_status=result.membership_status,
        auto_renew=result.auto_renew,
        renewed=result.renewed,
        idempotent_replay=result.idempotent_replay,
    )


@app.post(
    "/admin/members/{member_id}/membership/freeze",
    response_model=MembershipStateResponse,
    tags=["member administration"],
)
def freeze_member_membership(
    member_id: UUID,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("members.manage"))],
) -> MembershipStateResponse:
    try:
        state = freeze_membership(session, member_id, actor_id=principal.user_id)
    except BillingError as error:
        raise _billing_http_error(error) from error
    return _membership_state_response(state)


@app.post(
    "/admin/members/{member_id}/membership/resume",
    response_model=MembershipStateResponse,
    tags=["member administration"],
)
def resume_member_membership(
    member_id: UUID,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("members.manage"))],
) -> MembershipStateResponse:
    try:
        state = resume_membership(session, member_id, actor_id=principal.user_id)
    except BillingError as error:
        raise _billing_http_error(error) from error
    return _membership_state_response(state)


@app.post(
    "/admin/members/{member_id}/membership/cancel",
    response_model=MembershipStateResponse,
    tags=["member administration"],
)
def cancel_member_membership(
    member_id: UUID,
    request: CancelMembershipRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("members.manage"))],
) -> MembershipStateResponse:
    try:
        state = cancel_membership(
            session, member_id, reason=request.reason, actor_id=principal.user_id
        )
    except BillingError as error:
        raise _billing_http_error(error) from error
    return _membership_state_response(state)


@app.get("/admin/access-events", response_model=AccessEventDirectoryResponse, tags=["access administration"])
def list_access_events_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("access.read"))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    search: Annotated[str | None, Query(max_length=120)] = None,
    state: Annotated[Literal["authorized", "denied", "manual"] | None, Query()] = None,
) -> AccessEventDirectoryResponse:
    directory = list_access_events(session, page=page, page_size=page_size, search=search, state=state)
    return AccessEventDirectoryResponse(
        items=[
            AccessEventResponse(
                id=item.id,
                event_id=item.event_id,
                member_id=item.member_id,
                member_name=item.member_name,
                member_email=item.member_email,
                plan_name=item.plan_name,
                reader_id=item.reader_id,
                direction=item.direction,
                authorized=item.authorized,
                reason=item.reason,
                note=item.note,
                source=item.source,
                occurred_at=item.occurred_at,
                offline=item.offline,
            )
            for item in directory.items
        ],
        total=directory.total,
        page=directory.page,
        page_size=directory.page_size,
        pages=directory.pages,
        summary=AccessEventSummaryResponse(
            total=directory.summary.total,
            authorized=directory.summary.authorized,
            denied=directory.summary.denied,
            manual=directory.summary.manual,
        ),
    )


@app.post(
    "/admin/access-events/manual",
    response_model=AccessEventResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["access administration"],
)
def create_manual_access(
    request: ManualAccessRequest,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("access.manual_override"))],
) -> AccessEventResponse:
    try:
        event = record_manual_access(
            session,
            member_id=request.member_id,
            note=request.note,
            reader_id=request.reader_id,
        )
    except AccessMemberNotFound as error:
        raise HTTPException(status_code=404, detail="Member was not found") from error
    item = access_event_item(session, event)
    return AccessEventResponse(
        id=item.id,
        event_id=item.event_id,
        member_id=item.member_id,
        member_name=item.member_name,
        member_email=item.member_email,
        plan_name=item.plan_name,
        reader_id=item.reader_id,
        direction=item.direction,
        authorized=item.authorized,
        reason=item.reason,
        note=item.note,
        source=item.source,
        occurred_at=item.occurred_at,
        offline=item.offline,
    )


@app.get("/admin/dashboard", response_model=DashboardResponse, tags=["dashboard"])
def get_dashboard(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("dashboard.read"))],
) -> DashboardResponse:
    members = member_directory_summary(session)
    access = access_today_summary(session, timezone_name=os.getenv("APP_TIMEZONE", DEFAULT_TIMEZONE))
    return DashboardResponse(
        as_of=utc_now(),
        members=DashboardMembersResponse(
            total=members.total,
            active=members.active,
            expiring_soon=members.expiring_soon,
            frozen=members.frozen,
            pending=members.pending,
        ),
        access=DashboardAccessResponse(entries_today=access.entries, denied_today=access.denied),
    )


_INVENTORY_ERROR_STATUS: tuple[tuple[type[InventoryError], int], ...] = (
    (InvalidProductData, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (InvalidCart, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (InvalidReturn, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (InvalidAccountPayment, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (InvalidCreditLimit, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (InvalidStatementFormat, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (InvalidStatementPurpose, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (StatementRecipientMissing, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (InvalidSupplierData, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (InvalidPurchaseOrderData, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (DifferenceExplanationRequired, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (ProductNotFound, status.HTTP_404_NOT_FOUND),
    (SupplierNotFound, status.HTTP_404_NOT_FOUND),
    (PurchaseOrderNotFound, status.HTTP_404_NOT_FOUND),
    (CashSessionNotFound, status.HTTP_404_NOT_FOUND),
    (MemberUnavailable, status.HTTP_404_NOT_FOUND),
    (StatementDeliveryNotFound, status.HTTP_404_NOT_FOUND),
    (StatementDeliveryFailed, status.HTTP_502_BAD_GATEWAY),
    (StatementDeliveryRetryNotAllowed, status.HTTP_409_CONFLICT),
    (StatementReminderNotAllowed, status.HTTP_409_CONFLICT),
    (StatementEmailNotConfigured, status.HTTP_503_SERVICE_UNAVAILABLE),
    (SaleNotFound, status.HTTP_404_NOT_FOUND),
    (SaleItemNotFound, status.HTTP_404_NOT_FOUND),
    (DuplicateProductSku, status.HTTP_409_CONFLICT),
    (DuplicateProductBarcode, status.HTTP_409_CONFLICT),
    (DuplicateSupplierName, status.HTTP_409_CONFLICT),
    (ProductUnavailable, status.HTTP_409_CONFLICT),
    (InsufficientStock, status.HTTP_409_CONFLICT),
    (ReturnExceedsSold, status.HTTP_409_CONFLICT),
    (NoOutstandingBalance, status.HTTP_409_CONFLICT),
    (PaymentExceedsBalance, status.HTTP_409_CONFLICT),
    (CreditLimitExceeded, status.HTTP_409_CONFLICT),
    (InvalidPurchaseOrderState, status.HTTP_409_CONFLICT),
    (PurchaseOrderOverReceive, status.HTTP_409_CONFLICT),
    (CashSessionAlreadyOpen, status.HTTP_409_CONFLICT),
    (NoOpenCashSession, status.HTTP_409_CONFLICT),
    (InvalidCashSessionState, status.HTTP_409_CONFLICT),
)


def _inventory_http_error(error: InventoryError) -> HTTPException:
    for error_type, code in _INVENTORY_ERROR_STATUS:
        if isinstance(error, error_type):
            return HTTPException(status_code=code, detail=str(error))
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))


def _product_state(item: ProductItem) -> str:
    if not item.is_active:
        return "inactive"
    if item.stock <= 0:
        return "out"
    if item.stock <= item.stock_min:
        return "low"
    return "active"


def _product_response(item: ProductItem) -> ProductResponse:
    return ProductResponse(
        id=item.id,
        sku=item.sku,
        name=item.name,
        category=item.category,
        barcode=item.barcode,
        price_cents=item.price_cents,
        cost_cents=item.cost_cents,
        stock_min=item.stock_min,
        is_active=item.is_active,
        stock=item.stock,
        state=_product_state(item),
        updated_at=item.updated_at,
    )


def _sale_response(item: SaleItemView) -> SaleResponse:
    return SaleResponse(
        id=item.id,
        folio=item.folio,
        status=item.status,
        payment_method=item.payment_method,
        member_id=item.member_id,
        member_name=item.member_name,
        cashier_id=item.cashier_id,
        cashier_email=item.cashier_email,
        subtotal_cents=item.subtotal_cents,
        discount_cents=item.discount_cents,
        tax_cents=item.tax_cents,
        total_cents=item.total_cents,
        refunded_cents=item.refunded_cents,
        note=item.note,
        sold_at=item.sold_at,
        cash_session_id=item.cash_session_id,
        origin=item.origin,
        client_reference=item.client_reference,
        lines=[
            SaleLineResponse(
                sale_item_id=line.sale_item_id,
                product_id=line.product_id,
                product_name=line.product_name,
                sku=line.sku,
                quantity=line.quantity,
                unit_price_cents=line.unit_price_cents,
                line_total_cents=line.line_total_cents,
                refunded_quantity=line.refunded_quantity,
                returnable_quantity=line.returnable_quantity,
            )
            for line in item.lines
        ],
    )


def _offline_sale_result_response(item: OfflineSaleResult) -> OfflineSaleResultResponse:
    return OfflineSaleResultResponse(
        client_reference=item.client_reference,
        status=item.status,
        sale=_sale_response(item.sale) if item.sale is not None else None,
        error=item.error,
    )


def _sale_return_response(item: SaleReturnView) -> SaleReturnResponse:
    return SaleReturnResponse(
        id=item.id,
        folio=item.folio,
        sale_id=item.sale_id,
        sale_folio=item.sale_folio,
        cash_session_id=item.cash_session_id,
        member_id=item.member_id,
        member_name=item.member_name,
        actor_id=item.actor_id,
        actor_email=item.actor_email,
        refund_method=item.refund_method,
        total_refund_cents=item.total_refund_cents,
        reason=item.reason,
        returned_at=item.returned_at,
        lines=[
            SaleReturnLineResponse(
                sale_item_id=line.sale_item_id,
                product_id=line.product_id,
                product_name=line.product_name,
                sku=line.sku,
                quantity=line.quantity,
                unit_price_cents=line.unit_price_cents,
                line_refund_cents=line.line_refund_cents,
                disposition=line.disposition,
            )
            for line in item.lines
        ],
    )


def _cash_session_response(item: CashSessionView) -> CashSessionResponse:
    return CashSessionResponse(
        id=item.id,
        status=item.status,
        opened_by=item.opened_by,
        opened_by_email=item.opened_by_email,
        opened_at=item.opened_at,
        opening_cash_cents=item.opening_cash_cents,
        closed_by=item.closed_by,
        closed_by_email=item.closed_by_email,
        closed_at=item.closed_at,
        expected_cash_cents=item.expected_cash_cents,
        counted_cash_cents=item.counted_cash_cents,
        difference_cents=item.difference_cents,
        notes=item.notes,
        sales_count=item.sales_count,
        total_sales_cents=item.total_sales_cents,
        cash_sales_cents=item.cash_sales_cents,
        card_sales_cents=item.card_sales_cents,
        transfer_sales_cents=item.transfer_sales_cents,
        account_sales_cents=item.account_sales_cents,
        refunds_count=item.refunds_count,
        total_refunds_cents=item.total_refunds_cents,
        cash_refunds_cents=item.cash_refunds_cents,
        account_refunds_cents=item.account_refunds_cents,
        account_payments_count=item.account_payments_count,
        account_payments_cents=item.account_payments_cents,
        cash_account_payments_cents=item.cash_account_payments_cents,
        membership_payments_count=item.membership_payments_count,
        membership_payments_cents=item.membership_payments_cents,
        cash_membership_payments_cents=item.cash_membership_payments_cents,
    )


def _account_aging_response(aging: AccountAging) -> AccountAgingResponse:
    return AccountAgingResponse(
        current_cents=aging.current_cents,
        days_31_60_cents=aging.days_31_60_cents,
        days_61_90_cents=aging.days_61_90_cents,
        over_90_cents=aging.over_90_cents,
    )


def _member_account_summary_response(
    summary: MemberAccountSummary,
) -> MemberAccountSummaryResponse:
    return MemberAccountSummaryResponse(
        member_id=summary.member_id,
        member_name=summary.member_name,
        email=summary.email,
        phone=summary.phone,
        member_status=summary.member_status,
        charges_cents=summary.charges_cents,
        credits_cents=summary.credits_cents,
        payments_cents=summary.payments_cents,
        balance_cents=summary.balance_cents,
        credit_limit_cents=summary.credit_limit_cents,
        credit_available_cents=summary.credit_available_cents,
        over_limit=summary.over_limit,
        aging=_account_aging_response(summary.aging),
        charges_count=summary.charges_count,
        payments_count=summary.payments_count,
        last_activity_at=summary.last_activity_at,
        oldest_charge_at=summary.oldest_charge_at,
    )


def _member_account_entry_response(
    entry: MemberAccountEntry,
) -> MemberAccountEntryResponse:
    return MemberAccountEntryResponse(
        kind=entry.kind,
        occurred_at=entry.occurred_at,
        description=entry.description,
        reference=entry.reference,
        method=entry.method,
        amount_cents=entry.amount_cents,
        balance_cents=entry.balance_cents,
    )


def _member_account_statement_response(
    statement: MemberAccountStatement,
) -> MemberAccountStatementResponse:
    return MemberAccountStatementResponse(
        summary=_member_account_summary_response(statement.summary),
        entries=[_member_account_entry_response(entry) for entry in statement.entries],
        as_of=statement.as_of,
    )


def _statement_delivery_response(
    delivery: StatementDeliveryView,
) -> StatementDeliveryResponse:
    return StatementDeliveryResponse(
        id=delivery.id,
        member_id=delivery.member_id,
        actor_id=delivery.actor_id,
        actor_email=delivery.actor_email,
        recipient=delivery.recipient,
        format=delivery.format,
        purpose=delivery.purpose,
        status=delivery.status,
        as_of=delivery.as_of,
        error=delivery.error,
        retry_of_id=delivery.retry_of_id,
        created_at=delivery.created_at,
    )


def _statement_delivery_page_response(
    deliveries: StatementDeliveryList,
) -> StatementDeliveryPageResponse:
    return StatementDeliveryPageResponse(
        items=[_statement_delivery_response(item) for item in deliveries.items],
        total=deliveries.total,
        page=deliveries.page,
        page_size=deliveries.page_size,
        pages=deliveries.pages,
    )


def _statement_reminder_batch_response(
    batch: StatementReminderBatch,
) -> StatementReminderBatchResponse:
    return StatementReminderBatchResponse(
        requested=batch.requested,
        sent=batch.sent,
        simulated=batch.simulated,
        skipped=batch.skipped,
        failed=batch.failed,
        results=[
            StatementReminderResultResponse(
                member_id=result.member_id,
                member_name=result.member_name,
                status=result.status,
                reason=result.reason,
                balance_cents=result.balance_cents,
                overdue_cents=result.overdue_cents,
                delivery=(
                    _statement_delivery_response(result.delivery)
                    if result.delivery is not None
                    else None
                ),
            )
            for result in batch.results
        ],
    )


def _member_account_payment_response(
    payment: MemberAccountPaymentView,
) -> MemberAccountPaymentResponse:
    return MemberAccountPaymentResponse(
        id=payment.id,
        member_id=payment.member_id,
        member_name=payment.member_name,
        cash_session_id=payment.cash_session_id,
        actor_id=payment.actor_id,
        actor_email=payment.actor_email,
        method=payment.method,
        amount_cents=payment.amount_cents,
        note=payment.note,
        paid_at=payment.paid_at,
        balance_cents=payment.balance_cents,
    )


def _supplier_response(item: SupplierItem) -> SupplierResponse:
    return SupplierResponse(
        id=item.id,
        name=item.name,
        contact_name=item.contact_name,
        phone=item.phone,
        email=item.email,
        notes=item.notes,
        is_active=item.is_active,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _purchase_order_response(item: PurchaseOrderView) -> PurchaseOrderResponse:
    return PurchaseOrderResponse(
        id=item.id,
        folio=item.folio,
        supplier_id=item.supplier_id,
        supplier_name=item.supplier_name,
        status=item.status,
        subtotal_cents=item.subtotal_cents,
        tax_cents=item.tax_cents,
        total_cents=item.total_cents,
        expected_at=item.expected_at,
        notes=item.notes,
        created_by=item.created_by,
        created_by_email=item.created_by_email,
        received_by=item.received_by,
        received_by_email=item.received_by_email,
        created_at=item.created_at,
        sent_at=item.sent_at,
        received_at=item.received_at,
        cancelled_at=item.cancelled_at,
        lines=[
            PurchaseOrderLineResponse(
                item_id=line.item_id,
                product_id=line.product_id,
                product_name=line.product_name,
                sku=line.sku,
                quantity=line.quantity,
                received_quantity=line.received_quantity,
                pending_quantity=line.pending_quantity,
                unit_cost_cents=line.unit_cost_cents,
                line_total_cents=line.line_total_cents,
            )
            for line in item.lines
        ],
    )


@app.get("/admin/products", response_model=ProductDirectoryResponse, tags=["inventory"])
def list_products_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("inventory.read"))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    search: Annotated[str | None, Query(max_length=120)] = None,
    category: Annotated[str | None, Query(max_length=80)] = None,
    state: Annotated[Literal["active", "low", "out", "inactive"] | None, Query()] = None,
) -> ProductDirectoryResponse:
    directory = list_products(
        session,
        page=page,
        page_size=page_size,
        search=search,
        category=category,
        state=state,
    )
    return ProductDirectoryResponse(
        items=[_product_response(item) for item in directory.items],
        total=directory.total,
        page=directory.page,
        page_size=directory.page_size,
        pages=directory.pages,
        summary=ProductSummaryResponse(
            total=directory.summary.total,
            active=directory.summary.active,
            low_stock=directory.summary.low_stock,
            out_of_stock=directory.summary.out_of_stock,
            inactive=directory.summary.inactive,
        ),
        categories=directory.categories,
    )


@app.post(
    "/admin/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["inventory"],
)
def create_product_endpoint(
    request: CreateProductRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("inventory.manage"))],
) -> ProductResponse:
    try:
        product = create_product(
            session,
            sku=request.sku,
            name=request.name,
            category=request.category or "",
            barcode=request.barcode,
            price_cents=request.price_cents,
            cost_cents=request.cost_cents,
            stock_min=request.stock_min,
            initial_stock=request.initial_stock,
            actor_id=principal.user_id,
        )
    except InventoryError as error:
        raise _inventory_http_error(error) from error
    return _product_response(product)


@app.patch(
    "/admin/products/{product_id}",
    response_model=ProductResponse,
    tags=["inventory"],
)
def update_product_endpoint(
    product_id: UUID,
    request: UpdateProductRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("inventory.manage"))],
) -> ProductResponse:
    try:
        product = update_product(
            session,
            product_id,
            name=request.name,
            category=request.category or "",
            price_cents=request.price_cents,
            cost_cents=request.cost_cents,
            barcode=request.barcode,
            stock_min=request.stock_min,
            is_active=request.is_active,
            actor_id=principal.user_id,
        )
    except InventoryError as error:
        raise _inventory_http_error(error) from error
    return _product_response(product)


@app.post(
    "/admin/products/{product_id}/stock",
    response_model=ProductResponse,
    tags=["inventory"],
)
def register_stock_movement_endpoint(
    product_id: UUID,
    request: StockMovementRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("inventory.manage"))],
) -> ProductResponse:
    try:
        product = register_stock_movement(
            session,
            product_id,
            movement_type=request.movement_type,
            quantity=request.quantity,
            reason=request.reason,
            actor_id=principal.user_id,
        )
    except InventoryError as error:
        raise _inventory_http_error(error) from error
    return _product_response(product)


@app.get("/admin/sales", response_model=SaleDirectoryResponse, tags=["sales"])
def list_sales_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("sales.read"))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    search: Annotated[str | None, Query(max_length=120)] = None,
    payment_method: Annotated[
        Literal["cash", "card", "transfer", "account"] | None, Query()
    ] = None,
    origin: Annotated[Literal["online", "offline"] | None, Query()] = None,
) -> SaleDirectoryResponse:
    directory = list_sales(
        session,
        page=page,
        page_size=page_size,
        search=search,
        payment_method=payment_method,
        origin=origin,
    )
    return SaleDirectoryResponse(
        items=[_sale_response(item) for item in directory.items],
        total=directory.total,
        page=directory.page,
        page_size=directory.page_size,
        pages=directory.pages,
        summary=SaleSummaryResponse(
            count=directory.summary.count,
            total_cents=directory.summary.total_cents,
            cash_cents=directory.summary.cash_cents,
            card_cents=directory.summary.card_cents,
            transfer_cents=directory.summary.transfer_cents,
            account_cents=directory.summary.account_cents,
            refunds_cents=directory.summary.refunds_cents,
            refunded_count=directory.summary.refunded_count,
        ),
    )


@app.post(
    "/admin/sales",
    response_model=SaleResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["sales"],
)
def register_sale_endpoint(
    request: CreateSaleRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("sales.manage"))],
) -> SaleResponse:
    try:
        sale = register_sale(
            session,
            items=[(item.product_id, item.quantity) for item in request.items],
            payment_method=request.payment_method,
            member_id=request.member_id,
            note=request.note,
            cashier_id=principal.user_id,
        )
    except InventoryError as error:
        raise _inventory_http_error(error) from error
    return _sale_response(sale)


@app.post(
    "/admin/sales/offline",
    response_model=OfflineSaleSyncResponse,
    tags=["sales"],
)
def sync_offline_sales_endpoint(
    request: SyncOfflineSalesRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("sales.manage"))],
) -> OfflineSaleSyncResponse:
    entries = [
        OfflineSaleEntry(
            client_reference=sale.client_reference,
            items=[(item.product_id, item.quantity) for item in sale.items],
            payment_method=sale.payment_method,
            member_id=sale.member_id,
            note=sale.note,
            sold_at=sale.sold_at,
        )
        for sale in request.sales
    ]
    try:
        result = sync_offline_sales(session, entries, cashier_id=principal.user_id)
    except InventoryError as error:
        raise _inventory_http_error(error) from error
    return OfflineSaleSyncResponse(
        results=[_offline_sale_result_response(item) for item in result.results],
        created=result.created,
        duplicates=result.duplicates,
        rejected=result.rejected,
    )


@app.get("/admin/sales/returns", response_model=SaleReturnDirectoryResponse, tags=["sales"])
def list_sale_returns_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("sales.read"))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    search: Annotated[str | None, Query(max_length=120)] = None,
    sale_id: Annotated[UUID | None, Query()] = None,
) -> SaleReturnDirectoryResponse:
    directory = list_sale_returns(
        session,
        page=page,
        page_size=page_size,
        search=search,
        sale_id=sale_id,
    )
    return SaleReturnDirectoryResponse(
        items=[_sale_return_response(item) for item in directory.items],
        total=directory.total,
        page=directory.page,
        page_size=directory.page_size,
        pages=directory.pages,
        summary=SaleReturnSummaryResponse(
            count=directory.summary.count,
            total_refund_cents=directory.summary.total_refund_cents,
            cash_refund_cents=directory.summary.cash_refund_cents,
            card_refund_cents=directory.summary.card_refund_cents,
            transfer_refund_cents=directory.summary.transfer_refund_cents,
            account_refund_cents=directory.summary.account_refund_cents,
        ),
    )


@app.post(
    "/admin/sales/{sale_id}/returns",
    response_model=SaleReturnResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["sales"],
)
def register_sale_return_endpoint(
    sale_id: UUID,
    request: CreateSaleReturnRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("sales.manage"))],
) -> SaleReturnResponse:
    try:
        sale_return = register_sale_return(
            session,
            sale_id,
            lines=[(item.sale_item_id, item.quantity, item.disposition) for item in request.items],
            reason=request.reason,
            refund_method=request.refund_method,
            actor_id=principal.user_id,
        )
    except InventoryError as error:
        raise _inventory_http_error(error) from error
    return _sale_return_response(sale_return)


@app.get(
    "/admin/member-accounts",
    response_model=MemberAccountDirectoryResponse,
    tags=["sales"],
)
def list_member_accounts_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("sales.read"))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    search: Annotated[str | None, Query(max_length=120)] = None,
    over_limit: Annotated[bool | None, Query()] = None,
) -> MemberAccountDirectoryResponse:
    directory = list_member_accounts(
        session,
        page=page,
        page_size=page_size,
        search=search,
        over_limit=over_limit,
    )
    return MemberAccountDirectoryResponse(
        items=[_member_account_summary_response(item) for item in directory.items],
        total=directory.total,
        page=directory.page,
        page_size=directory.page_size,
        pages=directory.pages,
        total_receivable_cents=directory.total_receivable_cents,
        total_credit_cents=directory.total_credit_cents,
        members_with_balance=directory.members_with_balance,
        aging=_account_aging_response(directory.aging),
        over_limit_members=directory.over_limit_members,
        as_of=directory.as_of,
    )


@app.post(
    "/admin/member-accounts/reminders",
    response_model=StatementReminderBatchResponse,
    tags=["sales"],
)
def send_member_account_reminders_endpoint(
    request: SendStatementRemindersRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("sales.manage"))],
) -> StatementReminderBatchResponse:
    try:
        batch = send_member_account_reminders(
            session,
            request.member_ids,
            document_format=request.format,
            actor_id=principal.user_id,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    except InventoryError as error:
        raise _inventory_http_error(error) from error
    return _statement_reminder_batch_response(batch)


@app.get(
    "/admin/member-accounts/{member_id}",
    response_model=MemberAccountStatementResponse,
    tags=["sales"],
)
def member_account_statement_endpoint(
    member_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("sales.read"))],
) -> MemberAccountStatementResponse:
    try:
        statement = member_account_statement(session, member_id)
    except InventoryError as error:
        raise _inventory_http_error(error) from error
    return _member_account_statement_response(statement)


def _statement_download_response(
    statement: MemberAccountStatement, document_format: str
) -> Response:
    if document_format == "pdf":
        content = build_member_account_statement_pdf(statement)
        media_type = "application/pdf"
    else:
        content = build_member_account_statement_csv(statement)
        media_type = "text/csv; charset=utf-8"
    filename = statement_filename(statement, document_format)
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store, private",
        },
    )


@app.get(
    "/admin/member-accounts/{member_id}/statement.csv",
    tags=["sales"],
)
def member_account_statement_csv_endpoint(
    member_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("sales.read"))],
) -> Response:
    try:
        statement = member_account_statement(session, member_id)
    except InventoryError as error:
        raise _inventory_http_error(error) from error
    return _statement_download_response(statement, "csv")


@app.get(
    "/admin/member-accounts/{member_id}/statement.pdf",
    tags=["sales"],
)
def member_account_statement_pdf_endpoint(
    member_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("sales.read"))],
) -> Response:
    try:
        statement = member_account_statement(session, member_id)
    except InventoryError as error:
        raise _inventory_http_error(error) from error
    return _statement_download_response(statement, "pdf")


@app.post(
    "/admin/member-accounts/{member_id}/statement/send",
    response_model=StatementDeliveryResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["sales"],
)
def send_member_account_statement_endpoint(
    member_id: UUID,
    request: SendMemberAccountStatementRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("sales.manage"))],
) -> StatementDeliveryResponse:
    try:
        delivery = send_member_account_statement(
            session,
            member_id,
            recipient=str(request.recipient) if request.recipient is not None else None,
            document_format=request.format,
            actor_id=principal.user_id,
        )
    except InventoryError as error:
        raise _inventory_http_error(error) from error
    return _statement_delivery_response(delivery)


@app.get(
    "/admin/member-accounts/{member_id}/statement/deliveries",
    response_model=StatementDeliveryPageResponse,
    tags=["sales"],
)
def list_member_account_statement_deliveries_endpoint(
    member_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("sales.read"))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> StatementDeliveryPageResponse:
    try:
        deliveries = list_member_account_statement_deliveries(
            session, member_id, page=page, page_size=page_size
        )
    except InventoryError as error:
        raise _inventory_http_error(error) from error
    return _statement_delivery_page_response(deliveries)


@app.post(
    "/admin/member-accounts/{member_id}/statement/deliveries/{delivery_id}/retry",
    response_model=StatementDeliveryResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["sales"],
)
def retry_member_account_statement_delivery_endpoint(
    member_id: UUID,
    delivery_id: UUID,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("sales.manage"))],
) -> StatementDeliveryResponse:
    try:
        delivery = retry_member_account_statement_delivery(
            session,
            member_id,
            delivery_id,
            actor_id=principal.user_id,
        )
    except InventoryError as error:
        raise _inventory_http_error(error) from error
    return _statement_delivery_response(delivery)


@app.post(
    "/admin/member-accounts/{member_id}/payments",
    response_model=MemberAccountPaymentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["sales"],
)
def register_member_account_payment_endpoint(
    member_id: UUID,
    request: CreateMemberAccountPaymentRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("sales.manage"))],
) -> MemberAccountPaymentResponse:
    try:
        payment = register_member_account_payment(
            session,
            member_id,
            amount_cents=request.amount_cents,
            method=request.method,
            note=request.note,
            actor_id=principal.user_id,
        )
    except InventoryError as error:
        raise _inventory_http_error(error) from error
    return _member_account_payment_response(payment)


@app.patch(
    "/admin/member-accounts/{member_id}/credit-limit",
    response_model=MemberAccountSummaryResponse,
    tags=["sales"],
)
def update_member_credit_limit_endpoint(
    member_id: UUID,
    request: UpdateMemberCreditLimitRequest,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("sales.credit"))],
) -> MemberAccountSummaryResponse:
    try:
        summary = update_member_credit_limit(
            session,
            member_id,
            credit_limit_cents=request.credit_limit_cents,
        )
    except InventoryError as error:
        raise _inventory_http_error(error) from error
    return _member_account_summary_response(summary)


@app.get(
    "/admin/cash-sessions/current",
    response_model=CashSessionResponse | None,
    tags=["sales"],
)
def current_cash_session_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("sales.read"))],
) -> CashSessionResponse | None:
    cash_session = current_cash_session(session)
    if cash_session is None:
        return None
    return _cash_session_response(cash_session)


@app.get(
    "/admin/cash-sessions",
    response_model=list[CashSessionResponse],
    tags=["sales"],
)
def list_cash_sessions_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("sales.read"))],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[CashSessionResponse]:
    return [_cash_session_response(item) for item in list_cash_sessions(session, limit=limit)]


@app.post(
    "/admin/cash-sessions",
    response_model=CashSessionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["sales"],
)
def open_cash_session_endpoint(
    request: OpenCashSessionRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("sales.manage"))],
) -> CashSessionResponse:
    try:
        cash_session = open_cash_session(
            session,
            opening_cash_cents=request.opening_cash_cents,
            actor_id=principal.user_id,
        )
    except InventoryError as error:
        raise _inventory_http_error(error) from error
    return _cash_session_response(cash_session)


@app.post(
    "/admin/cash-sessions/{cash_session_id}/close",
    response_model=CashSessionResponse,
    tags=["sales"],
)
def close_cash_session_endpoint(
    cash_session_id: UUID,
    request: CloseCashSessionRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("sales.manage"))],
) -> CashSessionResponse:
    try:
        cash_session = close_cash_session(
            session,
            cash_session_id,
            counted_cash_cents=request.counted_cash_cents,
            notes=request.notes,
            actor_id=principal.user_id,
        )
    except InventoryError as error:
        raise _inventory_http_error(error) from error
    return _cash_session_response(cash_session)


@app.get("/admin/suppliers", response_model=SupplierDirectoryResponse, tags=["inventory"])
def list_suppliers_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("inventory.read"))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    search: Annotated[str | None, Query(max_length=120)] = None,
    active: Annotated[bool | None, Query()] = None,
) -> SupplierDirectoryResponse:
    directory = list_suppliers(
        session,
        page=page,
        page_size=page_size,
        search=search,
        active=active,
    )
    return SupplierDirectoryResponse(
        items=[_supplier_response(item) for item in directory.items],
        total=directory.total,
        page=directory.page,
        page_size=directory.page_size,
        pages=directory.pages,
    )


@app.post(
    "/admin/suppliers",
    response_model=SupplierResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["inventory"],
)
def create_supplier_endpoint(
    request: CreateSupplierRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("inventory.manage"))],
) -> SupplierResponse:
    try:
        supplier = create_supplier(
            session,
            name=request.name,
            contact_name=request.contact_name,
            phone=request.phone,
            email=request.email,
            notes=request.notes,
        )
    except InventoryError as error:
        raise _inventory_http_error(error) from error
    return _supplier_response(supplier)


@app.patch(
    "/admin/suppliers/{supplier_id}",
    response_model=SupplierResponse,
    tags=["inventory"],
)
def update_supplier_endpoint(
    supplier_id: UUID,
    request: UpdateSupplierRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("inventory.manage"))],
) -> SupplierResponse:
    try:
        supplier = update_supplier(
            session,
            supplier_id,
            name=request.name,
            contact_name=request.contact_name,
            phone=request.phone,
            email=request.email,
            notes=request.notes,
            is_active=request.is_active,
        )
    except InventoryError as error:
        raise _inventory_http_error(error) from error
    return _supplier_response(supplier)


@app.get(
    "/admin/purchase-orders",
    response_model=PurchaseOrderDirectoryResponse,
    tags=["inventory"],
)
def list_purchase_orders_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("inventory.read"))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    search: Annotated[str | None, Query(max_length=120)] = None,
    status_filter: Annotated[
        Literal["created", "sent", "received", "cancelled"] | None, Query(alias="status")
    ] = None,
    supplier_id: Annotated[UUID | None, Query()] = None,
) -> PurchaseOrderDirectoryResponse:
    directory = list_purchase_orders(
        session,
        page=page,
        page_size=page_size,
        search=search,
        status=status_filter,
        supplier_id=supplier_id,
    )
    return PurchaseOrderDirectoryResponse(
        items=[_purchase_order_response(item) for item in directory.items],
        total=directory.total,
        page=directory.page,
        page_size=directory.page_size,
        pages=directory.pages,
        summary=PurchaseOrderSummaryResponse(
            count=directory.summary.count,
            created=directory.summary.created,
            sent=directory.summary.sent,
            received=directory.summary.received,
            cancelled=directory.summary.cancelled,
            total_cents=directory.summary.total_cents,
        ),
    )


@app.post(
    "/admin/purchase-orders",
    response_model=PurchaseOrderResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["inventory"],
)
def create_purchase_order_endpoint(
    request: CreatePurchaseOrderRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("inventory.manage"))],
) -> PurchaseOrderResponse:
    try:
        order = create_purchase_order(
            session,
            supplier_id=request.supplier_id,
            lines=[(item.product_id, item.quantity, item.unit_cost_cents) for item in request.items],
            expected_at=request.expected_at,
            notes=request.notes,
            actor_id=principal.user_id,
        )
    except InventoryError as error:
        raise _inventory_http_error(error) from error
    return _purchase_order_response(order)


@app.get(
    "/admin/purchase-orders/{purchase_order_id}",
    response_model=PurchaseOrderResponse,
    tags=["inventory"],
)
def get_purchase_order_endpoint(
    purchase_order_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("inventory.read"))],
) -> PurchaseOrderResponse:
    try:
        order = get_purchase_order(session, purchase_order_id)
    except InventoryError as error:
        raise _inventory_http_error(error) from error
    return _purchase_order_response(order)


@app.post(
    "/admin/purchase-orders/{purchase_order_id}/send",
    response_model=PurchaseOrderResponse,
    tags=["inventory"],
)
def send_purchase_order_endpoint(
    purchase_order_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("inventory.manage"))],
) -> PurchaseOrderResponse:
    try:
        order = send_purchase_order(session, purchase_order_id)
    except InventoryError as error:
        raise _inventory_http_error(error) from error
    return _purchase_order_response(order)


@app.post(
    "/admin/purchase-orders/{purchase_order_id}/receive",
    response_model=PurchaseOrderResponse,
    tags=["inventory"],
)
def receive_purchase_order_endpoint(
    purchase_order_id: UUID,
    request: ReceivePurchaseOrderRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("inventory.manage"))],
) -> PurchaseOrderResponse:
    try:
        order = receive_purchase_order(
            session,
            purchase_order_id,
            lines=[(item.item_id, item.quantity) for item in request.items],
            actor_id=principal.user_id,
        )
    except InventoryError as error:
        raise _inventory_http_error(error) from error
    return _purchase_order_response(order)


@app.post(
    "/admin/purchase-orders/{purchase_order_id}/cancel",
    response_model=PurchaseOrderResponse,
    tags=["inventory"],
)
def cancel_purchase_order_endpoint(
    purchase_order_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("inventory.manage"))],
) -> PurchaseOrderResponse:
    try:
        order = cancel_purchase_order(session, purchase_order_id)
    except InventoryError as error:
        raise _inventory_http_error(error) from error
    return _purchase_order_response(order)


_CLASSES_ERROR_STATUS: tuple[tuple[type[ClassesError], int], ...] = (
    (InvalidClassData, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (ClassTypeNotFound, status.HTTP_404_NOT_FOUND),
    (ClassRoomNotFound, status.HTTP_404_NOT_FOUND),
    (InstructorNotFound, status.HTTP_404_NOT_FOUND),
    (ClassSessionNotFound, status.HTTP_404_NOT_FOUND),
    (ReservationNotFound, status.HTTP_404_NOT_FOUND),
    (MemberNotAvailable, status.HTTP_404_NOT_FOUND),
    (DuplicateClassType, status.HTTP_409_CONFLICT),
    (DuplicateClassRoom, status.HTTP_409_CONFLICT),
    (DuplicateReservation, status.HTTP_409_CONFLICT),
    (SessionFull, status.HTTP_409_CONFLICT),
    (InvalidSessionState, status.HTTP_409_CONFLICT),
    (InvalidReservationState, status.HTTP_409_CONFLICT),
    (MemberClassNotAllowed, status.HTTP_409_CONFLICT),
)


def _classes_http_error(error: ClassesError) -> HTTPException:
    for error_type, code in _CLASSES_ERROR_STATUS:
        if isinstance(error, error_type):
            return HTTPException(status_code=code, detail=str(error))
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))


def _class_type_response(item: ClassTypeItem) -> ClassTypeResponse:
    return ClassTypeResponse(
        id=item.id,
        name=item.name,
        description=item.description,
        is_active=item.is_active,
        created_at=item.created_at,
    )


def _class_room_response(item: ClassRoomItem) -> ClassRoomResponse:
    return ClassRoomResponse(
        id=item.id,
        name=item.name,
        capacity=item.capacity,
        is_active=item.is_active,
        created_at=item.created_at,
    )


def _instructor_response(item: InstructorItem) -> InstructorResponse:
    return InstructorResponse(id=item.id, name=item.name, job_title=item.job_title)


def _class_session_response(item: ClassSessionItem) -> ClassSessionResponse:
    return ClassSessionResponse(
        id=item.id,
        title=item.title,
        class_type_id=item.class_type_id,
        class_type_name=item.class_type_name,
        room_id=item.room_id,
        room_name=item.room_name,
        instructor_id=item.instructor_id,
        instructor_name=item.instructor_name,
        starts_at=item.starts_at,
        ends_at=item.ends_at,
        capacity=item.capacity,
        status=item.status,
        access_type=item.access_type,
        extra_price_cents=item.extra_price_cents,
        waitlist_enabled=item.waitlist_enabled,
        cancel_window_hours=item.cancel_window_hours,
        notes=item.notes,
        reserved_count=item.reserved_count,
        waitlist_count=item.waitlist_count,
        spots_left=item.spots_left,
        created_at=item.created_at,
        updated_at=item.updated_at,
        cancelled_at=item.cancelled_at,
    )


def _reservation_response(item: ReservationItem) -> ReservationResponse:
    return ReservationResponse(
        id=item.id,
        session_id=item.session_id,
        member_id=item.member_id,
        member_name=item.member_name,
        member_email=item.member_email,
        status=item.status,
        origin=item.origin,
        waitlist_position=item.waitlist_position,
        late_cancellation=item.late_cancellation,
        note=item.note,
        created_at=item.created_at,
        cancelled_at=item.cancelled_at,
        marked_at=item.marked_at,
    )


@app.get("/admin/classes/types", response_model=list[ClassTypeResponse], tags=["classes"])
def list_class_types_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("classes.read"))],
) -> list[ClassTypeResponse]:
    return [_class_type_response(item) for item in list_class_types(session)]


@app.post(
    "/admin/classes/types",
    response_model=ClassTypeResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["classes"],
)
def create_class_type_endpoint(
    request: CreateClassTypeRequest,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("classes.manage"))],
) -> ClassTypeResponse:
    try:
        item = create_class_type(session, name=request.name, description=request.description)
    except ClassesError as error:
        raise _classes_http_error(error) from error
    return _class_type_response(item)


@app.get("/admin/classes/rooms", response_model=list[ClassRoomResponse], tags=["classes"])
def list_class_rooms_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("classes.read"))],
) -> list[ClassRoomResponse]:
    return [_class_room_response(item) for item in list_class_rooms(session)]


@app.post(
    "/admin/classes/rooms",
    response_model=ClassRoomResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["classes"],
)
def create_class_room_endpoint(
    request: CreateClassRoomRequest,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("classes.manage"))],
) -> ClassRoomResponse:
    try:
        item = create_class_room(session, name=request.name, capacity=request.capacity)
    except ClassesError as error:
        raise _classes_http_error(error) from error
    return _class_room_response(item)


@app.get("/admin/classes/instructors", response_model=list[InstructorResponse], tags=["classes"])
def list_instructors_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("classes.read"))],
) -> list[InstructorResponse]:
    return [_instructor_response(item) for item in list_instructors(session)]


@app.get(
    "/admin/classes/sessions",
    response_model=ClassSessionDirectoryResponse,
    tags=["classes"],
)
def list_class_sessions_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("classes.read"))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
    room_id: Annotated[UUID | None, Query()] = None,
    instructor_id: Annotated[UUID | None, Query()] = None,
    class_type_id: Annotated[UUID | None, Query()] = None,
    status_filter: Annotated[Literal["scheduled", "cancelled"] | None, Query(alias="status")] = None,
    search: Annotated[str | None, Query(max_length=120)] = None,
) -> ClassSessionDirectoryResponse:
    directory = list_class_sessions(
        session,
        page=page,
        page_size=page_size,
        date_from=date_from,
        date_to=date_to,
        room_id=room_id,
        instructor_id=instructor_id,
        class_type_id=class_type_id,
        status=status_filter,
        search=search,
    )
    return ClassSessionDirectoryResponse(
        items=[_class_session_response(item) for item in directory.items],
        total=directory.total,
        page=directory.page,
        page_size=directory.page_size,
        pages=directory.pages,
        summary=ClassSessionSummaryResponse(
            total=directory.summary.total,
            scheduled=directory.summary.scheduled,
            cancelled=directory.summary.cancelled,
            upcoming=directory.summary.upcoming,
            reserved_total=directory.summary.reserved_total,
            waitlist_total=directory.summary.waitlist_total,
        ),
    )


@app.post(
    "/admin/classes/sessions",
    response_model=ClassSessionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["classes"],
)
def create_class_session_endpoint(
    request: CreateClassSessionRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("classes.manage"))],
) -> ClassSessionResponse:
    try:
        item = create_class_session(
            session,
            title=request.title,
            class_type_id=request.class_type_id,
            starts_at=request.starts_at,
            ends_at=request.ends_at,
            capacity=request.capacity,
            room_id=request.room_id,
            instructor_id=request.instructor_id,
            access_type=request.access_type,
            extra_price_cents=request.extra_price_cents,
            waitlist_enabled=request.waitlist_enabled,
            cancel_window_hours=request.cancel_window_hours,
            notes=request.notes,
            actor_id=principal.user_id,
        )
    except ClassesError as error:
        raise _classes_http_error(error) from error
    return _class_session_response(item)


@app.patch(
    "/admin/classes/sessions/{session_id}",
    response_model=ClassSessionResponse,
    tags=["classes"],
)
def update_class_session_endpoint(
    session_id: UUID,
    request: UpdateClassSessionRequest,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("classes.manage"))],
) -> ClassSessionResponse:
    provided = request.model_fields_set
    try:
        item = update_class_session(
            session,
            session_id,
            title=request.title,
            starts_at=request.starts_at,
            ends_at=request.ends_at,
            capacity=request.capacity,
            access_type=request.access_type,
            extra_price_cents=request.extra_price_cents,
            waitlist_enabled=request.waitlist_enabled,
            cancel_window_hours=request.cancel_window_hours,
            room_id=request.room_id if "room_id" in provided else UNSET,
            instructor_id=request.instructor_id if "instructor_id" in provided else UNSET,
            notes=request.notes if "notes" in provided else UNSET,
        )
    except ClassesError as error:
        raise _classes_http_error(error) from error
    return _class_session_response(item)


@app.post(
    "/admin/classes/sessions/{session_id}/cancel",
    response_model=ClassSessionResponse,
    tags=["classes"],
)
def cancel_class_session_endpoint(
    session_id: UUID,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("classes.manage"))],
) -> ClassSessionResponse:
    try:
        item = cancel_class_session(session, session_id, actor_id=principal.user_id)
    except ClassesError as error:
        raise _classes_http_error(error) from error
    return _class_session_response(item)


@app.get(
    "/admin/classes/sessions/{session_id}/reservations",
    response_model=ClassRosterResponse,
    tags=["classes"],
)
def list_session_reservations_endpoint(
    session_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("classes.read"))],
) -> ClassRosterResponse:
    try:
        roster = list_session_reservations(session, session_id)
    except ClassesError as error:
        raise _classes_http_error(error) from error
    return ClassRosterResponse(
        session=_class_session_response(roster.session),
        reservations=[_reservation_response(item) for item in roster.reservations],
    )


@app.post(
    "/admin/classes/sessions/{session_id}/reservations",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["classes"],
)
def reserve_seat_endpoint(
    session_id: UUID,
    request: ReserveSeatRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("classes.manage"))],
) -> ReservationResponse:
    try:
        item = reserve_seat(
            session,
            session_id,
            member_id=request.member_id,
            origin=request.origin,
            note=request.note,
            actor_id=principal.user_id,
        )
    except ClassesError as error:
        raise _classes_http_error(error) from error
    return _reservation_response(item)


@app.post(
    "/admin/classes/reservations/{reservation_id}/cancel",
    response_model=ReservationResponse,
    tags=["classes"],
)
def cancel_reservation_endpoint(
    reservation_id: UUID,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("classes.manage"))],
) -> ReservationResponse:
    try:
        item = cancel_reservation(session, reservation_id, actor_id=principal.user_id)
    except ClassesError as error:
        raise _classes_http_error(error) from error
    return _reservation_response(item)


@app.post(
    "/admin/classes/reservations/{reservation_id}/attendance",
    response_model=ReservationResponse,
    tags=["classes"],
)
def mark_attendance_endpoint(
    reservation_id: UUID,
    request: MarkAttendanceRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("classes.manage"))],
) -> ReservationResponse:
    try:
        item = mark_attendance(
            session,
            reservation_id,
            attended=request.attended,
            actor_id=principal.user_id,
        )
    except ClassesError as error:
        raise _classes_http_error(error) from error
    return _reservation_response(item)


_ROUTINES_ERROR_STATUS: tuple[tuple[type[RoutinesError], int], ...] = (
    (InvalidRoutineData, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (EmptyRoutine, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (DuplicateRoutineExercise, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (InvalidMeasurement, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (InvalidGoalData, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (InvalidWorkoutData, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (ProgressPhotoTooLarge, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE),
    (InvalidProgressPhoto, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (ExerciseNotFound, status.HTTP_404_NOT_FOUND),
    (RoutineNotFound, status.HTTP_404_NOT_FOUND),
    (AssignmentNotFound, status.HTTP_404_NOT_FOUND),
    (WorkoutNotFound, status.HTTP_404_NOT_FOUND),
    (GoalNotFound, status.HTTP_404_NOT_FOUND),
    (ProgressPhotoNotFound, status.HTTP_404_NOT_FOUND),
    (MemberNotEligible, status.HTTP_404_NOT_FOUND),
    (DuplicateExercise, status.HTTP_409_CONFLICT),
    (ExerciseUnavailable, status.HTTP_409_CONFLICT),
    (DuplicateAssignment, status.HTTP_409_CONFLICT),
    (DuplicateActiveGoal, status.HTTP_409_CONFLICT),
    (InvalidRoutineState, status.HTTP_409_CONFLICT),
    (InvalidAssignmentState, status.HTTP_409_CONFLICT),
    (InvalidGoalState, status.HTTP_409_CONFLICT),
    (InvalidWorkoutState, status.HTTP_409_CONFLICT),
)


def _routines_http_error(error: RoutinesError) -> HTTPException:
    for error_type, code in _ROUTINES_ERROR_STATUS:
        if isinstance(error, error_type):
            return HTTPException(status_code=code, detail=str(error))
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))


def _exercise_response(item: ExerciseItem) -> ExerciseResponse:
    return ExerciseResponse(
        id=item.id,
        name=item.name,
        muscle_group=item.muscle_group,
        category=item.category,
        equipment_name=item.equipment_name,
        equipment_id=item.equipment_id,
        equipment_status=item.equipment_status,
        description=item.description,
        video_url=item.video_url,
        image_url=item.image_url,
        is_active=item.is_active,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _routine_line_response(item: RoutineLine) -> RoutineLineResponse:
    return RoutineLineResponse(
        id=item.id,
        exercise_id=item.exercise_id,
        exercise_name=item.exercise_name,
        muscle_group=item.muscle_group,
        category=item.category,
        equipment_status=item.equipment_status,
        position=item.position,
        sets=item.sets,
        reps=item.reps,
        rest_seconds=item.rest_seconds,
        load_note=item.load_note,
        notes=item.notes,
    )


def _routine_response(item: RoutineItemView) -> RoutineResponse:
    return RoutineResponse(
        id=item.id,
        name=item.name,
        trainer_id=item.trainer_id,
        trainer_name=item.trainer_name,
        objective=item.objective,
        notes=item.notes,
        status=item.status,
        version=item.version,
        item_count=item.item_count,
        active_assignments=item.active_assignments,
        created_at=item.created_at,
        updated_at=item.updated_at,
        archived_at=item.archived_at,
    )


def _routine_revision_response(item: RoutineRevisionItem) -> RoutineRevisionResponse:
    return RoutineRevisionResponse(
        version=item.version,
        reason=item.reason,
        item_count=item.item_count,
        changed_by=item.changed_by,
        created_at=item.created_at,
    )


def _routine_detail_response(detail: RoutineDetail) -> RoutineDetailResponse:
    return RoutineDetailResponse(
        routine=_routine_response(detail.routine),
        items=[_routine_line_response(item) for item in detail.items],
        revisions=[_routine_revision_response(item) for item in detail.revisions],
    )


def _assignment_response(item: AssignmentItem) -> AssignmentResponse:
    return AssignmentResponse(
        id=item.id,
        routine_id=item.routine_id,
        routine_name=item.routine_name,
        routine_version=item.routine_version,
        member_id=item.member_id,
        member_name=item.member_name,
        member_email=item.member_email,
        trainer_id=item.trainer_id,
        trainer_name=item.trainer_name,
        start_date=item.start_date,
        end_date=item.end_date,
        frequency_per_week=item.frequency_per_week,
        status=item.status,
        notes=item.notes,
        workouts_logged=item.workouts_logged,
        last_workout_at=item.last_workout_at,
        created_at=item.created_at,
        ended_at=item.ended_at,
    )


def _assignment_detail_response(detail: AssignmentDetail) -> AssignmentDetailResponse:
    return AssignmentDetailResponse(
        assignment=_assignment_response(detail.assignment),
        routine_version=detail.routine_version,
        plan=[_routine_line_response(item) for item in detail.plan],
    )


def _workout_response(item: WorkoutItem) -> WorkoutResponse:
    return WorkoutResponse(
        id=item.id,
        assignment_id=item.assignment_id,
        member_id=item.member_id,
        routine_id=item.routine_id,
        routine_version=item.routine_version,
        performed_at=item.performed_at,
        duration_minutes=item.duration_minutes,
        perceived_effort=item.perceived_effort,
        notes=item.notes,
        status=item.status,
        origin=item.origin,
        reviewed_at=item.reviewed_at,
        created_at=item.created_at,
        sets=[
            WorkoutSetResponse(
                exercise_id=workout_set.exercise_id,
                exercise_name=workout_set.exercise_name,
                position=workout_set.position,
                set_number=workout_set.set_number,
                reps=workout_set.reps,
                weight_kg=workout_set.weight_kg,
            )
            for workout_set in item.sets
        ],
    )


def _workout_set_inputs(sets: list[WorkoutSetRequest]) -> list[WorkoutSetInput]:
    return [
        WorkoutSetInput(
            exercise_id=item.exercise_id,
            set_number=item.set_number,
            reps=item.reps,
            weight_kg=item.weight_kg,
        )
        for item in sets
    ]


def _measurement_response(item: MeasurementItem) -> MeasurementResponse:
    return MeasurementResponse(
        id=item.id,
        member_id=item.member_id,
        measured_at=item.measured_at,
        weight_kg=item.weight_kg,
        waist_cm=item.waist_cm,
        chest_cm=item.chest_cm,
        body_fat_percent=item.body_fat_percent,
        notes=item.notes,
        origin=item.origin,
        created_at=item.created_at,
    )


def _progress_photo_response(
    item: ProgressPhotoItem, *, file_path: str | None = None
) -> ProgressPhotoResponse:
    return ProgressPhotoResponse(
        id=item.id,
        member_id=item.member_id,
        angle=item.angle,
        captured_at=item.captured_at,
        notes=item.notes,
        content_type=item.content_type,
        byte_size=item.byte_size,
        origin=item.origin,
        created_at=item.created_at,
        file_path=file_path,
    )


def _member_progress_photos_response(
    photos: MemberProgressPhotos,
) -> MemberProgressPhotosResponse:
    return MemberProgressPhotosResponse(
        items=[
            _progress_photo_response(item, file_path=progress_photo_link(item.id))
            for item in photos.items
        ],
        consent_recorded=photos.consent_recorded,
    )


def _goal_response(item: MemberGoalItem) -> MemberGoalResponse:
    return MemberGoalResponse(
        id=item.id,
        member_id=item.member_id,
        metric=item.metric,
        direction=item.direction,
        target_value=item.target_value,
        baseline_value=item.baseline_value,
        baseline_measured_at=item.baseline_measured_at,
        target_date=item.target_date,
        notes=item.notes,
        status=item.status,
        origin=item.origin,
        current_value=item.current_value,
        current_measured_at=item.current_measured_at,
        progress_percent=item.progress_percent,
        achieved=item.achieved,
        achieved_value=item.achieved_value,
        achieved_at=item.achieved_at,
        cancelled_at=item.cancelled_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _routine_lines_payload(items: list[RoutineLineRequest]) -> list[RoutineItemInput]:
    return [
        RoutineItemInput(
            exercise_id=line.exercise_id,
            sets=line.sets,
            reps=line.reps,
            rest_seconds=line.rest_seconds,
            load_note=line.load_note,
            notes=line.notes,
        )
        for line in items
    ]


@app.get("/admin/routines/overview", response_model=RoutinesOverviewResponse, tags=["routines"])
def routines_overview_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.read"))],
) -> RoutinesOverviewResponse:
    overview: ModuleOverview = module_overview(session)
    return RoutinesOverviewResponse(
        exercises=overview.exercises,
        routines_active=overview.routines_active,
        routines_archived=overview.routines_archived,
        assignments_active=overview.assignments_active,
        workouts_last_7_days=overview.workouts_last_7_days,
    )


@app.get("/admin/routines/exercises", response_model=ExerciseDirectoryResponse, tags=["routines"])
def list_exercises_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.read"))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    search: Annotated[str | None, Query(max_length=120)] = None,
    muscle_group: Annotated[str | None, Query(max_length=60)] = None,
    category: Annotated[str | None, Query(max_length=60)] = None,
    include_inactive: Annotated[bool, Query()] = False,
) -> ExerciseDirectoryResponse:
    directory: ExercisePage = list_exercises(
        session,
        search=search,
        muscle_group=muscle_group,
        category=category,
        include_inactive=include_inactive,
        page=page,
        page_size=page_size,
    )
    return ExerciseDirectoryResponse(
        items=[_exercise_response(item) for item in directory.items],
        total=directory.total,
        page=directory.page,
        page_size=directory.page_size,
        pages=directory.pages,
        muscle_groups=directory.muscle_groups,
        categories=directory.categories,
    )


@app.post(
    "/admin/routines/exercises",
    response_model=ExerciseResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["routines"],
)
def create_exercise_endpoint(
    request: CreateExerciseRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.manage"))],
) -> ExerciseResponse:
    try:
        item = create_exercise(
            session,
            name=request.name,
            muscle_group=request.muscle_group,
            category=request.category,
            equipment_name=request.equipment_name,
            equipment_id=request.equipment_id,
            description=request.description,
            video_url=request.video_url,
            image_url=request.image_url,
            actor_id=principal.user_id,
        )
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return _exercise_response(item)


@app.patch(
    "/admin/routines/exercises/{exercise_id}",
    response_model=ExerciseResponse,
    tags=["routines"],
)
def update_exercise_endpoint(
    exercise_id: UUID,
    request: UpdateExerciseRequest,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.manage"))],
) -> ExerciseResponse:
    provided = request.model_fields_set
    try:
        item = update_exercise(
            session,
            exercise_id,
            name=request.name,
            muscle_group=request.muscle_group,
            category=request.category,
            equipment_name=request.equipment_name if "equipment_name" in provided else ROUTINES_UNSET,
            equipment_id=request.equipment_id if "equipment_id" in provided else ROUTINES_UNSET,
            description=request.description if "description" in provided else ROUTINES_UNSET,
            video_url=request.video_url if "video_url" in provided else ROUTINES_UNSET,
            image_url=request.image_url if "image_url" in provided else ROUTINES_UNSET,
            is_active=request.is_active,
        )
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return _exercise_response(item)


@app.get("/admin/routines/assignments", response_model=AssignmentDirectoryResponse, tags=["routines"])
def list_assignments_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.read"))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    member_id: Annotated[UUID | None, Query()] = None,
    routine_id: Annotated[UUID | None, Query()] = None,
    trainer_id: Annotated[UUID | None, Query()] = None,
    status_filter: Annotated[Literal["active", "completed", "cancelled"] | None, Query(alias="status")] = None,
    search: Annotated[str | None, Query(max_length=120)] = None,
) -> AssignmentDirectoryResponse:
    directory = list_assignments(
        session,
        member_id=member_id,
        routine_id=routine_id,
        trainer_id=trainer_id,
        status=status_filter,
        search=search,
        page=page,
        page_size=page_size,
    )
    return AssignmentDirectoryResponse(
        items=[_assignment_response(item) for item in directory.items],
        total=directory.total,
        page=directory.page,
        page_size=directory.page_size,
        pages=directory.pages,
        summary=AssignmentSummaryResponse(
            total=directory.summary.total,
            active=directory.summary.active,
            completed=directory.summary.completed,
            cancelled=directory.summary.cancelled,
        ),
    )


@app.post(
    "/admin/routines/assignments",
    response_model=AssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["routines"],
)
def create_assignment_endpoint(
    request: CreateAssignmentRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.manage"))],
) -> AssignmentResponse:
    try:
        item = create_assignment(
            session,
            routine_id=request.routine_id,
            member_id=request.member_id,
            start_date=request.start_date,
            end_date=request.end_date,
            frequency_per_week=request.frequency_per_week,
            trainer_id=request.trainer_id,
            notes=request.notes,
            actor_id=principal.user_id,
        )
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return _assignment_response(item)


@app.get(
    "/admin/routines/assignments/{assignment_id}",
    response_model=AssignmentDetailResponse,
    tags=["routines"],
)
def get_assignment_endpoint(
    assignment_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.read"))],
) -> AssignmentDetailResponse:
    try:
        detail = get_assignment(session, assignment_id)
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return _assignment_detail_response(detail)


@app.post(
    "/admin/routines/assignments/{assignment_id}/complete",
    response_model=AssignmentResponse,
    tags=["routines"],
)
def complete_assignment_endpoint(
    assignment_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.manage"))],
) -> AssignmentResponse:
    try:
        item = complete_assignment(session, assignment_id)
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return _assignment_response(item)


@app.post(
    "/admin/routines/assignments/{assignment_id}/cancel",
    response_model=AssignmentResponse,
    tags=["routines"],
)
def cancel_assignment_endpoint(
    assignment_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.manage"))],
) -> AssignmentResponse:
    try:
        item = cancel_assignment(session, assignment_id)
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return _assignment_response(item)


@app.get(
    "/admin/routines/assignments/{assignment_id}/workouts",
    response_model=list[WorkoutResponse],
    tags=["routines"],
)
def list_workouts_endpoint(
    assignment_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.read"))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    status_filter: Annotated[Literal["logged", "reviewed"] | None, Query(alias="status")] = None,
) -> list[WorkoutResponse]:
    workouts = list_workouts(
        session,
        assignment_id=assignment_id,
        status=status_filter,
        page=page,
        page_size=page_size,
    )
    return [_workout_response(item) for item in workouts]


@app.post(
    "/admin/routines/assignments/{assignment_id}/workouts",
    response_model=WorkoutResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["routines"],
)
def log_workout_endpoint(
    assignment_id: UUID,
    request: LogWorkoutRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.manage"))],
) -> WorkoutResponse:
    try:
        item = log_workout(
            session,
            assignment_id,
            performed_at=request.performed_at,
            duration_minutes=request.duration_minutes,
            perceived_effort=request.perceived_effort,
            notes=request.notes,
            sets=_workout_set_inputs(request.sets),
            actor_id=principal.user_id,
        )
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return _workout_response(item)


@app.post(
    "/admin/routines/workouts/{workout_id}/review",
    response_model=WorkoutResponse,
    tags=["routines"],
)
def review_workout_endpoint(
    workout_id: UUID,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.manage"))],
) -> WorkoutResponse:
    try:
        item = review_workout(session, workout_id, actor_id=principal.user_id)
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return _workout_response(item)


@app.get(
    "/admin/routines/members/{member_id}/progress",
    response_model=MemberProgressResponse,
    tags=["routines"],
)
def member_progress_endpoint(
    member_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.read"))],
) -> MemberProgressResponse:
    try:
        progress: MemberProgress = member_progress(session, member_id)
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return MemberProgressResponse(
        member_id=progress.member_id,
        member_name=progress.member_name,
        active_assignments=progress.active_assignments,
        workouts_total=progress.workouts_total,
        workouts_last_30_days=progress.workouts_last_30_days,
        last_workout_at=progress.last_workout_at,
        latest_measurement=(
            _measurement_response(progress.latest_measurement)
            if progress.latest_measurement is not None
            else None
        ),
        measurements=[_measurement_response(item) for item in progress.measurements],
    )


@app.get(
    "/admin/routines/members/{member_id}/measurements",
    response_model=list[MeasurementResponse],
    tags=["routines"],
)
def list_measurements_endpoint(
    member_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.read"))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 36,
) -> list[MeasurementResponse]:
    try:
        measurements = list_measurements(session, member_id, page=page, page_size=page_size)
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return [_measurement_response(item) for item in measurements]


@app.post(
    "/admin/routines/members/{member_id}/measurements",
    response_model=MeasurementResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["routines"],
)
def record_measurement_endpoint(
    member_id: UUID,
    request: RecordMeasurementRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.manage"))],
) -> MeasurementResponse:
    try:
        item = record_measurement(
            session,
            member_id,
            measured_at=request.measured_at,
            weight_kg=request.weight_kg,
            waist_cm=request.waist_cm,
            chest_cm=request.chest_cm,
            body_fat_percent=request.body_fat_percent,
            notes=request.notes,
            actor_id=principal.user_id,
        )
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return _measurement_response(item)


@app.get(
    "/admin/routines/members/{member_id}/photos",
    response_model=list[ProgressPhotoResponse],
    tags=["routines"],
)
def list_progress_photos_endpoint(
    member_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.read"))],
) -> list[ProgressPhotoResponse]:
    try:
        photos = list_progress_photos(session, member_id)
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return [_progress_photo_response(item) for item in photos]


@app.post(
    "/admin/routines/members/{member_id}/photos",
    response_model=ProgressPhotoResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["routines"],
)
async def upload_progress_photo_endpoint(
    member_id: UUID,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.manage"))],
    photo: Annotated[UploadFile, File(description="Imagen JPEG, PNG o WebP de hasta 8 MB")],
    angle: Annotated[str, Form()],
    captured_at: Annotated[datetime | None, Form()] = None,
    notes: Annotated[str | None, Form()] = None,
) -> ProgressPhotoResponse:
    content_type = photo.content_type
    data = await photo.read(MAX_PROGRESS_PHOTO_BYTES + 1)
    await photo.close()
    try:
        item = record_progress_photo(
            session,
            member_id,
            data=data,
            content_type=content_type,
            angle=angle,
            captured_at=captured_at,
            notes=notes,
            actor_id=principal.user_id,
        )
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return _progress_photo_response(item)


@app.get("/admin/routines/photos/{photo_id}/file", tags=["routines"])
def progress_photo_file_endpoint(
    photo_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.read"))],
) -> FileResponse:
    try:
        stored = progress_photo_file(session, photo_id)
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    filename = (
        f"foto-progreso-{stored.photo.captured_at.date().isoformat()}-"
        f"{stored.photo.angle}{stored.path.suffix}"
    )
    return FileResponse(
        stored.path,
        media_type=stored.photo.content_type,
        filename=filename,
        content_disposition_type="inline",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.delete(
    "/admin/routines/photos/{photo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["routines"],
)
def delete_progress_photo_endpoint(
    photo_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.manage"))],
) -> Response:
    try:
        delete_progress_photo(session, photo_id)
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get(
    "/admin/routines/members/{member_id}/goals",
    response_model=list[MemberGoalResponse],
    tags=["routines"],
)
def list_member_goals_endpoint(
    member_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.read"))],
    status_filter: Annotated[Literal["active", "achieved", "cancelled"] | None, Query(alias="status")] = None,
) -> list[MemberGoalResponse]:
    try:
        goals = list_member_goals(session, member_id, status=status_filter)
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return [_goal_response(item) for item in goals]


@app.post(
    "/admin/routines/members/{member_id}/goals",
    response_model=MemberGoalResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["routines"],
)
def create_member_goal_endpoint(
    member_id: UUID,
    request: CreateMemberGoalRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.manage"))],
) -> MemberGoalResponse:
    try:
        item = create_member_goal(
            session,
            member_id,
            metric=request.metric,
            direction=request.direction,
            target_value=request.target_value,
            target_date=request.target_date,
            notes=request.notes,
            actor_id=principal.user_id,
        )
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return _goal_response(item)


@app.patch(
    "/admin/routines/goals/{goal_id}",
    response_model=MemberGoalResponse,
    tags=["routines"],
)
def update_member_goal_endpoint(
    goal_id: UUID,
    request: UpdateMemberGoalRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.manage"))],
) -> MemberGoalResponse:
    provided = request.model_fields_set
    try:
        item = update_member_goal(
            session,
            goal_id,
            target_value=request.target_value,
            target_date=request.target_date if "target_date" in provided else ROUTINES_UNSET,
            notes=request.notes if "notes" in provided else ROUTINES_UNSET,
            actor_id=principal.user_id,
        )
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return _goal_response(item)


@app.post(
    "/admin/routines/goals/{goal_id}/cancel",
    response_model=MemberGoalResponse,
    tags=["routines"],
)
def cancel_member_goal_endpoint(
    goal_id: UUID,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.manage"))],
) -> MemberGoalResponse:
    try:
        item = cancel_member_goal(session, goal_id, actor_id=principal.user_id)
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return _goal_response(item)


@app.get("/admin/routines", response_model=RoutineDirectoryResponse, tags=["routines"])
def list_routines_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.read"))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    search: Annotated[str | None, Query(max_length=120)] = None,
    status_filter: Annotated[Literal["draft", "active", "archived"] | None, Query(alias="status")] = None,
    trainer_id: Annotated[UUID | None, Query()] = None,
) -> RoutineDirectoryResponse:
    directory = list_routines(
        session,
        search=search,
        status=status_filter,
        trainer_id=trainer_id,
        page=page,
        page_size=page_size,
    )
    return RoutineDirectoryResponse(
        items=[_routine_response(item) for item in directory.items],
        total=directory.total,
        page=directory.page,
        page_size=directory.page_size,
        pages=directory.pages,
        summary=RoutineSummaryResponse(
            total=directory.summary.total,
            active=directory.summary.active,
            draft=directory.summary.draft,
            archived=directory.summary.archived,
        ),
    )


@app.post(
    "/admin/routines",
    response_model=RoutineDetailResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["routines"],
)
def create_routine_endpoint(
    request: CreateRoutineRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.manage"))],
) -> RoutineDetailResponse:
    try:
        detail = create_routine(
            session,
            name=request.name,
            items=_routine_lines_payload(request.items),
            trainer_id=request.trainer_id,
            objective=request.objective,
            notes=request.notes,
            actor_id=principal.user_id,
        )
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return _routine_detail_response(detail)


@app.get("/admin/routines/{routine_id}", response_model=RoutineDetailResponse, tags=["routines"])
def get_routine_endpoint(
    routine_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.read"))],
    version: Annotated[int | None, Query(ge=1)] = None,
) -> RoutineDetailResponse:
    try:
        detail = get_routine(session, routine_id, version=version)
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return _routine_detail_response(detail)


@app.patch("/admin/routines/{routine_id}", response_model=RoutineDetailResponse, tags=["routines"])
def update_routine_endpoint(
    routine_id: UUID,
    request: UpdateRoutineRequest,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.manage"))],
) -> RoutineDetailResponse:
    provided = request.model_fields_set
    try:
        detail = update_routine(
            session,
            routine_id,
            name=request.name,
            trainer_id=request.trainer_id if "trainer_id" in provided else ROUTINES_UNSET,
            objective=request.objective if "objective" in provided else ROUTINES_UNSET,
            notes=request.notes if "notes" in provided else ROUTINES_UNSET,
            status=request.status,
        )
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return _routine_detail_response(detail)


@app.put("/admin/routines/{routine_id}/items", response_model=RoutineDetailResponse, tags=["routines"])
def replace_routine_items_endpoint(
    routine_id: UUID,
    request: ReplaceRoutineItemsRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.manage"))],
) -> RoutineDetailResponse:
    try:
        detail = replace_routine_items(
            session,
            routine_id,
            items=_routine_lines_payload(request.items),
            reason=request.reason,
            actor_id=principal.user_id,
        )
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return _routine_detail_response(detail)


@app.post("/admin/routines/{routine_id}/archive", response_model=RoutineDetailResponse, tags=["routines"])
def archive_routine_endpoint(
    routine_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("routines.manage"))],
) -> RoutineDetailResponse:
    try:
        detail = archive_routine(session, routine_id)
    except RoutinesError as error:
        raise _routines_http_error(error) from error
    return _routine_detail_response(detail)


_MAINTENANCE_ERROR_STATUS: tuple[tuple[type[MaintenanceError], int], ...] = (
    (InvalidEquipmentData, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (InvalidTicketData, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (InvalidRecordData, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (InvalidChecklistData, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (EquipmentNotFound, status.HTTP_404_NOT_FOUND),
    (TicketNotFound, status.HTTP_404_NOT_FOUND),
    (DuplicateSerial, status.HTTP_409_CONFLICT),
    (InvalidEquipmentState, status.HTTP_409_CONFLICT),
    (InvalidTicketState, status.HTTP_409_CONFLICT),
)


def _maintenance_http_error(error: MaintenanceError) -> HTTPException:
    for error_type, code in _MAINTENANCE_ERROR_STATUS:
        if isinstance(error, error_type):
            return HTTPException(status_code=code, detail=str(error))
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))


def _equipment_response(item: EquipmentItem) -> EquipmentResponse:
    return EquipmentResponse(
        id=item.id,
        name=item.name,
        category=item.category,
        brand=item.brand,
        model=item.model,
        serial_number=item.serial_number,
        location=item.location,
        acquired_on=item.acquired_on,
        useful_life_months=item.useful_life_months,
        purchase_cost_cents=item.purchase_cost_cents,
        status=item.status,
        next_preventive_due=item.next_preventive_due,
        notes=item.notes,
        retired_at=item.retired_at,
        open_tickets=item.open_tickets,
        last_maintenance_at=item.last_maintenance_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _equipment_choice_response(item: EquipmentChoice) -> EquipmentChoiceResponse:
    return EquipmentChoiceResponse(
        id=item.id, name=item.name, location=item.location, status=item.status
    )


def _equipment_summary_response(summary: EquipmentSummary) -> EquipmentSummaryResponse:
    return EquipmentSummaryResponse(
        total=summary.total,
        operational=summary.operational,
        maintenance=summary.maintenance,
        out_of_service=summary.out_of_service,
        inspection=summary.inspection,
        retired=summary.retired,
    )


def _ticket_response(item: TicketItem) -> TicketResponse:
    return TicketResponse(
        id=item.id,
        code=item.code,
        equipment_id=item.equipment_id,
        equipment_name=item.equipment_name,
        equipment_status=item.equipment_status,
        kind=item.kind,
        severity=item.severity,
        title=item.title,
        description=item.description,
        status=item.status,
        reported_by=item.reported_by,
        reporter_email=item.reporter_email,
        reported_at=item.reported_at,
        assigned_to=item.assigned_to,
        assignee_name=item.assignee_name,
        assigned_at=item.assigned_at,
        scheduled_for=item.scheduled_for,
        started_at=item.started_at,
        resolved_at=item.resolved_at,
        resolution_notes=item.resolution_notes,
        cost_cents=item.cost_cents,
        blocked_equipment=item.blocked_equipment,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _ticket_summary_response(summary: TicketSummary) -> TicketSummaryResponse:
    return TicketSummaryResponse(
        total=summary.total,
        open=summary.open,
        assigned=summary.assigned,
        in_progress=summary.in_progress,
        resolved=summary.resolved,
        cancelled=summary.cancelled,
        critical_open=summary.critical_open,
    )


def _maintenance_record_response(item: MaintenanceRecordItem) -> MaintenanceRecordResponse:
    return MaintenanceRecordResponse(
        id=item.id,
        equipment_id=item.equipment_id,
        equipment_name=item.equipment_name,
        ticket_id=item.ticket_id,
        kind=item.kind,
        summary=item.summary,
        notes=item.notes,
        performed_at=item.performed_at,
        cost_cents=item.cost_cents,
        technician_id=item.technician_id,
        technician_name=item.technician_name,
        created_at=item.created_at,
    )


def _checklist_response(item: ChecklistItem) -> ChecklistResponse:
    return ChecklistResponse(
        id=item.id,
        area=item.area,
        result=item.result,
        observations=item.observations,
        performed_at=item.performed_at,
        performed_by=item.performed_by,
        performer_email=item.performer_email,
        created_at=item.created_at,
    )


def _equipment_detail_response(detail: EquipmentDetail) -> EquipmentDetailResponse:
    return EquipmentDetailResponse(
        equipment=_equipment_response(detail.equipment),
        tickets=[_ticket_response(ticket) for ticket in detail.tickets],
        records=[_maintenance_record_response(record) for record in detail.records],
        exercises=[
            LinkedExerciseResponse(id=item.id, name=item.name, muscle_group=item.muscle_group)
            for item in detail.exercises
        ],
    )


def _ticket_detail_response(detail: TicketDetail) -> TicketDetailResponse:
    return TicketDetailResponse(
        ticket=_ticket_response(detail.ticket),
        record=(
            _maintenance_record_response(detail.record)
            if detail.record is not None
            else None
        ),
    )


@app.get(
    "/admin/maintenance/overview",
    response_model=MaintenanceOverviewResponse,
    tags=["maintenance"],
)
def maintenance_overview_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("maintenance.read"))],
) -> MaintenanceOverviewResponse:
    overview: MaintenanceOverview = maintenance_overview(session)
    return MaintenanceOverviewResponse(
        equipment_total=overview.equipment_total,
        operational=overview.operational,
        maintenance=overview.maintenance,
        out_of_service=overview.out_of_service,
        tickets_open=overview.tickets_open,
        tickets_critical=overview.tickets_critical,
        preventives_due=overview.preventives_due,
        records_last_30_days=overview.records_last_30_days,
    )


@app.get(
    "/admin/maintenance/equipment",
    response_model=EquipmentDirectoryResponse,
    tags=["maintenance"],
)
def list_equipment_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("maintenance.read"))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    search: Annotated[str | None, Query(max_length=120)] = None,
    status_filter: Annotated[str | None, Query(alias="status", max_length=20)] = None,
    category: Annotated[str | None, Query(max_length=60)] = None,
    location: Annotated[str | None, Query(max_length=80)] = None,
    include_retired: Annotated[bool, Query()] = False,
) -> EquipmentDirectoryResponse:
    directory: EquipmentPage = list_equipment(
        session,
        search=search,
        status=status_filter,
        category=category,
        location=location,
        include_retired=include_retired,
        page=page,
        page_size=page_size,
    )
    return EquipmentDirectoryResponse(
        items=[_equipment_response(item) for item in directory.items],
        total=directory.total,
        page=directory.page,
        page_size=directory.page_size,
        pages=directory.pages,
        summary=_equipment_summary_response(directory.summary),
        categories=directory.categories,
        locations=directory.locations,
    )


@app.get(
    "/admin/maintenance/equipment/options",
    response_model=list[EquipmentChoiceResponse],
    tags=["maintenance"],
)
def list_equipment_options_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("maintenance.read"))],
) -> list[EquipmentChoiceResponse]:
    return [_equipment_choice_response(item) for item in equipment_choices(session)]


@app.post(
    "/admin/maintenance/equipment",
    response_model=EquipmentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["maintenance"],
)
def create_equipment_endpoint(
    request: CreateEquipmentRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("maintenance.manage"))],
) -> EquipmentResponse:
    try:
        item = create_equipment(
            session,
            name=request.name,
            category=request.category,
            brand=request.brand,
            model=request.model,
            serial_number=request.serial_number,
            location=request.location,
            acquired_on=request.acquired_on,
            useful_life_months=request.useful_life_months,
            purchase_cost_cents=request.purchase_cost_cents,
            notes=request.notes,
            next_preventive_due=request.next_preventive_due,
            actor_id=principal.user_id,
        )
    except MaintenanceError as error:
        raise _maintenance_http_error(error) from error
    return _equipment_response(item)


@app.get(
    "/admin/maintenance/equipment/{equipment_id}",
    response_model=EquipmentDetailResponse,
    tags=["maintenance"],
)
def get_equipment_endpoint(
    equipment_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("maintenance.read"))],
) -> EquipmentDetailResponse:
    try:
        detail = get_equipment(session, equipment_id)
    except MaintenanceError as error:
        raise _maintenance_http_error(error) from error
    return _equipment_detail_response(detail)


@app.patch(
    "/admin/maintenance/equipment/{equipment_id}",
    response_model=EquipmentResponse,
    tags=["maintenance"],
)
def update_equipment_endpoint(
    equipment_id: UUID,
    request: UpdateEquipmentRequest,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("maintenance.manage"))],
) -> EquipmentResponse:
    provided = request.model_fields_set
    try:
        item = update_equipment(
            session,
            equipment_id,
            name=request.name,
            category=request.category,
            brand=request.brand if "brand" in provided else MAINTENANCE_UNSET,
            model=request.model if "model" in provided else MAINTENANCE_UNSET,
            serial_number=request.serial_number if "serial_number" in provided else MAINTENANCE_UNSET,
            location=request.location if "location" in provided else MAINTENANCE_UNSET,
            acquired_on=request.acquired_on if "acquired_on" in provided else MAINTENANCE_UNSET,
            useful_life_months=(
                request.useful_life_months if "useful_life_months" in provided else MAINTENANCE_UNSET
            ),
            purchase_cost_cents=request.purchase_cost_cents,
            notes=request.notes if "notes" in provided else MAINTENANCE_UNSET,
            next_preventive_due=(
                request.next_preventive_due if "next_preventive_due" in provided else MAINTENANCE_UNSET
            ),
        )
    except MaintenanceError as error:
        raise _maintenance_http_error(error) from error
    return _equipment_response(item)


@app.post(
    "/admin/maintenance/equipment/{equipment_id}/status",
    response_model=EquipmentResponse,
    tags=["maintenance"],
)
def set_equipment_status_endpoint(
    equipment_id: UUID,
    request: SetEquipmentStatusRequest,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("maintenance.report"))],
) -> EquipmentResponse:
    try:
        item = set_equipment_status(session, equipment_id, status=request.status)
    except MaintenanceError as error:
        raise _maintenance_http_error(error) from error
    return _equipment_response(item)


@app.post(
    "/admin/maintenance/equipment/{equipment_id}/retire",
    response_model=EquipmentResponse,
    tags=["maintenance"],
)
def retire_equipment_endpoint(
    equipment_id: UUID,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("maintenance.manage"))],
) -> EquipmentResponse:
    try:
        item = retire_equipment(session, equipment_id, actor_id=principal.user_id)
    except MaintenanceError as error:
        raise _maintenance_http_error(error) from error
    return _equipment_response(item)


@app.get(
    "/admin/maintenance/equipment/{equipment_id}/records",
    response_model=list[MaintenanceRecordResponse],
    tags=["maintenance"],
)
def list_equipment_records_endpoint(
    equipment_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("maintenance.read"))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[MaintenanceRecordResponse]:
    directory: RecordPage = list_records(
        session, equipment_id=equipment_id, page=page, page_size=page_size
    )
    return [_maintenance_record_response(item) for item in directory.items]


@app.post(
    "/admin/maintenance/equipment/{equipment_id}/records",
    response_model=MaintenanceRecordResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["maintenance"],
)
def record_maintenance_endpoint(
    equipment_id: UUID,
    request: RecordMaintenanceRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("maintenance.manage"))],
) -> MaintenanceRecordResponse:
    try:
        item = record_maintenance(
            session,
            equipment_id=equipment_id,
            kind=request.kind,
            summary=request.summary,
            performed_at=request.performed_at,
            notes=request.notes,
            cost_cents=request.cost_cents,
            technician_id=request.technician_id,
            next_due_on=request.next_due_on,
            ticket_id=request.ticket_id,
            actor_id=principal.user_id,
        )
    except MaintenanceError as error:
        raise _maintenance_http_error(error) from error
    return _maintenance_record_response(item)


@app.get(
    "/admin/maintenance/tickets",
    response_model=TicketDirectoryResponse,
    tags=["maintenance"],
)
def list_tickets_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("maintenance.read"))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    search: Annotated[str | None, Query(max_length=120)] = None,
    status_filter: Annotated[str | None, Query(alias="status", max_length=20)] = None,
    severity: Annotated[str | None, Query(max_length=20)] = None,
    kind: Annotated[str | None, Query(max_length=20)] = None,
    equipment_id: Annotated[UUID | None, Query()] = None,
    open_only: Annotated[bool, Query()] = False,
) -> TicketDirectoryResponse:
    directory: TicketPage = list_tickets(
        session,
        search=search,
        status=status_filter,
        severity=severity,
        kind=kind,
        equipment_id=equipment_id,
        open_only=open_only,
        page=page,
        page_size=page_size,
    )
    return TicketDirectoryResponse(
        items=[_ticket_response(item) for item in directory.items],
        total=directory.total,
        page=directory.page,
        page_size=directory.page_size,
        pages=directory.pages,
        summary=_ticket_summary_response(directory.summary),
    )


@app.post(
    "/admin/maintenance/tickets",
    response_model=TicketResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["maintenance"],
)
def create_ticket_endpoint(
    request: CreateTicketRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("maintenance.report"))],
) -> TicketResponse:
    try:
        item = create_ticket(
            session,
            equipment_id=request.equipment_id,
            title=request.title,
            kind=request.kind,
            severity=request.severity,
            description=request.description,
            assigned_to=request.assigned_to,
            scheduled_for=request.scheduled_for,
            block_equipment=request.block_equipment,
            actor_id=principal.user_id,
        )
    except MaintenanceError as error:
        raise _maintenance_http_error(error) from error
    return _ticket_response(item)


@app.get(
    "/admin/maintenance/tickets/{ticket_id}",
    response_model=TicketDetailResponse,
    tags=["maintenance"],
)
def get_ticket_endpoint(
    ticket_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("maintenance.read"))],
) -> TicketDetailResponse:
    try:
        detail = get_ticket(session, ticket_id)
    except MaintenanceError as error:
        raise _maintenance_http_error(error) from error
    return _ticket_detail_response(detail)


@app.patch(
    "/admin/maintenance/tickets/{ticket_id}",
    response_model=TicketResponse,
    tags=["maintenance"],
)
def update_ticket_endpoint(
    ticket_id: UUID,
    request: UpdateTicketRequest,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("maintenance.manage"))],
) -> TicketResponse:
    provided = request.model_fields_set
    try:
        item = update_ticket(
            session,
            ticket_id,
            title=request.title,
            description=request.description if "description" in provided else MAINTENANCE_UNSET,
            kind=request.kind,
            severity=request.severity,
            assigned_to=request.assigned_to if "assigned_to" in provided else MAINTENANCE_UNSET,
            scheduled_for=(
                request.scheduled_for if "scheduled_for" in provided else MAINTENANCE_UNSET
            ),
            cost_cents=request.cost_cents,
        )
    except MaintenanceError as error:
        raise _maintenance_http_error(error) from error
    return _ticket_response(item)


@app.post(
    "/admin/maintenance/tickets/{ticket_id}/start",
    response_model=TicketResponse,
    tags=["maintenance"],
)
def start_ticket_endpoint(
    ticket_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("maintenance.manage"))],
) -> TicketResponse:
    try:
        item = start_ticket(session, ticket_id)
    except MaintenanceError as error:
        raise _maintenance_http_error(error) from error
    return _ticket_response(item)


@app.post(
    "/admin/maintenance/tickets/{ticket_id}/resolve",
    response_model=TicketDetailResponse,
    tags=["maintenance"],
)
def resolve_ticket_endpoint(
    ticket_id: UUID,
    request: ResolveTicketRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("maintenance.manage"))],
) -> TicketDetailResponse:
    try:
        detail = resolve_ticket(
            session,
            ticket_id,
            resolution_notes=request.resolution_notes,
            cost_cents=request.cost_cents,
            next_due_on=request.next_due_on,
            technician_id=request.technician_id,
            performed_at=request.performed_at,
            actor_id=principal.user_id,
        )
    except MaintenanceError as error:
        raise _maintenance_http_error(error) from error
    return _ticket_detail_response(detail)


@app.post(
    "/admin/maintenance/tickets/{ticket_id}/cancel",
    response_model=TicketResponse,
    tags=["maintenance"],
)
def cancel_ticket_endpoint(
    ticket_id: UUID,
    request: CancelTicketRequest,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("maintenance.manage"))],
) -> TicketResponse:
    try:
        item = cancel_ticket(session, ticket_id, reason=request.reason)
    except MaintenanceError as error:
        raise _maintenance_http_error(error) from error
    return _ticket_response(item)


@app.get(
    "/admin/maintenance/records",
    response_model=MaintenanceRecordDirectoryResponse,
    tags=["maintenance"],
)
def list_maintenance_records_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("maintenance.read"))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    kind: Annotated[str | None, Query(max_length=20)] = None,
    equipment_id: Annotated[UUID | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> MaintenanceRecordDirectoryResponse:
    directory: RecordPage = list_records(
        session,
        equipment_id=equipment_id,
        kind=kind,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return MaintenanceRecordDirectoryResponse(
        items=[_maintenance_record_response(item) for item in directory.items],
        total=directory.total,
        page=directory.page,
        page_size=directory.page_size,
        pages=directory.pages,
        total_cost_cents=directory.total_cost_cents,
    )


@app.get(
    "/admin/maintenance/checklists",
    response_model=ChecklistDirectoryResponse,
    tags=["maintenance"],
)
def list_checklists_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("maintenance.read"))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    area: Annotated[str | None, Query(max_length=80)] = None,
    result: Annotated[str | None, Query(max_length=20)] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> ChecklistDirectoryResponse:
    directory: ChecklistPage = list_checklists(
        session,
        area=area,
        result=result,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return ChecklistDirectoryResponse(
        items=[_checklist_response(item) for item in directory.items],
        total=directory.total,
        page=directory.page,
        page_size=directory.page_size,
        pages=directory.pages,
    )


@app.post(
    "/admin/maintenance/checklists",
    response_model=ChecklistResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["maintenance"],
)
def record_checklist_endpoint(
    request: RecordChecklistRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("maintenance.manage"))],
) -> ChecklistResponse:
    try:
        item = record_checklist(
            session,
            area=request.area,
            result=request.result,
            observations=request.observations,
            performed_at=request.performed_at,
            actor_id=principal.user_id,
        )
    except MaintenanceError as error:
        raise _maintenance_http_error(error) from error
    return _checklist_response(item)


@app.get(
    "/admin/maintenance/service-status",
    response_model=list[AreaServiceStatusResponse],
    tags=["maintenance"],
)
def maintenance_service_status_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("maintenance.read"))],
) -> list[AreaServiceStatusResponse]:
    return [
        AreaServiceStatusResponse(
            area=item.area,
            total=item.total,
            operational=item.operational,
            maintenance=item.maintenance,
            out_of_service=item.out_of_service,
            inspection=item.inspection,
            retired=item.retired,
            availability=item.availability,
        )
        for item in service_status(session)
    ]


@app.post("/admin/staff", status_code=status.HTTP_201_CREATED, tags=["staff administration"])
def create_staff_member(
    request: CreateEmployeeRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("staff.manage"))],
) -> dict[str, object]:
    employee = Employee(
        employee_number=request.employee_number.strip(),
        first_name=request.first_name.strip(),
        last_name=request.last_name.strip(),
        email=request.email.strip().casefold() if request.email else None,
        phone=request.phone,
        job_title=request.job_title.strip(),
    )
    session.add(employee)
    session.add(
        AuthEvent(
            user_id=principal.user_id,
            actor_id=principal.user_id,
            event_type="employee_created",
            result="success",
            reason_code=employee.employee_number,
        )
    )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee number or email already exists") from error
    session.refresh(employee)
    return {
        "id": employee.id,
        "employee_number": employee.employee_number,
        "first_name": employee.first_name,
        "last_name": employee.last_name,
        "email": employee.email,
        "job_title": employee.job_title,
        "status": employee.status,
    }


@app.post("/admin/users", status_code=status.HTTP_201_CREATED, tags=["staff administration"])
def create_user(
    request: CreateUserRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(get_current_principal)],
) -> CreatedUserResponse:
    for permission_code in ("staff.manage", "roles.manage"):
        try:
            require_permission(principal, permission_code)
        except PermissionDenied as error:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions") from error
    try:
        user = register_user(
            session,
            email=request.email,
            password=request.password,
            employee_id=request.employee_id,
            role_codes=tuple(request.role_codes),
            assigned_by=principal.user_id,
        )
    except IdentityError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return CreatedUserResponse(
        id=user.id,
        email=user.email,
        employee_id=user.employee_id,
        roles=list(request.role_codes),
    )


@app.post("/admin/users/{user_id}/roles", tags=["staff administration"])
def grant_user_role(
    user_id: UUID,
    request: RoleAssignmentRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("roles.manage"))],
) -> dict[str, str | UUID]:
    try:
        assignment = assign_role(
            session,
            user_id=user_id,
            role_code=request.role_code,
            assigned_by=principal.user_id,
        )
    except IdentityError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return {"assignment_id": assignment.id, "user_id": user_id, "role_code": request.role_code}


@app.delete("/admin/users/{user_id}/roles/{role_code}", status_code=status.HTTP_204_NO_CONTENT, tags=["staff administration"])
def remove_user_role(
    user_id: UUID,
    role_code: str,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("roles.manage"))],
) -> None:
    try:
        revoke_role(session, user_id=user_id, role_code=role_code, revoked_by=principal.user_id)
    except LastOwnerRequired as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except IdentityError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@app.post("/admin/roles/{role_code}/permissions", status_code=status.HTTP_204_NO_CONTENT, tags=["staff administration"])
def grant_role_permission_endpoint(
    role_code: str,
    request: RolePermissionRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("roles.manage"))],
) -> None:
    try:
        grant_role_permission(
            session,
            role_code=role_code,
            permission_code=request.permission_code,
            actor_id=principal.user_id,
        )
    except ImmutableRole as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except (RoleNotFound, PermissionNotFound) as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@app.delete("/admin/roles/{role_code}/permissions/{permission_code}", status_code=status.HTTP_204_NO_CONTENT, tags=["staff administration"])
def revoke_role_permission_endpoint(
    role_code: str,
    permission_code: str,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("roles.manage"))],
) -> None:
    try:
        revoke_role_permission(
            session,
            role_code=role_code,
            permission_code=permission_code,
            actor_id=principal.user_id,
        )
    except ImmutableRole as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except (RoleNotFound, PermissionNotFound) as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@app.patch("/admin/users/{user_id}", tags=["staff administration"])
def update_user_status(
    user_id: UUID,
    request: UpdateUserStatusRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("roles.manage"))],
) -> dict[str, object]:
    try:
        user = set_user_status(
            session,
            user_id=user_id,
            status=request.status,
            actor_id=principal.user_id,
        )
    except LastOwnerRequired as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except UserUnavailable as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except IdentityError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return {"id": user.id, "email": user.email, "status": user.status}


def _principal_response(principal: AuthenticatedUser) -> UserResponse:
    return UserResponse(
        id=principal.user_id,
        email=principal.email,
        employee_id=principal.employee_id,
        roles=list(principal.roles),
        permissions=sorted(principal.permissions),
    )


def _member_summary_response(member: AuthenticatedMember) -> MemberSessionSummaryResponse:
    return MemberSessionSummaryResponse(
        id=member.member_id,
        first_name=member.first_name,
        last_name=member.last_name,
        email=member.email or None,
        status=member.status,
    )


def _member_profile_response(profile: MemberProfile) -> MemberPortalProfileResponse:
    membership = (
        MemberSessionMembershipResponse(
            plan_name=profile.membership.plan_name,
            status=profile.membership.status,
            starts_at=profile.membership.starts_at,
            ends_at=profile.membership.ends_at,
            auto_renew=profile.membership.auto_renew,
            days_remaining=profile.membership.days_remaining,
        )
        if profile.membership is not None
        else None
    )
    return MemberPortalProfileResponse(
        id=profile.id,
        first_name=profile.first_name,
        last_name=profile.last_name,
        email=profile.email,
        phone=profile.phone,
        status=profile.status,
        member_since=profile.member_since,
        membership=membership,
        balance_cents=profile.balance_cents,
        access_enabled=profile.access_enabled,
    )


def _member_reservation_response(
    reservation: MemberReservationSummary,
) -> MemberClassReservationResponse:
    return MemberClassReservationResponse(
        id=reservation.id,
        session_id=reservation.session_id,
        status=reservation.status,
        waitlist_position=reservation.waitlist_position,
        late_cancellation=reservation.late_cancellation,
        created_at=reservation.created_at,
    )


def _member_class_response(item: MemberClassItem) -> MemberClassResponse:
    return MemberClassResponse(
        id=item.id,
        title=item.title,
        class_type_name=item.class_type_name,
        room_name=item.room_name,
        instructor_name=item.instructor_name,
        starts_at=item.starts_at,
        ends_at=item.ends_at,
        capacity=item.capacity,
        access_type=item.access_type,
        extra_price_cents=item.extra_price_cents,
        waitlist_enabled=item.waitlist_enabled,
        cancel_window_hours=item.cancel_window_hours,
        notes=item.notes,
        reserved_count=item.reserved_count,
        waitlist_count=item.waitlist_count,
        spots_left=item.spots_left,
        can_reserve=item.can_reserve,
        blocked_reason=item.blocked_reason,
        reservation=(
            _member_reservation_response(item.reservation)
            if item.reservation is not None
            else None
        ),
    )


def _member_assignment_response(
    item: MemberAssignmentSummary,
) -> MemberRoutineAssignmentResponse:
    return MemberRoutineAssignmentResponse(
        id=item.id,
        routine_id=item.routine_id,
        routine_name=item.routine_name,
        routine_version=item.routine_version,
        trainer_name=item.trainer_name,
        start_date=item.start_date,
        end_date=item.end_date,
        frequency_per_week=item.frequency_per_week,
        status=item.status,
        notes=item.notes,
        workouts_logged=item.workouts_logged,
        last_workout_at=item.last_workout_at,
        created_at=item.created_at,
        ended_at=item.ended_at,
    )


def _member_progress_response(progress: MemberProgressView) -> MemberPortalProgressResponse:
    return MemberPortalProgressResponse(
        workouts_total=progress.workouts_total,
        workouts_last_30_days=progress.workouts_last_30_days,
        last_workout_at=progress.last_workout_at,
        latest_measurement=(
            _measurement_response(progress.latest_measurement)
            if progress.latest_measurement is not None
            else None
        ),
        measurements=[_measurement_response(item) for item in progress.measurements],
        goals=[_goal_response(item) for item in progress.goals],
    )


def _member_payment_response(item: MemberPaymentItem) -> MemberPaymentResponse:
    return MemberPaymentResponse(
        id=item.id,
        amount_cents=item.amount_cents,
        currency=item.currency,
        method=item.method,
        paid_at=item.paid_at,
        period_starts_at=item.period_starts_at,
        period_ends_at=item.period_ends_at,
        plan_name=item.plan_name,
        note=item.note,
    )


def _member_invoice_response(item: MemberInvoiceItem) -> MemberInvoiceResponse:
    return MemberInvoiceResponse(
        id=item.id,
        series=item.series,
        folio=item.folio,
        folio_label=item.folio_label,
        status=item.status,
        origin_type=item.origin_type,
        origin_reference=item.origin_reference,
        currency=item.currency,
        subtotal_cents=item.subtotal_cents,
        tax_cents=item.tax_cents,
        total_cents=item.total_cents,
        payment_form=item.payment_form,
        payment_method=item.payment_method,
        uuid=item.uuid,
        is_simulated=item.is_simulated,
        issued_at=item.issued_at,
        stamped_at=item.stamped_at,
        cancelled_at=item.cancelled_at,
        created_at=item.created_at,
        pdf_path=item.pdf_path,
        xml_path=item.xml_path,
    )


def _member_billable_origin_response(
    item: BillableOriginItem,
) -> MemberBillableOriginResponse:
    return MemberBillableOriginResponse(
        origin_type=item.origin_type,
        origin_id=item.origin_id,
        reference=item.reference,
        occurred_at=item.occurred_at,
        total_cents=item.total_cents,
        description=item.description,
        payment_method=item.payment_method,
    )


def _member_fiscal_profile_response(
    profile: FiscalProfileView,
) -> MemberFiscalProfileResponse:
    return MemberFiscalProfileResponse(
        member_id=profile.member_id,
        rfc=profile.rfc,
        legal_name=profile.legal_name,
        tax_regime=profile.tax_regime,
        postal_code=profile.postal_code,
        cfdi_use=profile.cfdi_use,
        email=profile.email,
        updated_at=profile.updated_at,
    )


def _member_notification_response(item: MemberNotificationItem) -> MemberNotificationResponse:
    return MemberNotificationResponse(
        id=item.id,
        kind=item.kind,
        title=item.title,
        body=item.body,
        ref_id=item.ref_id,
        created_at=item.created_at,
        read_at=item.read_at,
    )


def _staff_notification_response(item: StaffNotificationItem) -> StaffNotificationResponse:
    return StaffNotificationResponse(
        id=item.id,
        kind=item.kind,
        title=item.title,
        body=item.body,
        ref_id=item.ref_id,
        created_at=item.created_at,
        read_at=item.read_at,
    )


_REPORT_ERROR_STATUS = (
    (InvalidReportPeriod, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (UnknownReport, status.HTTP_404_NOT_FOUND),
)


def _report_http_error(error: ReportError) -> HTTPException:
    for error_type, code in _REPORT_ERROR_STATUS:
        if isinstance(error, error_type):
            return HTTPException(status_code=code, detail=str(error))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))


def _report_period_response(period: ReportPeriod) -> ReportPeriodResponse:
    return ReportPeriodResponse(
        date_from=period.date_from,
        date_to=period.date_to,
        days=period.days,
        timezone=period.timezone_name,
    )


def _report_count_rows(rows: list) -> list[ReportCountRowResponse]:
    return [ReportCountRowResponse(label=row.label, count=row.count) for row in rows]


def _report_amount_rows(rows: list) -> list[ReportAmountRowResponse]:
    return [
        ReportAmountRowResponse(label=row.label, count=row.count, amount_cents=row.amount_cents)
        for row in rows
    ]


def _report_revenue_days(rows: list) -> list[ReportRevenueDayResponse]:
    return [
        ReportRevenueDayResponse(
            day=row.day,
            pos_cents=row.pos_cents,
            membership_cents=row.membership_cents,
            total_cents=row.total_cents,
            sales_count=row.sales_count,
            refunds_cents=row.refunds_cents,
        )
        for row in rows
    ]


def _report_access_days(rows: list) -> list[ReportAccessDayResponse]:
    return [
        ReportAccessDayResponse(day=row.day, total=row.total, denied=row.denied)
        for row in rows
    ]


def _report_class_days(rows: list) -> list[ReportClassDayResponse]:
    return [
        ReportClassDayResponse(day=row.day, sessions=row.sessions, attended=row.attended)
        for row in rows
    ]


def _report_event_days(rows: list) -> list[ReportEventDayResponse]:
    return [
        ReportEventDayResponse(
            day=row.day, activations=row.activations, terminations=row.terminations
        )
        for row in rows
    ]


def _report_plan_rows(rows: list) -> list[ReportPlanRowResponse]:
    return [
        ReportPlanRowResponse(
            plan_id=row.plan_id,
            name=row.name,
            price_cents=row.price_cents,
            duration_days=row.duration_days,
            active_count=row.active_count,
            monthly_cents=row.monthly_cents,
            recurring=row.recurring,
        )
        for row in rows
    ]


def _report_product_rows(rows: list) -> list[ReportProductRowResponse]:
    return [
        ReportProductRowResponse(
            product_id=row.product_id,
            name=row.name,
            sku=row.sku,
            quantity=row.quantity,
            amount_cents=row.amount_cents,
        )
        for row in rows
    ]


def _report_equipment_rows(rows: list) -> list[ReportEquipmentRowResponse]:
    return [
        ReportEquipmentRowResponse(
            equipment_id=row.equipment_id,
            name=row.name,
            category=row.category,
            location=row.location,
            status=row.status,
            records_count=row.records_count,
            cost_cents=row.cost_cents,
            open_tickets=row.open_tickets,
        )
        for row in rows
    ]


def _report_movement_rows(rows: list) -> list[ReportMovementRowResponse]:
    return [
        ReportMovementRowResponse(label=row.label, movements=row.movements, units=row.units)
        for row in rows
    ]


def _report_inventory_product_rows(rows: list) -> list[ReportInventoryProductRowResponse]:
    return [
        ReportInventoryProductRowResponse(
            product_id=row.product_id,
            name=row.name,
            sku=row.sku,
            category=row.category,
            quantity=row.quantity,
            cost_cents=row.cost_cents,
            price_cents=row.price_cents,
            cost_value_cents=row.cost_value_cents,
            retail_value_cents=row.retail_value_cents,
        )
        for row in rows
    ]


def _report_overview_response(payload: OverviewReport) -> ReportOverviewResponse:
    return ReportOverviewResponse(
        period=_report_period_response(payload.period),
        pos_cents=payload.pos_cents,
        pos_gross_cents=payload.pos_gross_cents,
        refunds_cents=payload.refunds_cents,
        refunds_count=payload.refunds_count,
        membership_cents=payload.membership_cents,
        sales_count=payload.sales_count,
        average_ticket_cents=payload.average_ticket_cents,
        payments_count=payload.payments_count,
        mrr_expected_cents=payload.mrr_expected_cents,
        maintenance_cost_cents=payload.maintenance_cost_cents,
        maintenance_records=payload.maintenance_records,
        access_total=payload.access_total,
        access_denied=payload.access_denied,
        access_manual=payload.access_manual,
        class_sessions=payload.class_sessions,
        class_capacity=payload.class_capacity,
        class_attended=payload.class_attended,
        class_no_show=payload.class_no_show,
        class_occupancy_percent=payload.class_occupancy_percent,
        workouts=payload.workouts,
        measurements=payload.measurements,
        members_by_status=_report_count_rows(payload.members_by_status),
        memberships_by_status=_report_count_rows(payload.memberships_by_status),
        new_members=payload.new_members,
        members_expiring=payload.members_expiring,
        equipment_by_status=_report_count_rows(payload.equipment_by_status),
        equipment_total=payload.equipment_total,
        tickets_open=payload.tickets_open,
        tickets_critical=payload.tickets_critical,
        revenue_by_day=_report_revenue_days(payload.revenue_by_day),
        access_by_day=_report_access_days(payload.access_by_day),
    )


def _report_ppd_receivables_response(summary) -> ReportPpdReceivablesResponse:
    return ReportPpdReceivablesResponse(
        as_of=summary.as_of,
        invoices=summary.invoices,
        total_cents=summary.total_cents,
        paid_cents=summary.paid_cents,
        outstanding_cents=summary.outstanding_cents,
        aging=ReportPpdAgingResponse(
            current_cents=summary.aging.current_cents,
            days_31_60_cents=summary.aging.days_31_60_cents,
            days_61_90_cents=summary.aging.days_61_90_cents,
            over_90_cents=summary.aging.over_90_cents,
        ),
        oldest_stamped_at=summary.oldest_stamped_at,
        stamped_complements=summary.stamped_complements,
        stamped_complement_cents=summary.stamped_complement_cents,
        requested_complements=summary.requested_complements,
        requested_complement_cents=summary.requested_complement_cents,
        failed_complements=summary.failed_complements,
        failed_complement_cents=summary.failed_complement_cents,
    )


def _report_revenue_response(payload: RevenueReport) -> RevenueReportResponse:
    return RevenueReportResponse(
        period=_report_period_response(payload.period),
        pos_cents=payload.pos_cents,
        pos_gross_cents=payload.pos_gross_cents,
        refunds_cents=payload.refunds_cents,
        refunds_count=payload.refunds_count,
        membership_cents=payload.membership_cents,
        sales_count=payload.sales_count,
        average_ticket_cents=payload.average_ticket_cents,
        payments_count=payload.payments_count,
        by_day=_report_revenue_days(payload.by_day),
        pos_by_method=_report_amount_rows(payload.pos_by_method),
        membership_by_method=_report_amount_rows(payload.membership_by_method),
        by_category=_report_amount_rows(payload.by_category),
        top_products=_report_product_rows(payload.top_products),
        cash_sessions_opened=payload.cash_sessions_opened,
        cash_sessions_closed=payload.cash_sessions_closed,
        cash_difference_cents=payload.cash_difference_cents,
        ppd_receivables=_report_ppd_receivables_response(payload.ppd_receivables),
    )


def _report_memberships_response(payload: MembershipReport) -> MembershipReportResponse:
    return MembershipReportResponse(
        period=_report_period_response(payload.period),
        members_total=payload.members_total,
        members_by_status=_report_count_rows(payload.members_by_status),
        memberships_by_status=_report_count_rows(payload.memberships_by_status),
        by_plan=_report_plan_rows(payload.by_plan),
        mrr_expected_cents=payload.mrr_expected_cents,
        payments_cents=payload.payments_cents,
        payments_count=payload.payments_count,
        events=_report_count_rows(payload.events),
        events_by_day=_report_event_days(payload.events_by_day),
        new_members=payload.new_members,
        members_expiring=payload.members_expiring,
    )


def _report_operations_response(payload: OperationsReport) -> OperationsReportResponse:
    return OperationsReportResponse(
        period=_report_period_response(payload.period),
        access_total=payload.access_total,
        access_authorized=payload.access_authorized,
        access_denied=payload.access_denied,
        access_manual=payload.access_manual,
        access_by_day=_report_access_days(payload.access_by_day),
        access_by_hour=_report_count_rows(payload.access_by_hour),
        class_sessions=payload.class_sessions,
        class_capacity=payload.class_capacity,
        class_reserved=payload.class_reserved,
        class_attended=payload.class_attended,
        class_no_show=payload.class_no_show,
        class_waitlist=payload.class_waitlist,
        class_cancelled=payload.class_cancelled,
        class_occupancy_percent=payload.class_occupancy_percent,
        classes_by_day=_report_class_days(payload.classes_by_day),
        workouts=payload.workouts,
        workout_minutes=payload.workout_minutes,
        measurements=payload.measurements,
        workouts_by_day=_report_count_rows(payload.workouts_by_day),
    )


def _report_maintenance_response(payload: MaintenanceReport) -> MaintenanceReportResponse:
    return MaintenanceReportResponse(
        period=_report_period_response(payload.period),
        cost_cents=payload.cost_cents,
        records_count=payload.records_count,
        by_kind=_report_amount_rows(payload.by_kind),
        by_equipment=_report_equipment_rows(payload.by_equipment),
        tickets_created=payload.tickets_created,
        tickets_by_status=_report_count_rows(payload.tickets_by_status),
        tickets_by_severity=_report_count_rows(payload.tickets_by_severity),
        equipment_by_status=_report_count_rows(payload.equipment_by_status),
        preventives_due=payload.preventives_due,
    )


def _report_inventory_response(payload: InventoryReport) -> InventoryReportResponse:
    return InventoryReportResponse(
        period=_report_period_response(payload.period),
        products_total=payload.products_total,
        products_active=payload.products_active,
        products_inactive=payload.products_inactive,
        stock_units=payload.stock_units,
        stock_value_cents=payload.stock_value_cents,
        retail_value_cents=payload.retail_value_cents,
        low_stock=payload.low_stock,
        out_of_stock=payload.out_of_stock,
        by_category=_report_amount_rows(payload.by_category),
        by_product=_report_inventory_product_rows(payload.by_product),
        suppliers_total=payload.suppliers_total,
        suppliers_active=payload.suppliers_active,
        open_orders=payload.open_orders,
        open_orders_value_cents=payload.open_orders_value_cents,
        movements_count=payload.movements_count,
        movements_by_type=_report_movement_rows(payload.movements_by_type),
        units_in=payload.units_in,
        units_out=payload.units_out,
        orders_created=payload.orders_created,
        orders_by_status=_report_count_rows(payload.orders_by_status),
        orders_value_cents=payload.orders_value_cents,
        orders_received=payload.orders_received,
        orders_received_value_cents=payload.orders_received_value_cents,
        by_supplier=_report_amount_rows(payload.by_supplier),
    )


@app.get(
    "/admin/reports/overview",
    response_model=ReportOverviewResponse,
    tags=["reports"],
)
def reports_overview_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("finance.read"))],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> ReportOverviewResponse:
    try:
        period = resolve_period(date_from, date_to)
    except ReportError as error:
        raise _report_http_error(error) from error
    return _report_overview_response(build_report(session, "overview", period))


@app.get(
    "/admin/reports/revenue",
    response_model=RevenueReportResponse,
    tags=["reports"],
)
def reports_revenue_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("finance.read"))],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> RevenueReportResponse:
    try:
        period = resolve_period(date_from, date_to)
    except ReportError as error:
        raise _report_http_error(error) from error
    return _report_revenue_response(build_report(session, "revenue", period))


@app.get(
    "/admin/reports/memberships",
    response_model=MembershipReportResponse,
    tags=["reports"],
)
def reports_memberships_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("finance.read"))],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> MembershipReportResponse:
    try:
        period = resolve_period(date_from, date_to)
    except ReportError as error:
        raise _report_http_error(error) from error
    return _report_memberships_response(build_report(session, "memberships", period))


@app.get(
    "/admin/reports/operations",
    response_model=OperationsReportResponse,
    tags=["reports"],
)
def reports_operations_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("finance.read"))],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> OperationsReportResponse:
    try:
        period = resolve_period(date_from, date_to)
    except ReportError as error:
        raise _report_http_error(error) from error
    return _report_operations_response(build_report(session, "operations", period))


@app.get(
    "/admin/reports/maintenance",
    response_model=MaintenanceReportResponse,
    tags=["reports"],
)
def reports_maintenance_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("finance.read"))],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> MaintenanceReportResponse:
    try:
        period = resolve_period(date_from, date_to)
    except ReportError as error:
        raise _report_http_error(error) from error
    return _report_maintenance_response(build_report(session, "maintenance", period))


@app.get(
    "/admin/reports/inventory",
    response_model=InventoryReportResponse,
    tags=["reports"],
)
def reports_inventory_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("finance.read"))],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> InventoryReportResponse:
    try:
        period = resolve_period(date_from, date_to)
    except ReportError as error:
        raise _report_http_error(error) from error
    return _report_inventory_response(build_report(session, "inventory", period))


@app.get("/admin/reports/export", tags=["reports"])
def reports_export_endpoint(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("finance.read"))],
    report: Annotated[str, Query()] = "overview",
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> Response:
    try:
        period = resolve_period(date_from, date_to)
        table = build_export(build_report(session, report, period), period)
    except ReportError as error:
        raise _report_http_error(error) from error
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(table.headers)
    writer.writerows(table.rows)
    filename = f"reporte-{report}-{period.date_from.isoformat()}-{period.date_to.isoformat()}.csv"
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


if PREVIEW_MODE:

    @app.post("/preview/bootstrap-owner", tags=["preview identity"])
    def preview_bootstrap_owner(request: BootstrapOwnerRequest, session: SessionDependency):
        try:
            user = bootstrap_initial_owner(session, email=request.email, password=request.password)
        except IdentityError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {"id": user.id, "email": user.email, "role": "owner"}

    @app.post("/preview/seed", response_model=PreviewSeedResponse, tags=["preview"])
    def create_preview_seed(session: SessionDependency) -> PreviewSeedResponse:
        member = Member(
            first_name="Ana",
            last_name="Demo",
            email=f"ana-{uuid4().hex[:12]}@example.test",
            phone="5550000000",
        )
        plan = Plan(
            code=f"DEMO-{uuid4().hex[:12]}",
            name="Membresía de demostración",
            duration_days=30,
            price_cents=50000,
            currency="MXN",
        )
        session.add_all([member, plan])
        session.flush()
        payment_method = PaymentMethod(
            member_id=member.id,
            provider="local-preview",
            provider_method_id=f"pm_{uuid4().hex}",
            encrypted_provider_token=b"not-a-real-payment-token",
            is_default=True,
        )
        session.add_all(
            [
                payment_method,
                MemberConsent(
                    member_id=member.id,
                    consent_type="privacy_notice",
                    document_version="preview-v1",
                    accepted_at=utc_now(),
                ),
            ]
        )
        session.commit()
        return PreviewSeedResponse(
            member_id=member.id,
            plan_id=plan.id,
            payment_method_id=payment_method.id,
            amount_cents=plan.price_cents,
            currency=plan.currency,
        )

    @app.post("/preview/first-charge", tags=["preview"])
    def preview_first_charge(request: FirstChargeRequest, session: SessionDependency):
        try:
            result = start_first_charge(
                session,
                PreviewGateway(request.outcome),
                member_id=request.member_id,
                plan_id=request.plan_id,
                payment_method_id=request.payment_method_id,
                idempotency_key=request.idempotency_key,
            )
        except BillingError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return result

    @app.post("/preview/retry/{failed_attempt_id}", tags=["preview"])
    def preview_retry(
        failed_attempt_id: UUID,
        request: RetryRequest,
        session: SessionDependency,
    ):
        try:
            return retry_failed_charge(
                session,
                PreviewGateway(request.outcome),
                failed_attempt_id=failed_attempt_id,
                idempotency_key=request.idempotency_key,
            )
        except BillingError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post(
        "/preview/webhooks/{payment_attempt_id}",
        tags=["preview"],
        description="Solo demostración local; no valida la firma de un proveedor ni debe usarse como webhook real.",
    )
    def preview_webhook(
        payment_attempt_id: UUID,
        request: WebhookRequest,
        session: SessionDependency,
    ):
        event_content = json.dumps(
            {"event_id": request.provider_event_id, "outcome": request.outcome},
            sort_keys=True,
            separators=(",", ":"),
        )
        webhook = VerifiedWebhook(
            provider="local-preview",
            provider_event_id=request.provider_event_id,
            event_type=f"charge.{request.outcome}",
            payload_sha256=sha256(event_content.encode("utf-8")).hexdigest(),
            payment_attempt_id=payment_attempt_id,
            outcome=ChargeOutcome(status=ChargeStatus(request.outcome), occurred_at=utc_now()),
        )
        try:
            return process_verified_webhook(session, webhook)
        except BillingError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post("/preview/access/snapshots/{member_id}", tags=["access preview"])
    def cache_access_snapshot(
        member_id: UUID,
        request: PreviewAccessSnapshotRequest,
        session: SessionDependency,
    ):
        if access_store is None:
            raise HTTPException(status_code=503, detail="Local access cache is unavailable")
        membership = session.exec(
            select(Membership)
            .where(Membership.member_id == member_id)
            .order_by(Membership.created_at.desc())
        ).first()
        if membership is None:
            raise HTTPException(status_code=404, detail="Membership was not found")
        snapshot_time = utc_now()
        snapshot = AccessSnapshot(
            member_id=member_id,
            membership_status=membership.status,
            membership_starts_at=_as_utc(membership.starts_at),
            membership_ends_at=_as_utc(membership.ends_at),
            blocking_debt=request.blocking_debt,
            cached_at=snapshot_time,
            valid_until=snapshot_time + timedelta(seconds=request.valid_for_seconds),
            allowed_windows=(
                tuple(
                    AccessWindow(
                        weekday=window.weekday,
                        starts_at=window.starts_at,
                        ends_at=window.ends_at,
                    )
                    for window in request.allowed_windows
                )
                if request.allowed_windows is not None
                else None
            ),
            daily_entry_limit=request.daily_entry_limit,
            entries_today=request.entries_today,
        )
        access_store.put_snapshot(snapshot)
        return {
            "member_id": str(member_id),
            "membership_status": snapshot.membership_status,
            "cached_at": snapshot.cached_at,
            "valid_until": snapshot.valid_until,
        }

    @app.post("/preview/access/check", tags=["access preview"])
    def preview_access_check(request: PreviewAccessCheckRequest, session: SessionDependency):
        if access_store is None:
            raise HTTPException(status_code=503, detail="Local access cache is unavailable")
        access_request = AccessRequest(
            event_id=request.event_id,
            member_id=request.member_id,
            reader_id=request.reader_id,
            direction=request.direction,
            occurred_at=request.occurred_at,
            current_occupancy=request.current_occupancy,
            max_occupancy=request.max_occupancy,
            offline=request.offline,
        )
        try:
            decision = access_store.decide_and_enqueue(
                access_request,
                timezone_name=os.getenv("APP_TIMEZONE", DEFAULT_TIMEZONE),
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        record_access_event(session, decision, reader_id=request.reader_id)
        return decision

    @app.get("/preview/access/outbox", tags=["access preview"])
    def preview_access_outbox():
        if access_store is None:
            raise HTTPException(status_code=503, detail="Local access cache is unavailable")
        return {"pending_events": access_store.pending_events()}

    @app.post("/preview/access/outbox/ack", tags=["access preview"])
    def acknowledge_preview_access_events(request: PreviewOutboxAckRequest):
        if access_store is None:
            raise HTTPException(status_code=503, detail="Local access cache is unavailable")
        return {"synchronized": access_store.mark_synchronized(request.event_ids)}


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
# --- Billing / CFDI ---------------------------------------------------------


class InvoiceCreateRequest(BaseModel):
    origin_type: Literal["sale", "membership_payment"]
    origin_id: UUID
    idempotency_key: str = Field(min_length=1, max_length=128)
    payment_form: str | None = Field(default=None, min_length=2, max_length=2)
    payment_method: Literal["PUE", "PPD"] | None = None
    receptor: FiscalDataRequest


class InvoiceCancelRequest(BaseModel):
    reason_code: Literal["01", "02", "03", "04"]
    replacement_uuid: str | None = Field(default=None, min_length=36, max_length=36)
    note: str | None = Field(default=None, max_length=300)


class InvoiceSendRequest(BaseModel):
    email: EmailStr | None = None


class GlobalInvoiceCreateRequest(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    idempotency_key: str = Field(min_length=1, max_length=128)


class CreditNoteCreateRequest(BaseModel):
    amount_cents: int = Field(gt=0)
    reason: Literal["return", "discount", "correction", "other"]
    note: str | None = Field(default=None, max_length=300)
    idempotency_key: str = Field(min_length=1, max_length=128)


class PaymentComplementCreateRequest(BaseModel):
    amount_cents: int = Field(gt=0)
    payment_form: str = Field(min_length=2, max_length=2)
    paid_on: date | None = None
    idempotency_key: str = Field(min_length=1, max_length=128)


class PaymentComplementCancelRequest(BaseModel):
    reason_code: Literal["01", "02", "03", "04"]
    replacement_uuid: str | None = Field(default=None, min_length=36, max_length=36)
    note: str | None = Field(default=None, max_length=300)


def _cfdi_http_status(error: CfdiError) -> int:
    if isinstance(
        error,
        (
            InvoiceNotFound,
            OriginNotFound,
            BillingMemberNotFound,
            PaymentComplementNotFound,
        ),
    ):
        return status.HTTP_404_NOT_FOUND
    if isinstance(
        error,
        (
            OriginAlreadyInvoiced,
            OriginNotInvoiceable,
            InvoiceIdempotencyConflict,
            InvoiceStateError,
            CancellationNotAllowed,
            GlobalInvoiceNoEligibleSales,
            GlobalInvoicePeriodConflict,
        ),
    ):
        return status.HTTP_409_CONFLICT
    if isinstance(error, (PacUnavailable, InvoiceEmailNotConfigured)):
        return status.HTTP_503_SERVICE_UNAVAILABLE
    if isinstance(error, (PacRejected, InvoiceDeliveryFailed)):
        return status.HTTP_502_BAD_GATEWAY
    if isinstance(error, FiscalDataInvalid):
        return status.HTTP_422_UNPROCESSABLE_ENTITY
    return status.HTTP_400_BAD_REQUEST


def _raise_cfdi_error(error: CfdiError) -> None:
    raise HTTPException(status_code=_cfdi_http_status(error), detail=str(error)) from error


@app.get("/admin/billing/summary", tags=["billing"])
def get_billing_summary(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("billing.read"))],
) -> dict[str, object]:
    summary = invoice_summary(session)
    return {
        "total": summary.total,
        "requested": summary.requested,
        "failed": summary.failed,
        "stamped": summary.stamped,
        "cancelled": summary.cancelled,
        "simulated": summary.simulated,
        "stamped_cents": summary.stamped_cents,
        "cancelled_cents": summary.cancelled_cents,
        "credit_notes": summary.credit_notes,
        "credit_note_cents": summary.credit_note_cents,
        "net_stamped_cents": summary.net_stamped_cents,
        "pending_cancellations": summary.pending_cancellations,
    }


@app.get("/admin/billing/receivables", tags=["billing"])
def get_ppd_receivables(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("billing.read"))],
    search: Annotated[str | None, Query(max_length=120)] = None,
    aging_bucket: Annotated[
        Literal["current", "days_31_60", "days_61_90", "over_90"] | None,
        Query(),
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    try:
        return list_ppd_receivables(
            session,
            search=search,
            aging_bucket=aging_bucket,
            page=page,
            page_size=page_size,
        )
    except CfdiError as error:
        _raise_cfdi_error(error)


@app.get("/admin/billing/global-invoices/eligible", tags=["billing"])
def get_global_invoice_eligibility(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("billing.read"))],
    year: Annotated[int, Query(ge=2000, le=2100)],
    month: Annotated[int, Query(ge=1, le=12)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    try:
        return list_global_invoice_eligibility(
            session,
            year=year,
            month=month,
            page=page,
            page_size=page_size,
        )
    except CfdiError as error:
        _raise_cfdi_error(error)


@app.post(
    "/admin/billing/global-invoices",
    status_code=status.HTTP_201_CREATED,
    tags=["billing"],
)
def request_global_invoice(
    payload: GlobalInvoiceCreateRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("billing.manage"))],
) -> dict[str, object]:
    try:
        invoice, created = create_global_invoice(
            session,
            year=payload.year,
            month=payload.month,
            idempotency_key=payload.idempotency_key,
            actor_id=principal.user_id,
        )
    except CfdiError as error:
        _raise_cfdi_error(error)
    return {"invoice": invoice, "idempotent_replay": not created}


@app.get("/admin/billing/invoices", tags=["billing"])
def get_invoices(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("billing.read"))],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    origin_type: Annotated[
        Literal["sale", "membership_payment", "global", "credit_note"] | None,
        Query(),
    ] = None,
    search: Annotated[str | None, Query(max_length=120)] = None,
    cancellation_pending: Annotated[bool | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    try:
        return list_invoices(
            session,
            status_filter=status_filter,
            origin_type=origin_type,
            search=search,
            cancellation_pending=cancellation_pending,
            page=page,
            page_size=page_size,
        )
    except CfdiError as error:
        _raise_cfdi_error(error)


@app.post("/admin/billing/invoices", status_code=status.HTTP_201_CREATED, tags=["billing"])
def request_invoice(
    payload: InvoiceCreateRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("billing.request"))],
) -> dict[str, object]:
    receptor = payload.receptor
    try:
        invoice, created = create_invoice(
            session,
            origin_type=payload.origin_type,
            origin_id=payload.origin_id,
            rfc=receptor.rfc,
            legal_name=receptor.legal_name,
            tax_regime=receptor.tax_regime,
            postal_code=receptor.postal_code,
            cfdi_use=receptor.cfdi_use,
            email=str(receptor.email) if receptor.email is not None else None,
            idempotency_key=payload.idempotency_key,
            payment_form=payload.payment_form,
            payment_method=payload.payment_method,
            actor_id=principal.user_id,
        )
    except CfdiError as error:
        _raise_cfdi_error(error)
    return {"invoice": invoice, "idempotent_replay": not created}


@app.post(
    "/admin/billing/invoices/{invoice_id}/credit-notes",
    status_code=status.HTTP_201_CREATED,
    tags=["billing"],
)
def request_credit_note(
    invoice_id: UUID,
    payload: CreditNoteCreateRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("billing.manage"))],
) -> dict[str, object]:
    try:
        invoice, created = create_credit_note(
            session,
            invoice_id=invoice_id,
            amount_cents=payload.amount_cents,
            reason=payload.reason,
            note=payload.note,
            idempotency_key=payload.idempotency_key,
            actor_id=principal.user_id,
        )
    except CfdiError as error:
        _raise_cfdi_error(error)
    return {"invoice": invoice, "idempotent_replay": not created}


@app.get("/admin/billing/invoices/{invoice_id}", tags=["billing"])
def get_invoice_detail(
    invoice_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("billing.read"))],
):
    try:
        return get_invoice(session, invoice_id)
    except CfdiError as error:
        _raise_cfdi_error(error)


@app.post("/admin/billing/invoices/{invoice_id}/stamp", tags=["billing"])
def stamp_invoice_detail(
    invoice_id: UUID,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("billing.manage"))],
):
    try:
        return stamp_invoice(session, invoice_id, actor_id=principal.user_id)
    except CfdiError as error:
        _raise_cfdi_error(error)


@app.post("/admin/billing/invoices/{invoice_id}/cancel", tags=["billing"])
def cancel_invoice_detail(
    invoice_id: UUID,
    payload: InvoiceCancelRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("billing.manage"))],
    response: Response,
):
    try:
        view = cancel_invoice(
            session,
            invoice_id,
            reason_code=payload.reason_code,
            replacement_uuid=payload.replacement_uuid,
            note=payload.note,
            actor_id=principal.user_id,
        )
    except CfdiError as error:
        _raise_cfdi_error(error)
    if view.cancellation_pending:
        # 202: the SAT accepted the request and is still processing it.
        response.status_code = status.HTTP_202_ACCEPTED
    return view


@app.post("/admin/billing/invoices/{invoice_id}/cancellation-check", tags=["billing"])
def check_invoice_cancellation(
    invoice_id: UUID,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("billing.manage"))],
):
    try:
        return refresh_cancellation_status(
            session, invoice_id, actor_id=principal.user_id
        )
    except CfdiError as error:
        _raise_cfdi_error(error)


@app.get("/admin/billing/invoices/{invoice_id}/xml", tags=["billing"])
def download_invoice_xml(
    invoice_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("billing.read"))],
) -> Response:
    try:
        filename, content = invoice_xml(session, invoice_id)
    except CfdiError as error:
        _raise_cfdi_error(error)
    return Response(
        content=content,
        media_type="application/xml; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@app.get("/admin/billing/invoices/{invoice_id}/pdf", tags=["billing"])
def download_invoice_pdf(
    invoice_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("billing.read"))],
) -> Response:
    try:
        filename, content = invoice_pdf(session, invoice_id)
    except CfdiError as error:
        _raise_cfdi_error(error)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@app.post("/admin/billing/invoices/{invoice_id}/send", tags=["billing"])
def send_invoice(
    invoice_id: UUID,
    session: SessionDependency,
    principal: Annotated[
        AuthenticatedUser, Depends(require_api_permission("billing.request"))
    ],
    payload: InvoiceSendRequest | None = None,
):
    try:
        return send_invoice_email(
            session,
            invoice_id,
            recipient=(
                str(payload.email)
                if payload is not None and payload.email is not None
                else None
            ),
            actor_id=principal.user_id,
        )
    except CfdiError as error:
        _raise_cfdi_error(error)


@app.post(
    "/admin/billing/invoices/{invoice_id}/payment-complements",
    status_code=status.HTTP_201_CREATED,
    tags=["billing"],
)
def request_payment_complement(
    invoice_id: UUID,
    payload: PaymentComplementCreateRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("billing.manage"))],
) -> dict[str, object]:
    try:
        payment, created = create_payment_complement(
            session,
            invoice_id=invoice_id,
            amount_cents=payload.amount_cents,
            payment_form=payload.payment_form,
            paid_on=payload.paid_on,
            idempotency_key=payload.idempotency_key,
            actor_id=principal.user_id,
        )
    except CfdiError as error:
        _raise_cfdi_error(error)
    return {"payment": payment, "idempotent_replay": not created}


@app.get("/admin/billing/payment-complements/{payment_id}", tags=["billing"])
def get_payment_complement_detail(
    payment_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("billing.read"))],
):
    try:
        return get_payment_complement(session, payment_id)
    except CfdiError as error:
        _raise_cfdi_error(error)


@app.post("/admin/billing/payment-complements/{payment_id}/stamp", tags=["billing"])
def stamp_payment_complement_detail(
    payment_id: UUID,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("billing.manage"))],
):
    try:
        return stamp_payment_complement(session, payment_id, actor_id=principal.user_id)
    except CfdiError as error:
        _raise_cfdi_error(error)


@app.post("/admin/billing/payment-complements/{payment_id}/cancel", tags=["billing"])
def cancel_payment_complement_detail(
    payment_id: UUID,
    payload: PaymentComplementCancelRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("billing.manage"))],
):
    try:
        return cancel_payment_complement(
            session,
            payment_id,
            reason_code=payload.reason_code,
            replacement_uuid=payload.replacement_uuid,
            note=payload.note,
            actor_id=principal.user_id,
        )
    except CfdiError as error:
        _raise_cfdi_error(error)


@app.get("/admin/billing/payment-complements/{payment_id}/xml", tags=["billing"])
def download_payment_complement_xml(
    payment_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("billing.read"))],
) -> Response:
    try:
        filename, content = payment_complement_xml(session, payment_id)
    except CfdiError as error:
        _raise_cfdi_error(error)
    return Response(
        content=content,
        media_type="application/xml; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@app.get("/admin/billing/payment-complements/{payment_id}/pdf", tags=["billing"])
def download_payment_complement_pdf(
    payment_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("billing.read"))],
) -> Response:
    try:
        filename, content = payment_complement_pdf(session, payment_id)
    except CfdiError as error:
        _raise_cfdi_error(error)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@app.get("/admin/billing/origins", tags=["billing"])
def get_billing_origins(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("billing.read"))],
    origin_type: Annotated[Literal["sale", "membership_payment"], Query()],
    search: Annotated[str | None, Query(max_length=120)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 10,
):
    try:
        return list_origin_options(
            session,
            origin_type=origin_type,
            search=search,
            page=page,
            page_size=page_size,
        )
    except CfdiError as error:
        _raise_cfdi_error(error)


@app.get("/admin/members/{member_id}/fiscal-profile", tags=["billing"])
def get_member_fiscal_profile(
    member_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("billing.read"))],
):
    try:
        profile = get_fiscal_profile(session, member_id)
    except CfdiError as error:
        _raise_cfdi_error(error)
    if profile is None:
        raise HTTPException(status_code=404, detail="El socio no tiene datos fiscales registrados.")
    return profile


@app.put("/admin/members/{member_id}/fiscal-profile", tags=["billing"])
def put_member_fiscal_profile(
    member_id: UUID,
    payload: FiscalDataRequest,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("billing.request"))],
):
    try:
        return save_fiscal_profile(
            session,
            member_id=member_id,
            rfc=payload.rfc,
            legal_name=payload.legal_name,
            tax_regime=payload.tax_regime,
            postal_code=payload.postal_code,
            cfdi_use=payload.cfdi_use,
            email=str(payload.email) if payload.email is not None else None,
        )
    except CfdiError as error:
        _raise_cfdi_error(error)


# --- Finance / bank reconciliation -----------------------------------------


class BankAccountCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    bank_name: str = Field(min_length=2, max_length=80)
    account_last4: str = Field(min_length=4, max_length=4)
    currency: str = Field(default="MXN", min_length=3, max_length=3)


class BankAccountStatusRequest(BaseModel):
    status: Literal["active", "inactive"]


class BankMovementImportRowRequest(BaseModel):
    occurred_on: date
    amount_cents: int
    reference: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=240)


class BankMovementImportRequest(BaseModel):
    rows: list[BankMovementImportRowRequest] = Field(min_length=1, max_length=500)


class BankMovementMatchRequest(BaseModel):
    source: Literal[
        "membership_payment",
        "sale",
        "member_account_payment",
        "sale_return",
        "invoice_payment",
    ]
    source_id: UUID
    note: str | None = Field(default=None, max_length=300)


class BankMovementUnmatchRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class BankMovementFlagRequest(BaseModel):
    status: Literal["pending", "difference", "reviewing"]
    note: str | None = Field(default=None, max_length=300)


def _finance_http_status(error: FinanceError) -> int:
    if isinstance(error, (BankAccountNotFound, BankMovementNotFound, MatchCandidateNotFound)):
        return status.HTTP_404_NOT_FOUND
    if isinstance(
        error, (DuplicateBankAccount, BankMovementStateError, CandidateUnavailable)
    ):
        return status.HTTP_409_CONFLICT
    if isinstance(error, (InvalidBankData, InvalidImportBatch, InvalidMatch)):
        return status.HTTP_422_UNPROCESSABLE_ENTITY
    return status.HTTP_400_BAD_REQUEST


def _raise_finance_error(error: FinanceError) -> None:
    raise HTTPException(status_code=_finance_http_status(error), detail=str(error)) from error


@app.get("/admin/finance/bank-accounts", tags=["finance"])
def get_bank_accounts(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("finance.read"))],
):
    try:
        return list_bank_accounts(session)
    except FinanceError as error:
        _raise_finance_error(error)


@app.post(
    "/admin/finance/bank-accounts",
    status_code=status.HTTP_201_CREATED,
    tags=["finance"],
)
def create_bank_account_endpoint(
    payload: BankAccountCreateRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("finance.manage"))],
):
    try:
        return create_bank_account(
            session,
            name=payload.name,
            bank_name=payload.bank_name,
            account_last4=payload.account_last4,
            currency=payload.currency,
            actor_id=principal.user_id,
        )
    except FinanceError as error:
        _raise_finance_error(error)


@app.patch("/admin/finance/bank-accounts/{account_id}", tags=["finance"])
def update_bank_account_endpoint(
    account_id: UUID,
    payload: BankAccountStatusRequest,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("finance.manage"))],
):
    try:
        return update_bank_account_status(session, account_id, status=payload.status)
    except FinanceError as error:
        _raise_finance_error(error)


@app.post("/admin/finance/bank-accounts/{account_id}/movements", tags=["finance"])
def import_bank_movements_endpoint(
    account_id: UUID,
    payload: BankMovementImportRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("finance.manage"))],
):
    rows = [
        {
            "occurred_on": row.occurred_on,
            "amount_cents": row.amount_cents,
            "reference": row.reference,
            "description": row.description,
        }
        for row in payload.rows
    ]
    try:
        return import_bank_movements(
            session, account_id, rows, actor_id=principal.user_id
        )
    except FinanceError as error:
        _raise_finance_error(error)


@app.get("/admin/finance/bank-movements", tags=["finance"])
def get_bank_movements(
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("finance.read"))],
    bank_account_id: Annotated[UUID | None, Query()] = None,
    status_filter: Annotated[
        Literal["pending", "reconciled", "difference", "reviewing"] | None,
        Query(alias="status"),
    ] = None,
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=120)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 25,
):
    try:
        return list_bank_movements(
            session,
            bank_account_id=bank_account_id,
            status_filter=status_filter,
            from_date=from_date,
            to_date=to_date,
            search=search,
            page=page,
            page_size=page_size,
        )
    except FinanceError as error:
        _raise_finance_error(error)


@app.get("/admin/finance/bank-movements/{movement_id}", tags=["finance"])
def get_bank_movement_endpoint(
    movement_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedUser, Depends(require_api_permission("finance.read"))],
    candidate_search: Annotated[str | None, Query(max_length=80)] = None,
):
    try:
        return get_bank_movement(session, movement_id, candidate_search=candidate_search)
    except FinanceError as error:
        _raise_finance_error(error)


@app.post("/admin/finance/bank-movements/{movement_id}/match", tags=["finance"])
def match_bank_movement_endpoint(
    movement_id: UUID,
    payload: BankMovementMatchRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("finance.manage"))],
):
    try:
        return match_bank_movement(
            session,
            movement_id,
            source=payload.source,
            source_id=payload.source_id,
            note=payload.note,
            actor_id=principal.user_id,
        )
    except FinanceError as error:
        _raise_finance_error(error)


@app.post("/admin/finance/bank-movements/{movement_id}/unmatch", tags=["finance"])
def unmatch_bank_movement_endpoint(
    movement_id: UUID,
    payload: BankMovementUnmatchRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("finance.manage"))],
):
    try:
        return unmatch_bank_movement(
            session,
            movement_id,
            reason=payload.reason,
            actor_id=principal.user_id,
        )
    except FinanceError as error:
        _raise_finance_error(error)


@app.post("/admin/finance/bank-movements/{movement_id}/flag", tags=["finance"])
def flag_bank_movement_endpoint(
    movement_id: UUID,
    payload: BankMovementFlagRequest,
    session: SessionDependency,
    principal: Annotated[AuthenticatedUser, Depends(require_api_permission("finance.manage"))],
):
    try:
        return flag_bank_movement(
            session,
            movement_id,
            status=payload.status,
            note=payload.note,
            actor_id=principal.user_id,
        )
    except FinanceError as error:
        _raise_finance_error(error)
