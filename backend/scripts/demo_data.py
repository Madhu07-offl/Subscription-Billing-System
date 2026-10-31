"""Realistic demo data for the Subscription Billing System.

    python scripts/demo_data.py            # create it (does nothing if Demo data already exists)
    python scripts/demo_data.py --reset    # delete everything this script created (rows named / mailed "Demo")

Everything goes through the service layer wherever one exists: signup, subscriptions and their lifecycle, the
billing run, invoice confirmation and payments. There are no catalogue / customer services yet, so those rows are
created with the ORM models. Dates are relative to today, so the data always looks current.

Creates: 8 customers (the first can log in), 3 products with variants, a GST tax, 3 plans (monthly and yearly),
2 discounts, 15 subscriptions in every status, a billing run, confirmed invoices, full and partial payments, and
overdue invoices. Needs the seeded admin (database/seed.sql) and a backend/.env, like the API itself.
"""
import argparse
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so `app` imports work from any directory

from sqlalchemy import func, select, text, update  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import app.models  # noqa: E402,F401  (registers every model)
from app.db import SessionLocal  # noqa: E402
from app.models.billing import Invoice  # noqa: E402
from app.models.catalogue import Plan, Product, ProductVariant, Tax  # noqa: E402
from app.models.discounts import Discount, DiscountProduct  # noqa: E402
from app.models.identity import Customer, User  # noqa: E402
from app.models.subscriptions import Subscription  # noqa: E402
from app.schemas.auth import SignupRequest  # noqa: E402
from app.schemas.billing import BillingRunRequest  # noqa: E402
from app.schemas.invoices import PaymentInput  # noqa: E402
from app.schemas.subscriptions import LineInput, SubscriptionInput  # noqa: E402
from app.services import auth_service, billing_service, invoice_service, payment_service  # noqa: E402
from app.services import subscription_service as subs  # noqa: E402
from app.services.periods import add_months  # noqa: E402

PREFIX = "Demo"
EMAIL_LIKE = "demo-%@example.com"
LOGIN_EMAIL = "demo-customer1@example.com"
LOGIN_PASSWORD = "Demo#Pass2026"
TODAY = date.today()
TERM_DAYS = invoice_service.PAYMENT_TERM_DAYS


def months_ago(n: int) -> date:
    return add_months(TODAY, -n)


# ------------------------------------------------------------------ guard / reset
def demo_exists(db: Session) -> bool:
    return bool(
        db.scalar(select(func.count()).select_from(Plan).where(Plan.name.like(f"{PREFIX}%")))
        or db.scalar(select(func.count()).select_from(Customer).where(Customer.email.like(EMAIL_LIKE)))
    )


def reset(db: Session) -> None:
    """Delete what this script created, children before parents (financial rows are RESTRICTed)."""
    mine = "select id from customers where email like :e"
    p = {"e": EMAIL_LIKE, "n": f"{PREFIX}%"}
    runs = [
        str(r[0])
        for r in db.execute(
            text(f"select distinct billing_run_id from invoices where customer_id in ({mine}) and billing_run_id is not null"), p
        )
    ]
    db.execute(text(f"delete from payments where invoice_id in (select id from invoices where customer_id in ({mine}))"), p)
    db.execute(text(f"delete from invoices where customer_id in ({mine})"), p)
    if runs:
        db.execute(text("delete from billing_runs where id = any(cast(:ids as uuid[]))"), {"ids": runs})
    db.execute(text(f"delete from subscriptions where customer_id in ({mine})"), p)
    for table in ("discounts", "quotation_templates", "plans", "products", "taxes"):
        db.execute(text(f"delete from {table} where name like :n"), p)
    db.execute(text("delete from users where email like :e"), p)
    db.execute(text("delete from customers where email like :e"), p)
    db.commit()
    print("Demo data removed.")


# ------------------------------------------------------------------ catalogue and customers (ORM: no services yet)
@dataclass
class Catalogue:
    crm: Product
    helpdesk: Product
    onboarding: Product
    variants: dict[str, ProductVariant]
    plans: dict[str, Plan]


