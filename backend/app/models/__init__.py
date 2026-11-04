"""ORM 模型包。

在此导入所有模型，使其注册到 `Base.metadata`，从而被 `init_db()` 建表。
"""

from app.models.analysis import (
    AnalysisAffectedNode,
    AnalysisFaultSource,
    AnalysisPathStep,
    PropagationAnalysis,
)
from app.models.fault import FaultEvent
from app.models.recovery import RecoveryPlan, RecoveryStrategy, RecoveryStrategyNote
from app.models.topology import Topology, TopologyEdge, TopologyNode

__all__ = [
    "Topology",
    "TopologyNode",
    "TopologyEdge",
    "FaultEvent",
    "PropagationAnalysis",
    "AnalysisFaultSource",
    "AnalysisAffectedNode",
    "AnalysisPathStep",
    "RecoveryPlan",
    "RecoveryStrategy",
    "RecoveryStrategyNote",
]
