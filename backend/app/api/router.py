"""汇总各模块的 API 路由。"""

from fastapi import APIRouter

from app.api import health, topologies

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(topologies.router)
