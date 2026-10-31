"""Customer records (contract: Customers tag). hasLogin / activeSubscriptions come from v_customers."""
import uuid

from sqlalchemy import Boolean, Integer, Select, Uuid, column, or_, select, table
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.pagination import PageParams, paginate
from app.models.identity import Customer
from app.schemas.customers import CustomerInput, CustomerOut, CustomerUpdate

_v_customers = table(
    "v_customers",
    column("id", Uuid),
    column("has_login", Boolean),
    column("active_subscriptions", Integer),
)

# API address key -> customers column
_ADDRESS_COLUMNS = {
    "line1": "address_line1",
    "line2": "address_line2",
    "city": "city",
    "state": "state",
    "postal_code": "postal_code",
    "country": "country",
}

DUPLICATE_EMAIL = "A customer with this email already exists"


def _select() -> Select:
    return select(Customer, _v_customers.c.has_login, _v_customers.c.active_subscriptions).join(
        _v_customers, _v_customers.c.id == Customer.id
    )


def to_out(row) -> CustomerOut:
    customer, has_login, active_subscriptions = row
    return CustomerOut(
        id=customer.id,
        name=customer.name,
        email=customer.email,
        phone=customer.phone,
        company=customer.company,
        tax_id=customer.tax_id,
        address={key: getattr(customer, col) for key, col in _ADDRESS_COLUMNS.items()},
        has_login=has_login,
        active_subscriptions=active_subscriptions,
        created_at=customer.created_at,
    )


def _load(db: Session, customer_id: uuid.UUID) -> CustomerOut:
    row = db.execute(_select().where(Customer.id == customer_id)).first()
    if row is None:
        raise AppError.not_found("Customer not found")
    return to_out(row)


def list_customers(db: Session, params: PageParams, q: str | None):
    stmt = _select()
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Customer.name.ilike(like), Customer.email.ilike(like), Customer.company.ilike(like)))
    rows, meta = paginate(db, stmt.order_by(Customer.created_at.desc(), Customer.id), params)
    return [to_out(r) for r in rows], meta


def get_customer(db: Session, customer_id: uuid.UUID) -> CustomerOut:
    return _load(db, customer_id)


def _email_taken(db: Session, email: str, exclude: uuid.UUID | None = None) -> bool:
    stmt = select(Customer.id).where(Customer.email == email)  # citext: case-insensitive
    if exclude is not None:
        stmt = stmt.where(Customer.id != exclude)
    return db.scalar(stmt) is not None


def _apply_address(customer: Customer, address: dict | None) -> None:
    for key, value in (address or {}).items():
        setattr(customer, _ADDRESS_COLUMNS[key], value)


def create_customer(db: Session, data: CustomerInput) -> CustomerOut:
    if _email_taken(db, data.email):
        raise AppError.conflict(DUPLICATE_EMAIL)
    customer = Customer(
        name=data.name, email=data.email, phone=data.phone, company=data.company, tax_id=data.tax_id
    )
    _apply_address(customer, data.address.model_dump(exclude_unset=True) if data.address else None)
    db.add(customer)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError.conflict(DUPLICATE_EMAIL) from None
    return _load(db, customer.id)


def update_customer(db: Session, customer_id: uuid.UUID, data: CustomerUpdate) -> CustomerOut:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise AppError.not_found("Customer not found")
    changes = data.model_dump(exclude_unset=True)
    # name and email are NOT NULL columns: an explicit null is a validation problem, not "clear it".
    for field in ("name", "email"):
        if field in changes and changes[field] is None:
            raise AppError.validation(f"{field} cannot be empty", field=field)
    if "email" in changes and _email_taken(db, changes["email"], exclude=customer.id):
        raise AppError.conflict(DUPLICATE_EMAIL)
    for field in ("name", "email", "phone", "company", "tax_id"):
        if field in changes:
            setattr(customer, field, changes[field])
    _apply_address(customer, changes.get("address"))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError.conflict(DUPLICATE_EMAIL) from None
    return _load(db, customer.id)
