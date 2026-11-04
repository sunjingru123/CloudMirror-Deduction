"""拓扑相关的 Pydantic Schema。

节点类型与状态使用枚举约束，保证请求/响应取值合法。
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class NodeType(str, Enum):
    """节点类型。"""

    USER_ENTRY = "user_entry"
    LOAD_BALANCER = "load_balancer"
    APP_SERVER = "app_server"
    DATABASE = "database"
    CACHE = "cache"
    MESSAGE_QUEUE = "message_queue"
    EXTERNAL_API = "external_api"


class NodeStatus(str, Enum):
    """节点状态。"""

    HEALTHY = "healthy"
    FAULTY = "faulty"
    DEGRADED = "degraded"


class TopologyBase(BaseModel):
    """拓扑基础字段。"""

    name: str = Field(..., min_length=1, max_length=128, description="拓扑名称")
    description: str | None = Field(None, description="拓扑描述")


class TopologyCreate(TopologyBase):
    """创建拓扑请求体。"""


class TopologyUpdate(BaseModel):
    """更新拓扑请求体，字段均可选。"""

    name: str | None = Field(None, min_length=1, max_length=128)
    description: str | None = None


class TopologyRead(TopologyBase):
    """拓扑摘要响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    node_count: int = 0
    edge_count: int = 0


class TopologyNodeBase(BaseModel):
    """节点基础字段。"""

    name: str = Field(..., min_length=1, max_length=128, description="节点名称")
    type: NodeType = Field(..., description="节点类型")
    description: str | None = Field(None, description="节点描述")
    status: NodeStatus = Field(NodeStatus.HEALTHY, description="节点状态")
    position_x: float = Field(0.0, description="画布 X 坐标")
    position_y: float = Field(0.0, description="画布 Y 坐标")


class TopologyNodeCreate(TopologyNodeBase):
    """创建节点请求体。"""


class TopologyNodeUpdate(BaseModel):
    """更新节点请求体，字段均可选。"""

    name: str | None = Field(None, min_length=1, max_length=128)
    type: NodeType | None = None
    description: str | None = None
    status: NodeStatus | None = None
    position_x: float | None = None
    position_y: float | None = None


class TopologyNodeRead(TopologyNodeBase):
    """节点响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    topology_id: int
    created_at: datetime
    updated_at: datetime


class TopologyEdgeCreate(BaseModel):
    """创建依赖关系请求体。

    方向约定：source_node_id 依赖 target_node_id（source → target）。
    """

    source_node_id: int = Field(..., description="依赖方节点 ID（source）")
    target_node_id: int = Field(..., description="被依赖方节点 ID（target）")
    description: str | None = Field(None, description="依赖说明")


class TopologyEdgeRead(BaseModel):
    """依赖关系响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    topology_id: int
    source_node_id: int
    target_node_id: int
    description: str | None
    created_at: datetime


class TopologyDetail(TopologyBase):
    """拓扑详情响应，包含完整节点与依赖关系。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    nodes: list[TopologyNodeRead] = Field(default_factory=list)
    edges: list[TopologyEdgeRead] = Field(default_factory=list)