def create_catalogue(db: Session) -> Catalogue:
    db.add(Tax(name=f"{PREFIX} GST 18%", computation="percentage", value=Decimal("18")))  # no types: every product

    crm = Product(name=f"{PREFIX} CRM Suite", type="software", sales_price=Decimal("2000.00"), cost_price=Decimal("700.00"))
    helpdesk = Product(name=f"{PREFIX} Helpdesk", type="software", sales_price=Decimal("1200.00"), cost_price=Decimal("400.00"))
    onboarding = Product(name=f"{PREFIX} Onboarding Service", type="service", sales_price=Decimal("500.00"), cost_price=Decimal("200.00"))
    db.add_all([crm, helpdesk, onboarding])
    db.flush()
    variants = {
        "crm_pro": ProductVariant(product_id=crm.id, attribute="Edition", value="Pro", extra_price=Decimal("800.00")),
        "crm_ent": ProductVariant(product_id=crm.id, attribute="Edition", value="Enterprise", extra_price=Decimal("2500.00")),
        "hd_prem": ProductVariant(product_id=helpdesk.id, attribute="Support", value="Premium 24x7", extra_price=Decimal("600.00")),
        "ob_onsite": ProductVariant(product_id=onboarding.id, attribute="Delivery", value="On-site", extra_price=Decimal("300.00")),
    }
    db.add_all(variants.values())

    open_since = TODAY - timedelta(days=800)
    plans = {
        "basic": Plan(name=f"{PREFIX} Monthly Basic", price=Decimal("999.00"), billing_period="monthly", available_from=open_since,
                      allow_pause=True, allow_early_close=True, allow_renew=True),
        "pro": Plan(name=f"{PREFIX} Monthly Pro", price=Decimal("2999.00"), billing_period="monthly", available_from=open_since,
                    allow_pause=True, allow_early_close=True, allow_renew=True, auto_close=True),
        "yearly": Plan(name=f"{PREFIX} Yearly Business", price=Decimal("29999.00"), billing_period="yearly", available_from=open_since,
                       allow_pause=False, allow_early_close=False, allow_renew=True),
    }
    db.add_all(plans.values())

    # 10% off CRM lines (first 50 invoices); Rs 500 off any subscription whose subtotal is at least 3000.
    crm_discount = Discount(name=f"{PREFIX} CRM 10% off", type="percentage", value=Decimal("10"), scope="products",
                            start_date=open_since, usage_limit=50)
    flat_discount = Discount(name=f"{PREFIX} Rs 500 off big orders", type="fixed", value=Decimal("500"), scope="subscriptions",
                             min_purchase_amount=Decimal("3000.00"), start_date=open_since, usage_limit=25)
    db.add_all([crm_discount, flat_discount])
    db.flush()
    db.add(DiscountProduct(discount_id=crm_discount.id, product_id=crm.id))
    db.commit()
    return Catalogue(crm, helpdesk, onboarding, variants, plans)


CUSTOMERS = [
    ("Asha Verma", "Verma Textiles", "Pune"),
    ("Rohan Mehta", "Mehta Logistics", "Mumbai"),
    ("Priya Nair", "Nair Foods", "Kochi"),
    ("Karan Singh", "Singh & Sons", "Delhi"),
    ("Neha Gupta", "Gupta Clinics", "Jaipur"),
    ("Vikram Rao", "Rao Studios", "Hyderabad"),
    ("Sana Khan", "Khan Boutique", "Lucknow"),
    ("Arjun Das", "Das Analytics", "Kolkata"),
]


def create_customers(db: Session) -> list[Customer]:
    # The first customer signs up through the auth service, so there is a login for trying the customer views.
    login = auth_service.signup(
        db, SignupRequest(name=CUSTOMERS[0][0], email=LOGIN_EMAIL, password=LOGIN_PASSWORD, company=CUSTOMERS[0][1])
    )
    customers = [db.get(Customer, login.customer_id)]
    for i, (name, company, city) in enumerate(CUSTOMERS[1:], start=2):
        customers.append(
            Customer(name=name, email=f"demo-customer{i}@example.com", company=company, city=city, country="India",
                     phone=f"+91 90000 000{i:02d}")
        )
    db.add_all(customers[1:])
    db.commit()
    return customers


