"""Task API endpoints — CRUD, assignment, comments."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.shared.database import get_db
from src.auth.permissions import get_current_user
from src.tasks.service import (
    create_task,
    get_task,
    list_tasks,
    assign_task,
    transition_status,
    add_comment,
    get_comments,
)
from src.tasks.models import TaskStatus, TaskPriority

router = APIRouter()


class CreateTaskRequest(BaseModel):
    title: str
    description: str = ""
    priority: TaskPriority = TaskPriority.MEDIUM
    assignee_id: int | None = None


class UpdateStatusRequest(BaseModel):
    status: TaskStatus


class AssignRequest(BaseModel):
    assignee_id: int


class CommentRequest(BaseModel):
    body: str


@router.post("")
def create(body: CreateTaskRequest, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Create a new task."""
    task = create_task(
        db,
        title=body.title,
        description=body.description,
        creator_id=user["user_id"],
        priority=body.priority,
        assignee_id=body.assignee_id,
    )
    return {"id": task.id, "title": task.title}


@router.get("")
def index(
    assignee_id: int | None = None,
    status: TaskStatus | None = None,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List tasks with optional filters."""
    tasks = list_tasks(db, assignee_id=assignee_id, status=status)
    return [{"id": t.id, "title": t.title, "status": t.status, "priority": t.priority} for t in tasks]


@router.get("/{task_id}")
def show(task_id: int, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """Get a single task."""
    task = get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.patch("/{task_id}/status")
def update_status(
    task_id: int,
    body: UpdateStatusRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Change task status."""
    task = transition_status(db, task_id, body.status)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"id": task.id, "status": task.status}


@router.patch("/{task_id}/assign")
def assign(
    task_id: int,
    body: AssignRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Assign a task to a user."""
    task = assign_task(db, task_id, body.assignee_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"id": task.id, "assignee_id": task.assignee_id}


@router.post("/{task_id}/comments")
def create_comment(
    task_id: int,
    body: CommentRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Add a comment to a task."""
    comment = add_comment(db, task_id, user["user_id"], body.body)
    return {"id": comment.id, "body": comment.body}


@router.get("/{task_id}/comments")
def list_comments(task_id: int, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """Get comments for a task."""
    return [{"id": c.id, "body": c.body, "author_id": c.author_id} for c in get_comments(db, task_id)]
