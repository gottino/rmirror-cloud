"""API routers."""

from fastapi import APIRouter

from app.api import agents, auth, integrations, notebooks, onboarding, processing, sync, todos, users, waitlist
from app.api.webhooks import clerk as clerk_webhook

api_router = APIRouter()

# Include routers
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(onboarding.router, prefix="/onboarding", tags=["onboarding"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(notebooks.router, prefix="/notebooks", tags=["notebooks"])
api_router.include_router(processing.router, prefix="/processing", tags=["processing"])
api_router.include_router(integrations.router, prefix="/integrations", tags=["integrations"])
api_router.include_router(sync.router, prefix="/sync", tags=["sync"])
api_router.include_router(todos.router, prefix="/todos", tags=["todos"])
api_router.include_router(waitlist.router, tags=["waitlist"])
api_router.include_router(clerk_webhook.router, prefix="/webhooks/clerk", tags=["webhooks"])
