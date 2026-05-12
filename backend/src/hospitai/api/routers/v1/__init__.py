"""API version 1 router tree."""

from __future__ import annotations

from fastapi import APIRouter

from hospitai.api.routers.v1 import admin as admin_r
from hospitai.api.routers.v1 import appointments as appointments_r
from hospitai.api.routers.v1 import auth as auth_r
from hospitai.api.routers.v1 import internal as internal_r
from hospitai.api.routers.v1 import ping as ping_r
from hospitai.api.routers.v1 import tickets as tickets_r
from hospitai.api.routers.v1 import users as users_r

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(ping_r.router)
api_v1.include_router(auth_r.router)
api_v1.include_router(users_r.router)
api_v1.include_router(appointments_r.router)
api_v1.include_router(tickets_r.router)
api_v1.include_router(admin_r.router)
api_v1.include_router(internal_r.router)
