"""推演历史（传播分析记录）接口。

- `GET /topologies/{topology_id}/analyses`：分页查询历史分析（时间倒序）
- `GET /topologies/{topology_id}/analyses/{analysis_id}`：读取单次分析的完整结果

历史结果在落库时保存了故障源与受影响节点的**名称快照**，
因此即使故障已被恢复、节点已被删除，历史分析仍可完整回看。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.analysis import AnalysisHistoryPage, AnalysisResult
from app.services import propagation_service

router = APIRouter(prefix="/topologies", tags=["analysis"])


@router.get(
    "/{topology_id}/analyses",
    response_model=AnalysisHistoryPage,
    summary="分页查询历史分析记录",
)
def list_analyses(
    topology_id: int,
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数，1-100"),
    db: Session = Depends(get_db),
) -> AnalysisHistoryPage:
    return propagation_service.list_analyses(db, topology_id, page, page_size)


@router.get(
    "/{topology_id}/analyses/{analysis_id}",
    response_model=AnalysisResult,
    summary="读取单次历史分析详情",
)
def get_analysis(
    topology_id: int, analysis_id: int, db: Session = Depends(get_db)
) -> AnalysisResult:
    return propagation_service.get_analysis(db, topology_id, analysis_id)
