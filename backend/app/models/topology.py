"""拓扑相关的 ORM 模型。

依赖方向约定（前后端必须保持一致）：

    边 A → B 表示「A 依赖 B」，即 source_node_id = A（依赖方）、
    target_node_id = B（被依赖方）。

    当 B 出现故障时，A 可能受到影响。因此故障传播方向与依赖方向相反：
    依赖边 A → B 对应的传播路径为 B → A。

    Vue Flow 中边的 source/target 与后端字段一一对应，箭头指向 B（被依赖方），
    不会与画布上的箭头方向产生歧义。
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:  # pragma: no cover - 仅供类型检查
    from app.models.analysis import PropagationAnalysis
    from app.models.fault import FaultEvent
    from app.models.redundancy import RedundancyGroup


def utcnow() -> datetime:
    """返回不带时区信息的 UTC 当前时间，便于 SQLite 统一存储。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Topology(Base):
    """业务系统拓扑。"""

    __tablename__ = "topology"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    nodes: Mapped[list["TopologyNode"]] = relationship(
        back_populates="topology",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    edges: Mapped[list["TopologyEdge"]] = relationship(
        back_populates="topology",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    faults: Mapped[list["FaultEvent"]] = relationship(
        back_populates="topology",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    analyses: Mapped[list["PropagationAnalysis"]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    # 冗余关系（显式主备 / 双活声明），与依赖边语义不同，见 models/redundancy.py
    redundancy_groups: Mapped[list["RedundancyGroup"]] = relationship(
        back_populates="topology",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class TopologyNode(Base):
    """拓扑中的系统节点。"""

    __tablename__ = "topology_node"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topology_id: Mapped[int] = mapped_column(
        ForeignKey("topology.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # 节点类型与状态以字符串存储，取值范围由 Pydantic 枚举约束
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="healthy")
    position_x: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    position_y: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    topology: Mapped[Topology] = relationship(back_populates="nodes")


class TopologyEdge(Base):
    """节点之间的依赖关系。

    方向约定：source_node_id 依赖 target_node_id（source → target）。
    """

    __tablename__ = "topology_edge"
    __table_args__ = (
        UniqueConstraint(
            "topology_id",
            "source_node_id",
            "target_node_id",
            name="uq_topology_edge_unique",
        ),
        CheckConstraint(
            "source_node_id <> target_node_id",
            name="ck_topology_edge_no_self_loop",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topology_id: Mapped[int] = mapped_column(
        ForeignKey("topology.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 依赖方
    source_node_id: Mapped[int] = mapped_column(
        ForeignKey("topology_node.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 被依赖方
    target_node_id: Mapped[int] = mapped_column(
        ForeignKey("topology_node.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    topology: Mapped[Topology] = relationship(back_populates="edges")
