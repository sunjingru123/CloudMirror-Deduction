"""故障事件的 ORM 模型。

设计要点（务必区分三类「状态」，避免混淆）：

1. 节点原始状态：`TopologyNode.status`，表示节点自身的配置 / 期望状态，
   不因注入故障而被改写。
2. 当前激活的故障事件：`FaultEvent` 中 `status = active` 的记录，
   表示「此刻正在发生的故障」。
3. 算法计算出的影响状态：由传播分析服务根据拓扑与激活故障推导，
   仅存在于分析结果中，不落回节点表。

依赖方向约定见 `app/models/topology.py`：边 A → B 表示 A 依赖 B，
故障传播方向与之相反（B 故障时 A 可能受影响）。
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.topology import utcnow

if TYPE_CHECKING:  # pragma: no cover - 仅供类型检查
    from app.models.topology import Topology, TopologyNode


class FaultEvent(Base):
    """故障事件记录。

    同一节点允许存在多个不同类型的故障；对「同一节点的同一故障类型」，
    业务层会拦截重复的激活故障（见 `services/fault_service.py`）。

    恢复故障只更新 `status` 与 `recovered_at`，不删除记录，保留历史。
    """

    __tablename__ = "fault_event"
    __table_args__ = (
        Index("ix_fault_event_topology_status", "topology_id", "status"),
        Index("ix_fault_event_source_node", "source_node_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topology_id: Mapped[int] = mapped_column(
        ForeignKey("topology.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 故障源节点
    source_node_id: Mapped[int] = mapped_column(
        ForeignKey("topology_node.id", ondelete="CASCADE"), nullable=False
    )
    # 故障类型、严重程度、状态以字符串存储，取值范围由 Pydantic 枚举约束
    fault_type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    recovered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    topology: Mapped["Topology"] = relationship(back_populates="faults")
    source_node: Mapped["TopologyNode"] = relationship()
