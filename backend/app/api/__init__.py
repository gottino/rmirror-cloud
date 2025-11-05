"""API routers."""

from fastapi import APIRouter

from app.api import auth, notebooks, users

api_router = APIRouter()

# Include routers
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(notebooks.router, prefix="/notebooks", tags=["notebooks"])
