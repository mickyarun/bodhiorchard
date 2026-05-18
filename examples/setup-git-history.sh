#!/bin/bash
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

# Re-create git repos with proper author commit history for scan testing.
# Run this after cloning the main repo.
#
# Usage: cd examples && bash setup-git-history.sh
#
# The example repos are no longer tracked by the parent bodhiorchard
# repository (see top-level .gitignore). Before rebuilding the synthetic
# history we clone fresh copies from GitHub if the local directories
# are missing — keeps the bootstrap a one-command operation for new
# contributors and CI environments.

set -e

REPOS=(taskflow-api taskflow-web taskflow-worker taskflow-qa)
GITHUB_OWNER="${BODHIORCHARD_EXAMPLES_OWNER:-mickyarun}"

for repo in "${REPOS[@]}"; do
  if [ ! -d "$repo" ]; then
    echo "Cloning $repo from github.com/${GITHUB_OWNER}/$repo..."
    if command -v gh >/dev/null 2>&1; then
      gh repo clone "${GITHUB_OWNER}/$repo"
    else
      git clone "git@github.com:${GITHUB_OWNER}/$repo.git"
    fi
  fi
done

echo "Setting up taskflow-api git history..."
cd taskflow-api
rm -rf .git
git init && git branch -m main
git add requirements.txt src/__init__.py src/main.py src/shared/
git -c user.name="Dave Chen" -c user.email="dave@taskflow.dev" commit -m "Initial project setup with FastAPI skeleton and database config" --date="2025-12-01T09:00:00"
git add src/auth/__init__.py src/auth/models.py src/auth/service.py src/auth/permissions.py src/auth/router.py
git -c user.name="Alice Kim" -c user.email="alice@taskflow.dev" commit -m "Add authentication system: JWT, password hashing, RBAC permissions" --date="2025-12-03T10:30:00"
git add src/tasks/
git -c user.name="Bob Martinez" -c user.email="bob@taskflow.dev" commit -m "Add task management: CRUD, assignment, status transitions, comments" --date="2025-12-05T14:00:00"
git add src/notifications/
git -c user.name="Dave Chen" -c user.email="dave@taskflow.dev" commit -m "Add notification system: in-app, email queue, push queue, preferences" --date="2025-12-08T11:00:00"
git add src/billing/
git -c user.name="Carol Singh" -c user.email="carol@taskflow.dev" commit -m "Add billing: plans, subscriptions, invoices, usage tracking" --date="2025-12-10T16:00:00"
git add src/auth/password_reset.py
git -c user.name="Alice Kim" -c user.email="alice@taskflow.dev" commit -m "Add password reset flow with token validation" --date="2025-12-12T09:00:00"
git add README.md .gitignore src/create_db.py
git -c user.name="Dave Chen" -c user.email="dave@taskflow.dev" commit -m "Add CORS, create_db script, README" --date="2025-12-16T12:00:00"
echo "  Done ($(git rev-list --count HEAD) commits)"

echo "Setting up taskflow-worker git history..."
cd ../taskflow-worker
rm -rf .git
git init && git branch -m main
git add requirements.txt src/__init__.py src/main.py src/shared/
git -c user.name="Dave Chen" -c user.email="dave@taskflow.dev" commit -m "Worker skeleton: Redis queue consumer, job dispatch loop" --date="2025-12-02T10:00:00"
git add src/notifications/
git -c user.name="Dave Chen" -c user.email="dave@taskflow.dev" commit -m "Add email, push, and digest notification delivery" --date="2025-12-09T14:00:00"
git add src/auth/
git -c user.name="Alice Kim" -c user.email="alice@taskflow.dev" commit -m "Add session cleanup and inactive user detection" --date="2025-12-11T10:00:00"
git add src/reminders/
git -c user.name="Bob Martinez" -c user.email="bob@taskflow.dev" commit -m "Add task reminder scheduler with due-date checks" --date="2025-12-13T11:00:00"
git add src/billing/
git -c user.name="Carol Singh" -c user.email="carol@taskflow.dev" commit -m "Add invoice generation and Stripe billing sync" --date="2025-12-15T15:00:00"
git add README.md
git -c user.name="Dave Chen" -c user.email="dave@taskflow.dev" commit -m "Add README with setup instructions" --date="2025-12-16T09:30:00"
echo "  Done ($(git rev-list --count HEAD) commits)"

echo "Setting up taskflow-web git history..."
cd ../taskflow-web
rm -rf .git
git init && git branch -m main
git add package.json src/services/
git -c user.name="Dave Chen" -c user.email="dave@taskflow.dev" commit -m "Vue 3 project setup with API client and auth interceptors" --date="2025-12-04T09:00:00"
git add src/views/auth/
git -c user.name="Bob Martinez" -c user.email="bob@taskflow.dev" commit -m "Add login and registration views with form validation" --date="2025-12-06T10:00:00"
git add src/views/tasks/
git -c user.name="Bob Martinez" -c user.email="bob@taskflow.dev" commit -m "Add task board and detail views with comments" --date="2025-12-07T14:00:00"
git add src/components/notifications/
git -c user.name="Dave Chen" -c user.email="dave@taskflow.dev" commit -m "Add notification bell component and preferences panel" --date="2025-12-10T11:00:00"
git add src/views/billing/
git -c user.name="Carol Singh" -c user.email="carol@taskflow.dev" commit -m "Add billing plans view with usage tracking and invoices" --date="2025-12-14T16:00:00"
git add index.html vite.config.ts tsconfig.json src/main.ts src/App.vue README.md
git -c user.name="Dave Chen" -c user.email="dave@taskflow.dev" commit -m "Add Vite config, router, App shell, README" --date="2025-12-16T11:00:00"
echo "  Done ($(git rev-list --count HEAD) commits)"

cd ..
echo ""
echo "All 3 repos ready. Add them as tracked repositories in Bodhiorchard settings."
