"""Billing API endpoints — plans, subscriptions, invoices, usage."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.shared.database import get_db
from src.auth.permissions import get_current_user, require_role
from src.billing.service import (
    get_current_plan,
    subscribe_to_plan,
    list_invoices,
    get_usage_summary,
    check_plan_limits,
)

router = APIRouter()


class SubscribeRequest(BaseModel):
    plan_id: int


@router.get("/plan")
def current_plan(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get the current user's plan."""
    plan = get_current_plan(db, user["user_id"])
    if not plan:
        return {"plan": None}
    return {"plan": plan.name, "tier": plan.tier, "price": plan.price_monthly}


@router.post("/subscribe")
def subscribe(body: SubscribeRequest, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Subscribe to a new plan."""
    sub = subscribe_to_plan(db, user["user_id"], body.plan_id)
    return {"subscription_id": sub.id, "plan_id": sub.plan_id}


@router.get("/invoices")
def invoices(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """List invoices for the current user."""
    return [
        {"id": inv.id, "amount": inv.amount, "status": inv.status}
        for inv in list_invoices(db, user["user_id"])
    ]


@router.get("/usage")
def usage(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get usage summary and plan limits."""
    return check_plan_limits(db, user["user_id"])
