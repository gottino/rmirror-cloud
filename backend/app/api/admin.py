"""Admin API endpoints for user management dashboard."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.waitlist import get_admin_user
from app.database import get_db
from app.models.notebook import Notebook
from app.models.page import Page
from app.models.quota_usage import QuotaUsage
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ==================== Schemas ====================


class AdminUserResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    created_at: str
    subscription_tier: str
    onboarding_state: str
    # Milestone timestamps
    agent_downloaded_at: Optional[str] = None
    agent_first_connected_at: Optional[str] = None
    first_notebook_synced_at: Optional[str] = None
    first_ocr_completed_at: Optional[str] = None
    notion_connected_at: Optional[str] = None
    # Usage stats
    notebook_count: int = 0
    page_count: int = 0
    quota_used: int = 0
    quota_limit: int = 30
    # Activity
    last_active_at: Optional[str] = None


class AdminUsersStats(BaseModel):
    total_users: int = 0
    agent_downloaded: int = 0
    agent_connected: int = 0
    first_notebook_synced: int = 0
    first_ocr_completed: int = 0
    notion_connected: int = 0


class AdminUsersResponse(BaseModel):
    users: list[AdminUserResponse]
    total: int
    stats: AdminUsersStats


# ==================== Endpoints ====================


@router.get("/users", response_model=AdminUsersResponse)
async def get_admin_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    sort_by: str = Query("created_at"),
    sort_dir: str = Query("desc"),
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """List all users with onboarding milestones and usage stats (admin only)."""
    # Subqueries for aggregates
    notebook_counts = (
        db.query(
            Notebook.user_id,
            func.count(Notebook.id).label("notebook_count"),
        )
        .filter(Notebook.document_type != "folder")
        .group_by(Notebook.user_id)
        .subquery()
    )

    page_counts = (
        db.query(
            Notebook.user_id,
            func.count(Page.id).label("page_count"),
        )
        .join(Page, Page.notebook_id == Notebook.id)
        .group_by(Notebook.user_id)
        .subquery()
    )

    quota_usage = (
        db.query(
            QuotaUsage.user_id,
            QuotaUsage.used.label("quota_used"),
            QuotaUsage.limit.label("quota_limit"),
        )
        .filter(QuotaUsage.quota_type == "ocr")
        .subquery()
    )

    # Main query
    query = (
        db.query(
            User,
            func.coalesce(notebook_counts.c.notebook_count, 0).label("notebook_count"),
            func.coalesce(page_counts.c.page_count, 0).label("page_count"),
            func.coalesce(quota_usage.c.quota_used, 0).label("quota_used"),
            func.coalesce(quota_usage.c.quota_limit, 30).label("quota_limit"),
        )
        .outerjoin(notebook_counts, User.id == notebook_counts.c.user_id)
        .outerjoin(page_counts, User.id == page_counts.c.user_id)
        .outerjoin(quota_usage, User.id == quota_usage.c.user_id)
    )

    # Sorting
    allowed_sort = {
        "created_at": User.created_at,
        "email": User.email,
        "onboarding_state": User.onboarding_state,
    }
    sort_col = allowed_sort.get(sort_by, User.created_at)
    if sort_dir == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    total = db.query(func.count(User.id)).scalar() or 0
    rows = query.offset(skip).limit(limit).all()

    # Build response
    users = []
    for row in rows:
        user = row[0]
        nb_count = row[1]
        pg_count = row[2]
        q_used = row[3]
        q_limit = row[4]

        # Compute last_active_at as the max of available timestamps
        timestamps = [
            user.last_login_at,
            user.agent_first_connected_at,
            user.first_notebook_synced_at,
            user.first_ocr_completed_at,
        ]
        active_timestamps = [t for t in timestamps if t is not None]
        last_active = max(active_timestamps) if active_timestamps else user.created_at

        users.append(AdminUserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            created_at=user.created_at.isoformat() + "Z",
            subscription_tier=user.subscription_tier,
            onboarding_state=user.onboarding_state,
            agent_downloaded_at=user.agent_downloaded_at.isoformat() + "Z" if user.agent_downloaded_at else None,
            agent_first_connected_at=user.agent_first_connected_at.isoformat() + "Z" if user.agent_first_connected_at else None,
            first_notebook_synced_at=user.first_notebook_synced_at.isoformat() + "Z" if user.first_notebook_synced_at else None,
            first_ocr_completed_at=user.first_ocr_completed_at.isoformat() + "Z" if user.first_ocr_completed_at else None,
            notion_connected_at=user.notion_connected_at.isoformat() + "Z" if user.notion_connected_at else None,
            notebook_count=nb_count,
            page_count=pg_count,
            quota_used=q_used,
            quota_limit=q_limit,
            last_active_at=last_active.isoformat() + "Z" if last_active else None,
        ))

    # Stats
    stats = AdminUsersStats(
        total_users=total,
        agent_downloaded=db.query(func.count(User.id)).filter(User.agent_downloaded_at.isnot(None)).scalar() or 0,
        agent_connected=db.query(func.count(User.id)).filter(User.agent_first_connected_at.isnot(None)).scalar() or 0,
        first_notebook_synced=db.query(func.count(User.id)).filter(User.first_notebook_synced_at.isnot(None)).scalar() or 0,
        first_ocr_completed=db.query(func.count(User.id)).filter(User.first_ocr_completed_at.isnot(None)).scalar() or 0,
        notion_connected=db.query(func.count(User.id)).filter(User.notion_connected_at.isnot(None)).scalar() or 0,
    )

    return AdminUsersResponse(users=users, total=total, stats=stats)