# ------------------------------------------------------------------ subscriptions (service layer)
@dataclass
class Spec:
    customer: int
    plan: str | None  # None = a bare draft (only a customer)
    start: date | None
    terms: str | None
    lines: list[LineInput]
    final: str  # draft | quotation | confirmed | active | paused | closed


def specs(cat: Catalogue) -> list[Spec]:
    v = cat.variants

    def line(product: Product, variant: ProductVariant | None = None, qty: int = 1) -> LineInput:
        return LineInput(product_id=product.id, variant_id=variant.id if variant else None, quantity=qty)

    crm, hd, ob = cat.crm, cat.helpdesk, cat.onboarding
    return [
        Spec(0, "basic", months_ago(4), "net_15", [line(crm, v["crm_pro"], 2)], "active"),
        Spec(0, "yearly", months_ago(1), "net_30", [line(crm, v["crm_ent"]), line(ob, v["ob_onsite"])], "active"),
        Spec(1, "pro", months_ago(3), "net_30", [line(hd, v["hd_prem"], 3)], "active"),
        Spec(2, "basic", months_ago(2), "immediate", [line(hd)], "active"),
        Spec(3, "pro", months_ago(5), "net_45", [line(crm), line(hd, qty=2)], "active"),
        Spec(4, "basic", months_ago(3), "net_15", [line(ob, qty=2)], "paused"),
        Spec(5, "pro", months_ago(2), "net_30", [line(crm, v["crm_pro"]), line(ob)], "active"),
        Spec(6, "basic", TODAY - timedelta(days=10), "net_30", [line(hd, v["hd_prem"])], "confirmed"),
        Spec(7, "pro", TODAY - timedelta(days=5), "net_15", [line(crm)], "confirmed"),
        Spec(1, "basic", TODAY + timedelta(days=7), "net_30", [line(hd, qty=2)], "quotation"),
        Spec(2, "yearly", TODAY + timedelta(days=14), "net_60", [line(crm, v["crm_pro"], 2)], "quotation"),
        Spec(3, "basic", TODAY + timedelta(days=30), "net_30", [line(ob)], "draft"),
        Spec(4, None, None, None, [], "draft"),
        Spec(6, "pro", months_ago(6), "net_30", [line(hd, v["hd_prem"])], "closed"),
        Spec(7, "basic", months_ago(5), "net_15", [line(crm), line(ob)], "closed"),
    ]


def create_subscriptions(db: Session, admin: User, customers: list[Customer], cat: Catalogue) -> list[tuple[Spec, Subscription]]:
    """Each subscription is taken as far as billing needs it: up to 'active' (paused / closed come after billing)."""
    out = []
    for spec in specs(cat):
        customer = customers[spec.customer]
        if spec.plan is None:
            body = SubscriptionInput(customer_id=customer.id, notes=f"{PREFIX} bare draft")
        else:
            body = SubscriptionInput(
                customer_id=customer.id, plan_id=cat.plans[spec.plan].id, start_date=spec.start,
                expiry_date=add_months(spec.start, 12), payment_terms=spec.terms, lines=spec.lines, notes=f"{PREFIX} subscription",
            )
        sub = subs.create_subscription(db, body, admin)
        if spec.final != "draft":
            subs.send_quotation(db, sub.id, admin)
        if spec.final in ("confirmed", "active", "paused", "closed"):
            subs.confirm(db, sub.id, admin)
        if spec.final in ("active", "paused", "closed"):
            subs.activate(db, sub.id, admin)
        out.append((spec, db.get(Subscription, sub.id)))
    return out


