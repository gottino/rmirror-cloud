"""API routers."""

from fastapi import APIRouter

from app.api import (
    agents,
    auth,
    integrations,
    notebooks,
    notion_oauth,
    onboarding,
    pages,
    processing,
    quota,
    sync,
    todos,
    users,
    waitlist,
)
from app.api.webhooks import clerk as clerk_webhook

api_router = APIRouter()

# Include routers
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(onboarding.router, prefix="/onboarding", tags=["onboarding"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(notebooks.router, prefix="/notebooks", tags=["notebooks"])
api_router.include_router(pages.router, prefix="/pages", tags=["pages"])
api_router.include_router(processing.router, prefix="/processing", tags=["processing"])
api_router.include_router(quota.router, prefix="/quota", tags=["quota"])
api_router.include_router(integrations.router, prefix="/integrations", tags=["integrations"])
api_router.include_router(notion_oauth.router, prefix="/integrations", tags=["integrations", "notion-oauth"])
api_router.include_router(sync.router, prefix="/sync", tags=["sync"])
api_router.include_router(todos.router, prefix="/todos", tags=["todos"])
api_router.include_router(waitlist.router, tags=["waitlist"])
api_router.include_router(clerk_webhook.router, prefix="/webhooks/clerk", tags=["webhooks"])
