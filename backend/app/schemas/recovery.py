"""恢复策略相关的 Pydantic Schema。

说明
----

- 所有 `estimated_*` 字段与 `recommendation_score` 均为**基于规则与配置参数的
  模拟估算值**，不是真实生产环境的测量数据。
- 评分模型为可解释的加权规则（权重见 `services/recovery_config.py`），
  不使用随机数，也不使用机器学习模型。
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class RecoveryStrategyType(str, Enum):
    """恢复策略类型。"""

    RESTART_SERVICE = "restart_service"
    FAILOVER = "failover"
    ISOLATE_NODE = "isolate_node"


class ResourceCost(str, Enum):
    """估算资源成本等级。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskLevel(str, Enum):
    """操作风险等级。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RecoveryRequest(BaseModel):
    """恢复策略推荐请求体。

    `analysis_id` 为空时使用该拓扑最近一次传播分析结果。
    """

    analysis_id: int | None = Field(
        None, description="参与本次策略对比的传播分析 ID；为空则使用最近一次分析"
    )


class PrerequisiteCheck(BaseModel):
    """单项前置条件检查结果。"""

    check_name: str
    passed: bool
    detail: str


class StandbyCandidateRead(BaseModel):
    """一个被评估的备用节点候选。

    `eligible=True` 仅表示当前模拟模型的规则判定它满足切换前提，
    不代表真实生产环境已验证容量、网络、数据同步与配置一致性。
    """

    node_id: int | None
    node_name: str
    priority: int | None = Field(None, description="数值越小优先级越高")
    eligible: bool
    detail: str


class RecoveryStrategyRead(BaseModel):
    """单个策略的评估结果。"""

    strategy_id: int
    strategy_type: RecoveryStrategyType
    strategy_name: str
    description: str
    applicable: bool
    inapplicable_reason: str | None = Field(None, description="不适用时的具体原因")
    estimated_recovery_time: float = Field(..., description="估算恢复时间（秒，模拟估算值）")
    estimated_affected_nodes: int = Field(
        ..., description="估算需要停机或短暂失去服务的节点数量"
    )
    estimated_resource_cost: ResourceCost
    risk_level: RiskLevel
    advantages: list[str] = Field(default_factory=list)
    disadvantages: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    recommendation_score: float = Field(..., description="规则加权评分（0-100，模拟估算值）")

    # --- 仅 failover 策略会填充的显式冗余字段，其余策略为空 ---
    redundancy_group_id: int | None = Field(None, description="所选显式冗余组 ID")
    redundancy_group_name: str | None = Field(None, description="所选显式冗余组名称")
    primary_node_id: int | None = Field(None, description="发生故障的主节点 ID")
    selected_standby_node_id: int | None = Field(
        None, description="被选中的备用节点 ID（按优先级选定）"
    )
    standby_candidates: list[StandbyCandidateRead] = Field(
        default_factory=list, description="评估过的备用节点候选（含是否可用）"
    )
    selection_reason: str | None = Field(None, description="备用节点选择理由")
    prerequisite_checks: list[PrerequisiteCheck] = Field(
        default_factory=list, description="逐项前置条件检查结果"
    )


class RecoveryRecommendation(BaseModel):
    """一次恢复策略推荐的完整结果。"""

    plan_id: int
    analysis_id: int
    topology_id: int
    strategies: list[RecoveryStrategyRead] = Field(default_factory=list)
    recommended_strategy_id: int | None = Field(
        None, description="推荐的策略 ID；没有可用策略时为空"
    )
    recommended_strategy_type: RecoveryStrategyType | None
    recommendation_reason: str
    estimation_notice: str
    created_at: datetime


class StrategyTypeInfo(BaseModel):
    """策略类型的配置说明（用于前端展示规则来源）。"""

    strategy_type: RecoveryStrategyType
    strategy_name: str
    description: str
    base_recovery_seconds: float
    per_node_seconds: float
    base_resource_cost: ResourceCost
    base_risk_level: RiskLevel
    prerequisites: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ScoringWeights(BaseModel):
    """评分权重（合计 1.00）。"""

    recovery_time: float
    impact: float
    cost: float
    risk: float
    business_recovery: float


class StrategyConfigResponse(BaseModel):
    """策略类型与评分配置。"""

    topology_id: int
    strategy_types: list[StrategyTypeInfo] = Field(default_factory=list)
    scoring_weights: ScoringWeights
    reference_recovery_seconds: float
    estimation_notice: str
