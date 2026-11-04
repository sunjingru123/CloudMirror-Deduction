"""故障事件相关的 Pydantic Schema。

故障类型 / 严重程度 / 状态均使用枚举约束，保证请求与响应取值合法。
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class FaultType(str, Enum):
    """故障类型。"""

    NODE_DOWN = "node_down"
    SERVICE_UNAVAILABLE = "service_unavailable"
    NETWORK_LATENCY = "network_latency"
    NETWORK_UNREACHABLE = "network_unreachable"


class FaultSeverity(str, Enum):
    """故障严重程度。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FaultStatus(str, Enum):
    """故障状态。"""

    ACTIVE = "active"
    RECOVERED = "recovered"


class FaultEventCreate(BaseModel):
    """注入故障请求体。"""

    source_node_id: int = Field(..., description="故障源节点 ID")
    fault_type: FaultType = Field(..., description="故障类型")
    severity: FaultSeverity = Field(FaultSeverity.MEDIUM, description="严重程度")
    description: str | None = Field(None, description="故障描述")


class FaultEventRead(BaseModel):
    """故障事件响应。"""

    id: int
    topology_id: int
    source_node_id: int
    source_node_name: str | None = Field(None, description="故障源节点名称（便于展示）")
    fault_type: FaultType
    severity: FaultSeverity
    description: str | None
    status: FaultStatus
    created_at: datetime
    recovered_at: datetime | None
