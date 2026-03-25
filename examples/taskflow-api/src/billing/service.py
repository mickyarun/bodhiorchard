"""Billing service — subscriptions, plan management, usage tracking."""

from sqlalchemy.orm import Session

from src.billing.models import Plan, Subscription, Invoice, UsageRecord


def get_current_plan(db: Session, user_id: int) -> Plan | None:
    """Get the user's current active plan."""
    sub = (
        db.query(Subscription)
        .filter(Subscription.user_id == user_id, Subscription.is_active.is_(True))
        .first()
    )
    if not sub:
        return None
    return db.query(Plan).filter(Plan.id == sub.plan_id).first()


def subscribe_to_plan(db: Session, user_id: int, plan_id: int) -> Subscription:
    """Subscribe a user to a plan (cancels existing)."""
    # Cancel any existing subscription
    db.query(Subscription).filter(
        Subscription.user_id == user_id, Subscription.is_active.is_(True)
    ).update({"is_active": False})

    sub = Subscription(user_id=user_id, plan_id=plan_id)
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


def list_invoices(db: Session, user_id: int) -> list[Invoice]:
    """Get all invoices for a user."""
    return (
        db.query(Invoice)
        .filter(Invoice.user_id == user_id)
        .order_by(Invoice.created_at.desc())
        .all()
    )


def record_usage(db: Session, user_id: int, metric: str, quantity: int = 1) -> UsageRecord:
    """Record a usage metric for billing."""
    record = UsageRecord(user_id=user_id, metric=metric, quantity=quantity)
    db.add(record)
    db.commit()
    return record


def get_usage_summary(db: Session, user_id: int) -> dict[str, int]:
    """Get total usage per metric for the current billing period."""
    from sqlalchemy import func

    rows = (
        db.query(UsageRecord.metric, func.sum(UsageRecord.quantity))
        .filter(UsageRecord.user_id == user_id)
        .group_by(UsageRecord.metric)
        .all()
    )
    return {metric: total for metric, total in rows}


def check_plan_limits(db: Session, user_id: int) -> dict:
    """Check if user is within their plan limits."""
    plan = get_current_plan(db, user_id)
    if not plan:
        return {"within_limits": False, "reason": "No active plan"}

    usage = get_usage_summary(db, user_id)
    tasks_used = usage.get("tasks_created", 0)

    return {
        "within_limits": tasks_used < plan.max_tasks,
        "tasks_used": tasks_used,
        "tasks_limit": plan.max_tasks,
        "plan": plan.name,
    }
