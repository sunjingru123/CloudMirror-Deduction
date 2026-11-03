"""健康检查接口。"""

from fastapi import APIRouter

from app.core.config import settings
from app.schemas.health import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse, summary="健康检查")
def health_check() -> HealthResponse:
    """返回服务运行状态、项目名称与版本号。"""
    return HealthResponse(
        status="ok",
        project_name=settings.PROJECT_NAME,
        project_name_en=settings.PROJECT_NAME_EN,
        version=settings.VERSION,
    )
