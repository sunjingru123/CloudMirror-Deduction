"""故障传播分析相关的 Pydantic Schema。

传播方向的说明见 `services/propagation_service.py` 与 `docs/项目说明.md`。
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.fault import FaultSeverity, FaultType


class ImpactLevel(str, Enum):
    """影响等级。

    - direct：直接依赖故障源的节点（传播距离为 1）。
    - indirect：经由其他受影响节点间接传播到的节点。
    """

    DIRECT = "direct"
    INDIRECT = "indirect"


class AnalysisRequest(BaseModel):
    """传播分析请求体。

    `fault_ids` 为空或不传时，分析当前拓扑全部 `active` 故障。
    """

    fault_ids: list[int] | None = Field(
        None, description="参与本次分析的故障事件 ID；为空则使用全部激活故障"
    )


class PathStepRead(BaseModel):
    """传播路径中的一步。"""

    node_id: int | None
    node_name: str


class FaultSourceRead(BaseModel):
    """参与分析的故障源快照。"""

    fault_id: int | None
    source_node_id: int | None
    source_node_name: str
    fault_type: FaultType
    severity: FaultSeverity


class AffectedNodeRead(BaseModel):
    """单个受影响节点的影响详情。"""

    node_id: int | None
    node_name: str
    impact_level: ImpactLevel
    distance: int
    source_fault_id: int | None
    source_node_id: int | None
    propagation_path: list[PathStepRead] = Field(default_factory=list)


class PropagationPathRead(BaseModel):
    """一条完整的传播路径（从故障源到受影响节点）。"""

    source_fault_id: int | None
    source_node_id: int | None
    target_node_id: int | None
    target_node_name: str
    distance: int
    steps: list[PathStepRead] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    """一次传播分析的完整结果。"""

    analysis_id: int
    topology_id: int
    fault_sources: list[FaultSourceRead] = Field(default_factory=list)
    affected_nodes: list[AffectedNodeRead] = Field(default_factory=list)
    direct_affected_count: int
    indirect_affected_count: int
    total_affected_count: int
    total_node_count: int
    impact_ratio: float
    propagation_paths: list[PropagationPathRead] = Field(default_factory=list)
    analysis_time: datetime


class AnalysisHistoryItem(BaseModel):
    """历史分析列表中的一行（汇总指标）。"""

    analysis_id: int
    topology_id: int
    topology_name: str
    analysis_time: datetime
    fault_source_count: int
    direct_affected_count: int
    indirect_affected_count: int
    total_affected_count: int
    total_node_count: int
    impact_ratio: float


class AnalysisHistoryPage(BaseModel):
    """分页后的历史分析列表。"""

    total: int
    page: int
    page_size: int
    items: list[AnalysisHistoryItem] = Field(default_factory=list)
