"""API routers."""

from fastapi import APIRouter

from app.api import auth, integrations, notebooks, processing, sync, todos, users

api_router = APIRouter()

# Include routers
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(notebooks.router, prefix="/notebooks", tags=["notebooks"])
api_router.include_router(processing.router, prefix="/processing", tags=["processing"])
api_router.include_router(integrations.router, prefix="/integrations", tags=["integrations"])
api_router.include_router(sync.router, prefix="/sync", tags=["sync"])
api_router.include_router(todos.router, prefix="/todos", tags=["todos"])
