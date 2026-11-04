"""汇总各模块的 API 路由。"""

from fastapi import APIRouter

from app.api import analyses, faults, health, recovery, topologies

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(topologies.router)
api_router.include_router(faults.topology_router)
api_router.include_router(faults.fault_router)
api_router.include_router(analyses.router)
api_router.include_router(recovery.router)