# ------------------------------------------------------------------ invoices and payments (service layer)
def settle_invoices(db: Session, admin: User, customers: list[Customer]) -> dict[str, int]:
    """Confirm the invoices, date them in their own period, then pay most of them in full, some partly, some not
    at all; the old unpaid ones are the overdue ones. The newest invoice of every third subscription stays a draft."""
    ids = [c.id for c in customers]
    invoices = list(
        db.scalars(select(Invoice).where(Invoice.customer_id.in_(ids)).order_by(Invoice.subscription_id, Invoice.period_start))
    )
    latest: dict = {}
    for inv in invoices:
        latest[inv.subscription_id] = inv.id
    keep_draft = {inv_id for i, inv_id in enumerate(latest.values()) if i % 3 == 0}

    stats = {"draft": 0, "full": 0, "partial": 0, "unpaid": 0}
    confirmed = []
    for inv in invoices:
        if inv.id in keep_draft:
            stats["draft"] += 1
            continue
        invoice_service.confirm(db, inv.id, admin)
        terms = db.scalar(select(Subscription.payment_terms).where(Subscription.id == inv.subscription_id))
        issued = min(inv.period_start, TODAY)  # issued when its period began, not "today": that is what makes old ones overdue
        db.execute(update(Invoice).where(Invoice.id == inv.id).values(issue_date=issued, due_date=issued + timedelta(days=TERM_DAYS[terms])))
        db.commit()
        confirmed.append((inv.id, issued))

    for i, (inv_id, issued) in enumerate(confirmed):
        pattern = i % 5  # 0-2 paid in full, 3 partly paid, 4 unpaid
        if pattern == 4:
            stats["unpaid"] += 1
            continue
        total = db.scalar(select(Invoice.total).where(Invoice.id == inv_id))
        amount = total if pattern < 3 else (total * Decimal("0.4")).quantize(Decimal("0.01"))
        payment_service.record_payment(
            db,
            PaymentInput(invoice_id=inv_id, method=("bank_transfer", "upi", "card", "cheque")[i % 4], amount=amount,
                         payment_date=min(issued + timedelta(days=3), TODAY), reference=f"DEMO-{i + 1:04d}",
                         note=f"{PREFIX} payment" if pattern < 3 else f"{PREFIX} part payment"),
            admin,
        )
        stats["full" if pattern < 3 else "partial"] += 1
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="delete the demo data instead of creating it")
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.reset:
            reset(db)
            return
        if demo_exists(db):
            print("Demo data already exists - nothing to do (run with --reset to remove it first).")
            return
        admin = db.scalar(select(User).where(User.role == "admin", User.is_active.is_(True)).order_by(User.created_at))
        if admin is None:
            sys.exit("No admin user found. Run database/seed.sql first.")

        cat = create_catalogue(db)
        customers = create_customers(db)
        made = create_subscriptions(db, admin, customers, cat)

        run = billing_service.run_billing(
            db,
            BillingRunRequest(as_of=TODAY, subscription_ids=[s.id for _, s in made if s.status == "active"]),
            admin,
        )
        print(f"Billing run: {run.counts.created} invoices created, {run.counts.failed} failed")

        for spec, sub in made:  # pause / close only after billing, so these were billed while they were active
            if spec.final == "paused":
                subs.pause(db, sub.id, admin)
            elif spec.final == "closed":
                subs.close(db, sub.id, None, admin)
        stats = settle_invoices(db, admin, customers)

        overdue = db.scalar(text("select count(*) from v_invoices where is_overdue and customer_email like :e"), {"e": EMAIL_LIKE})
        by_status = dict(db.execute(select(Subscription.status, func.count()).where(Subscription.customer_id.in_([c.id for c in customers])).group_by(Subscription.status)).all())
        print(f"Customers: {len(customers)}   Subscriptions: {sum(by_status.values())} {dict(sorted(by_status.items()))}")
        print(f"Invoices: {stats}   overdue: {overdue}")
        print(f"Customer login: {LOGIN_EMAIL} / {LOGIN_PASSWORD}   (admin: see database/seed.sql)")


if __name__ == "__main__":
    main()
