"""冗余关系相关的 Pydantic Schema。

冗余关系与依赖关系（`topology_edge`）语义不同，详见 `app/models/redundancy.py`。

创建接口支持在**一次请求**内提交完整的主备结构（主节点 + 若干备用节点及其优先级），
不需要用户分多次提交。
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class RedundancyType(str, Enum):
    """冗余模式。"""

    ACTIVE_STANDBY = "active_standby"
    """主备模式：一个主节点 + 至少一个备用节点。"""

    ACTIVE_ACTIVE = "active_active"
    """双活模式：至少两个 active 成员。"""

    MANUAL_STANDBY = "manual_standby"
    """手动备用模式：结构同主备，切换由人工执行。"""


class MemberRole(str, Enum):
    """冗余成员角色。"""

    PRIMARY = "primary"
    """主节点（主备 / 手动备用模式）。"""

    STANDBY = "standby"
    """备用节点（主备 / 手动备用模式）。"""

    ACTIVE = "active"
    """双活成员（双活模式）。"""


class RedundancyMemberInput(BaseModel):
    """创建 / 更新冗余组时的成员输入。

    `priority` 数值**越小优先级越高**；主备与手动备用模式下备用节点必须指定
    `priority`，否则接口返回 400。
    """

    node_id: int = Field(..., description="节点 ID，必须属于同一拓扑")
    member_role: MemberRole = Field(..., description="成员角色")
    priority: int | None = Field(
        None, ge=0, description="备用优先级，数值越小优先级越高（备用节点必填）"
    )


class RedundancyGroupCreate(BaseModel):
    """创建冗余组请求体（一次提交完整成员）。"""

    name: str = Field(..., min_length=1, max_length=128, description="冗余组名称")
    redundancy_type: RedundancyType = Field(
        RedundancyType.ACTIVE_STANDBY, description="冗余模式"
    )
    description: str | None = Field(None, description="冗余组说明")
    members: list[RedundancyMemberInput] = Field(
        default_factory=list, description="成员列表（主节点 + 备用节点）"
    )


class RedundancyGroupUpdate(BaseModel):
    """更新冗余组请求体，字段均可选。

    提供 `members` 时会**整体替换**成员列表（仍然是单次请求提交完整结构）。
    """

    name: str | None = Field(None, min_length=1, max_length=128)
    redundancy_type: RedundancyType | None = None
    description: str | None = None
    members: list[RedundancyMemberInput] | None = None


class RedundancyMemberRead(BaseModel):
    """冗余成员响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    redundancy_group_id: int
    node_id: int
    node_name: str
    member_role: MemberRole
    priority: int | None
    created_at: datetime


class RedundancyGroupRead(BaseModel):
    """冗余组响应（含成员）。"""

    id: int
    topology_id: int
    name: str
    redundancy_type: RedundancyType
    description: str | None
    members: list[RedundancyMemberRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
