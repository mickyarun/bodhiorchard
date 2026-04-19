"""Create all database tables. Run once before starting the API."""

from src.shared.database import engine, Base
from src.auth.models import User, RefreshToken  # noqa: F401
from src.tasks.models import Task, Comment  # noqa: F401
from src.notifications.models import Notification, NotificationPreference  # noqa: F401
from src.billing.models import Plan, Subscription, Invoice, UsageRecord  # noqa: F401

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully.")
