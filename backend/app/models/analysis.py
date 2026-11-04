"""故障传播分析结果的 ORM 模型。

分析结果采用**规范化的父子表**存储，而不是把整段 JSON 塞进单个字段：

- `propagation_analysis`：一次分析的汇总指标。
- `analysis_fault_source`：本次分析参与的故障源快照。
- `analysis_affected_node`：每个受影响节点的影响等级、距离、来源故障。
- `analysis_path_step`：某受影响节点的完整传播路径（有序步骤）。

所有结果都可以由「拓扑结构 + 故障记录」重新推导，不含随机成分。
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.topology import utcnow

if TYPE_CHECKING:  # pragma: no cover - 仅供类型检查
    from app.models.fault import FaultEvent
    from app.models.topology import Topology, TopologyNode


class PropagationAnalysis(Base):
    """一次故障传播分析的汇总结果。"""

    __tablename__ = "propagation_analysis"
    __table_args__ = (Index("ix_propagation_analysis_topology", "topology_id", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topology_id: Mapped[int] = mapped_column(
        ForeignKey("topology.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fault_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    direct_affected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    indirect_affected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_affected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_node_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    impact_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # 分析使用的故障源数量为 0 时同样落库，便于「无故障」场景返回空结果
    analysis_time: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    topology: Mapped["Topology"] = relationship(back_populates="analyses")
    fault_sources: Mapped[list["AnalysisFaultSource"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan", passive_deletes=True
    )
    affected_nodes: Mapped[list["AnalysisAffectedNode"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan", passive_deletes=True
    )


class AnalysisFaultSource(Base):
    """分析参与的故障源快照。"""

    __tablename__ = "analysis_fault_source"
    __table_args__ = (Index("ix_analysis_fault_source_analysis", "analysis_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("propagation_analysis.id", ondelete="CASCADE"), nullable=False
    )
    fault_id: Mapped[int | None] = mapped_column(
        ForeignKey("fault_event.id", ondelete="SET NULL"), nullable=True
    )
    node_id: Mapped[int | None] = mapped_column(
        ForeignKey("topology_node.id", ondelete="SET NULL"), nullable=True
    )
    node_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    fault_type: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="")

    analysis: Mapped[PropagationAnalysis] = relationship(back_populates="fault_sources")


class AnalysisAffectedNode(Base):
    """单个受影响节点的影响详情。"""

    __tablename__ = "analysis_affected_node"
    __table_args__ = (
        Index("ix_analysis_affected_node_analysis", "analysis_id"),
        Index("ix_analysis_affected_node_node", "node_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("propagation_analysis.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[int | None] = mapped_column(
        ForeignKey("topology_node.id", ondelete="SET NULL"), nullable=True
    )
    node_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    # impact_level: direct / indirect
    impact_level: Mapped[str] = mapped_column(String(16), nullable=False)
    distance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_fault_id: Mapped[int | None] = mapped_column(
        ForeignKey("fault_event.id", ondelete="SET NULL"), nullable=True
    )
    source_node_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    analysis: Mapped[PropagationAnalysis] = relationship(back_populates="affected_nodes")
    path_steps: Mapped[list["AnalysisPathStep"]] = relationship(
        back_populates="affected_node", cascade="all, delete-orphan", passive_deletes=True
    )


class AnalysisPathStep(Base):
    """传播路径中的一步（有序）。

    路径从故障源节点出发，沿传播方向依次记录到达受影响节点的节点序列。
    """

    __tablename__ = "analysis_path_step"
    __table_args__ = (Index("ix_analysis_path_step_affected", "affected_node_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    affected_node_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_affected_node.id", ondelete="CASCADE"), nullable=False
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    node_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    node_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")

    affected_node: Mapped[AnalysisAffectedNode] = relationship(back_populates="path_steps")
