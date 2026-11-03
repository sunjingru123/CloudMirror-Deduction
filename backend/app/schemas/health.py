"""健康检查相关 Schema。"""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """健康检查响应体。"""

    status: str = Field(..., description="服务状态", examples=["ok"])
    project_name: str = Field(..., description="项目名称", examples=["云镜推演"])
    project_name_en: str = Field(
        ..., description="项目英文名称", examples=["CloudMirror Deduction"]
    )
    version: str = Field(..., description="服务版本号", examples=["0.1.0"])
