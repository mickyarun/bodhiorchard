# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Create all database tables. Run once before starting the API."""

from src.shared.database import engine, Base
from src.auth.models import User, RefreshToken  # noqa: F401
from src.tasks.models import Task, Comment  # noqa: F401
from src.notifications.models import Notification, NotificationPreference  # noqa: F401
from src.billing.models import Plan, Subscription, Invoice, UsageRecord  # noqa: F401

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully.")
