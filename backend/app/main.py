"""
FastAPI application entry point.

Run from backend/:  uvicorn app.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.modules.catalog.router import router as catalog_router
from app.modules.channels.router import router as channels_router
from app.modules.inventory.router import router as inventory_router
from app.modules.orders.router import router as orders_router
from app.modules.tenants.router import router as tenants_router

app = FastAPI(title=settings.app_name, debug=settings.debug)

# Auth is a Bearer token, not cookies — so no allow_credentials
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(tenants_router)
app.include_router(catalog_router)
app.include_router(inventory_router)
app.include_router(orders_router)
app.include_router(channels_router)
