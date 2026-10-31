"""The daily auto-close job (API.md section 2: "autoClose plans: a daily job moves active subscriptions past
expiryDate to closed").

Closes every `active` subscription whose plan has auto_close = true and whose expiry_date is before `as_of`.
Closing clears next_billing_date (no proration, no credit note in v1) and writes the status history with no user,
which the contract defines as an automatic change. One transaction per subscription, so a problem with one row
never blocks the rest; rows another process is already working on are skipped and picked up by the next run.

Run it once a day, AFTER the billing run (periods that start on or before expiry_date must be billed first;
closing clears the billing date):

    POST /api/v1/billing/auto-close                       (admin token; from cron / a scheduler)
    python -m app.services.auto_close_service             (from the backend directory; same code, no HTTP)
"""
import logging
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalogue import Plan
from app.models.subscriptions import Subscription, SubscriptionStatusHistory
from app.schemas.billing import AutoCloseResult, ClosedSubscription

logger = logging.getLogger("app.auto_close")


def auto_close_expired(db: Session, as_of: date | None = None) -> AutoCloseResult:
    as_of = as_of or date.today()
    candidates = db.execute(
        select(Subscription.id, Subscription.number)
        .join(Plan, Plan.id == Subscription.plan_id)
        .where(Subscription.status == "active", Plan.auto_close.is_(True), Subscription.expiry_date < as_of)
        .order_by(Subscription.expiry_date, Subscription.number)
    ).all()
    db.rollback()  # end the read transaction; each subscription gets its own

    closed: list[ClosedSubscription] = []
    for sub_id, number in candidates:
        try:
            sub = db.scalars(
                select(Subscription)
                .where(Subscription.id == sub_id)
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            ).first()
            # re-check under the lock: it may have been closed, or renewed past today, since the read above
            if sub is None or sub.status != "active" or sub.expiry_date is None or sub.expiry_date >= as_of:
                db.rollback()
                continue
            reason = f"Auto-closed: expired on {sub.expiry_date}"
            sub.status = "closed"
            sub.closed_at = func.now()
            sub.close_reason = reason
            sub.next_billing_date = None
            db.add(
                SubscriptionStatusHistory(
                    subscription_id=sub.id,
                    event="status_change",
                    from_status="active",
                    to_status="closed",
                    note=reason,
                    changed_by=None,  # automatic change
                )
            )
            db.commit()
            closed.append(ClosedSubscription(subscription_id=sub_id, number=number))
        except Exception:  # noqa: BLE001 - keep closing the others
            db.rollback()
            logger.exception("Auto-close failed for %s", number)
    logger.info("Auto-close as of %s: %d of %d candidates closed", as_of, len(closed), len(candidates))
    return AutoCloseResult(as_of=as_of, closed_count=len(closed), closed=closed)


def main() -> None:  # pragma: no cover - thin CLI wrapper for schedulers without HTTP
    from app.db import SessionLocal

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    with SessionLocal() as db:
        result = auto_close_expired(db)
    print(f"closed {result.closed_count} subscription(s) as of {result.as_of}")


if __name__ == "__main__":  # pragma: no cover
    main()
