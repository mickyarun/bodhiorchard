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

"""Task business logic — CRUD, assignment, status transitions."""

from sqlalchemy.orm import Session

from src.tasks.models import Task, TaskStatus, Comment


def create_task(db: Session, title: str, description: str, creator_id: int, **kwargs) -> Task:
    """Create a new task."""
    task = Task(title=title, description=description, creator_id=creator_id, **kwargs)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_task(db: Session, task_id: int) -> Task | None:
    """Fetch a single task by ID."""
    return db.query(Task).filter(Task.id == task_id).first()


def list_tasks(
    db: Session,
    assignee_id: int | None = None,
    status: TaskStatus | None = None,
    limit: int = 50,
) -> list[Task]:
    """List tasks with optional filters."""
    query = db.query(Task)
    if assignee_id:
        query = query.filter(Task.assignee_id == assignee_id)
    if status:
        query = query.filter(Task.status == status)
    return query.order_by(Task.created_at.desc()).limit(limit).all()


def assign_task(db: Session, task_id: int, assignee_id: int) -> Task | None:
    """Assign a task to a user."""
    task = get_task(db, task_id)
    if not task:
        return None
    task.assignee_id = assignee_id
    db.commit()
    db.refresh(task)
    return task


def transition_status(db: Session, task_id: int, new_status: TaskStatus) -> Task | None:
    """Move a task to a new status."""
    task = get_task(db, task_id)
    if not task:
        return None
    task.status = new_status
    db.commit()
    db.refresh(task)
    return task


def add_comment(db: Session, task_id: int, author_id: int, body: str) -> Comment:
    """Add a comment to a task."""
    comment = Comment(task_id=task_id, author_id=author_id, body=body)
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


def get_comments(db: Session, task_id: int) -> list[Comment]:
    """Get all comments for a task, newest first."""
    return (
        db.query(Comment)
        .filter(Comment.task_id == task_id)
        .order_by(Comment.created_at.desc())
        .all()
    )
