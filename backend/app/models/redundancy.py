"""冗余关系相关的 ORM 模型。

与「依赖关系」的区别（务必区分）
--------------------------------

- `topology_edge`（依赖关系）：描述**业务调用**方向，边 A → B 表示「A 依赖 B」，
  是故障传播分析的输入。
- `redundancy_group` / `redundancy_member`（冗余关系）：描述**同一业务角色**的
  多个节点之间「谁能顶替谁」的运维关系，是恢复策略 `failover` 的输入。

两者语义完全独立：冗余关系不参与故障传播计算，依赖关系也不代表冗余能力。

冗余模式（`redundancy_type`）
----------------------------

- `active_standby`：主备模式。必须有且只有一个 `primary`，至少一个 `standby`。
- `active_active`：双活模式。成员角色均为 `active`，至少两个成员。
- `manual_standby`：手动备用模式。结构同主备模式（一个 `primary` + 若干 `standby`），
  区别仅在于切换由人工执行（当前版本对二者的适用性判定相同）。

约束说明
--------

数据库层保证：
1. 冗余组只能引用**本拓扑**节点（服务层校验 + 外键指向 `topology_node`）。
2. 同一节点不能在同一冗余组中重复出现（唯一约束 `uq_redundancy_member_group_node`）。
3. 删除节点时，`topology_node` 的外键 `ON DELETE CASCADE` 会清理成员行；
   服务层同时会重新校验冗余组是否仍然满足模式约束。
4. 删除拓扑时级联删除冗余组及成员。

服务层保证（数据库无法表达的约束）：
5. 主备模式必须有且只有一个主节点、至少一个备用节点。
6. **当前版本限制**：同一拓扑内，一个节点最多只能加入一个冗余组。跨组复用
   （例如一个节点既是 A 组的主节点、又是 B 组的备用节点）暂不支持，服务层会
   明确拒绝并说明原因。

重要说明：冗余关系只是**虚拟推演模型**中的声明。当前版本不执行真实切流，
不校验真实容量、网络连通性、数据同步与配置一致性。
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.topology import utcnow

if TYPE_CHECKING:  # pragma: no cover - 仅供类型检查
    from app.models.topology import Topology, TopologyNode


class RedundancyGroup(Base):
    """冗余组：一组可以互相顶替的节点。"""

    __tablename__ = "redundancy_group"
    __table_args__ = (Index("ix_redundancy_group_topology", "topology_id", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topology_id: Mapped[int] = mapped_column(
        ForeignKey("topology.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # 冗余模式：active_standby / active_active / manual_standby
    redundancy_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    topology: Mapped["Topology"] = relationship(back_populates="redundancy_groups")
    members: Mapped[list["RedundancyMember"]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class RedundancyMember(Base):
    """冗余组中的一个成员节点。"""

    __tablename__ = "redundancy_member"
    __table_args__ = (
        UniqueConstraint(
            "redundancy_group_id",
            "node_id",
            name="uq_redundancy_member_group_node",
        ),
        Index("ix_redundancy_member_group", "redundancy_group_id"),
        Index("ix_redundancy_member_node", "node_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    redundancy_group_id: Mapped[int] = mapped_column(
        ForeignKey("redundancy_group.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[int] = mapped_column(
        ForeignKey("topology_node.id", ondelete="CASCADE"), nullable=False
    )
    # 成员角色：primary / standby / active
    member_role: Mapped[str] = mapped_column(String(16), nullable=False)
    # 备用优先级：数值越小优先级越高；主备 / 手动备用模式下备用节点必须明确指定
    priority: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    group: Mapped[RedundancyGroup] = relationship(back_populates="members")
    node: Mapped["TopologyNode"] = relationship()
