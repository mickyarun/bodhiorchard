"""Billing models — plans, subscriptions, invoices, usage tracking."""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.sql import func
import enum

from src.shared.database import Base


class PlanTier(str, enum.Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class Plan(Base):
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    tier = Column(String, nullable=False)
    price_monthly = Column(Float, nullable=False)
    max_tasks = Column(Integer, default=100)
    max_members = Column(Integer, default=5)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=False)
    stripe_subscription_id = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    started_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime, nullable=True)


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="usd")
    status = Column(String, default="pending")  # pending, paid, failed
    stripe_invoice_id = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    paid_at = Column(DateTime, nullable=True)


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    metric = Column(String, nullable=False)  # tasks_created, api_calls, storage_mb
    quantity = Column(Integer, default=1)
    recorded_at = Column(DateTime, server_default=func.now())
