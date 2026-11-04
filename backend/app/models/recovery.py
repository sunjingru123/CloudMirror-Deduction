"""恢复策略相关的 ORM 模型。

设计说明
--------

- `recovery_plan`：一次「恢复策略推荐」的结果（对应某次传播分析 `analysis_id`）。
- `recovery_strategy`：该次推荐中每种候选策略的评估结果（策略类型、是否适用、
  估算指标、风险等级、推荐评分等）。
- `recovery_strategy_note`：策略的优势 / 劣势 / 前置条件条目（规范化子表，非 JSON 大字段）。
- `recovery_standby_candidate`：`failover` 策略评估过的备用节点候选（含是否可用）。
- `recovery_prerequisite_check`：`failover` 策略的逐项适用性检查结果。

重要说明：`estimated_*` 字段与 `recommendation_score` 均为**基于规则与配置参数的
模拟估算值**，不是真实生产环境的测量数据。评分模型为可解释的加权规则，
不使用随机数，也不使用机器学习模型。

`redundancy_group_id` / `primary_node_id` / `selected_standby_node_id` 使用普通
整数**软引用**而非外键：即使之后删除了冗余组或节点，历史推荐记录仍然可读。

依赖方向约定见 `app/models/topology.py`。
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.topology import utcnow

if TYPE_CHECKING:  # pragma: no cover - 仅供类型检查
    from app.models.analysis import PropagationAnalysis
    from app.models.topology import Topology


class RecoveryPlan(Base):
    """一次恢复策略推荐的汇总记录。"""

    __tablename__ = "recovery_plan"
    __table_args__ = (Index("ix_recovery_plan_topology", "topology_id", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topology_id: Mapped[int] = mapped_column(
        ForeignKey("topology.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 关联的传播分析（分析删除时保留计划，但置空关联）
    analysis_id: Mapped[int | None] = mapped_column(
        ForeignKey("propagation_analysis.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # 被推荐的策略（无可用策略时为空）；为避免表间循环外键，此处使用软引用
    recommended_strategy_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recommendation_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    estimation_notice: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    topology: Mapped["Topology"] = relationship()
    strategies: Mapped[list["RecoveryStrategy"]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="RecoveryStrategy.plan_id",
    )


class RecoveryStrategy(Base):
    """某次推荐中一种策略的评估结果。

    `strategy_id` 即主键 `id`；`strategy_type` 取值为
    `restart_service` / `failover` / `isolate_node`。
    """

    __tablename__ = "recovery_strategy"
    __table_args__ = (
        Index("ix_recovery_strategy_plan", "plan_id"),
        Index("ix_recovery_strategy_type", "strategy_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("recovery_plan.id", ondelete="CASCADE"), nullable=False
    )
    strategy_type: Mapped[str] = mapped_column(String(32), nullable=False)
    strategy_name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    applicable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # 不适用原因（applicable=True 时为空）
    inapplicable_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 估算恢复时间（秒），模拟估算值
    estimated_recovery_time: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # 估算受影响（需操作 / 会失去依赖）的节点数量
    estimated_affected_nodes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 资源成本与风险等级：low / medium / high
    estimated_resource_cost: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    # 推荐评分（0-100，规则加权，模拟估算值）
    recommendation_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # --- failover（备用节点切换）专用字段，其他策略为空 ---
    # 以下三个字段使用普通整数软引用，保证删除冗余组 / 节点后历史仍可读
    redundancy_group_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    redundancy_group_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    primary_node_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selected_standby_node_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    plan: Mapped[RecoveryPlan] = relationship(
        back_populates="strategies", foreign_keys=[plan_id]
    )
    notes: Mapped[list["RecoveryStrategyNote"]] = relationship(
        back_populates="strategy", cascade="all, delete-orphan", passive_deletes=True
    )
    standby_candidates: Mapped[list["RecoveryStandbyCandidate"]] = relationship(
        back_populates="strategy", cascade="all, delete-orphan", passive_deletes=True
    )
    prerequisite_checks: Mapped[list["RecoveryPrerequisiteCheck"]] = relationship(
        back_populates="strategy", cascade="all, delete-orphan", passive_deletes=True
    )


class RecoveryStrategyNote(Base):
    """策略的优势 / 劣势 / 前置条件条目（有序）。"""

    __tablename__ = "recovery_strategy_note"
    __table_args__ = (
        Index("ix_recovery_strategy_note_strategy", "strategy_id", "kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("recovery_strategy.id", ondelete="CASCADE"), nullable=False
    )
    # kind: advantage / disadvantage / prerequisite
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    strategy: Mapped[RecoveryStrategy] = relationship(back_populates="notes")


class RecoveryStandbyCandidate(Base):
    """`failover` 评估过的备用节点候选（有序）。

    `node_id` / `node_name` 为软引用与名称快照，节点被删除后仍可读。
    """

    __tablename__ = "recovery_standby_candidate"
    __table_args__ = (
        Index("ix_recovery_standby_candidate_strategy", "strategy_id", "position"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("recovery_strategy.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    node_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    node_name: Mapped[str] = mapped_column(String(128), nullable=False)
    priority: Mapped[int | None] = mapped_column(Integer, nullable=True)
    eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")

    strategy: Mapped[RecoveryStrategy] = relationship(back_populates="standby_candidates")


class RecoveryPrerequisiteCheck(Base):
    """`failover` 的逐项前置条件检查结果（有序）。"""

    __tablename__ = "recovery_prerequisite_check"
    __table_args__ = (
        Index("ix_recovery_prerequisite_check_strategy", "strategy_id", "position"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("recovery_strategy.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    check_name: Mapped[str] = mapped_column(String(128), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")

    strategy: Mapped[RecoveryStrategy] = relationship(back_populates="prerequisite_checks")
