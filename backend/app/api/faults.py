"""故障注入与传播分析接口。

包含两组路由：

- `/topologies/{topology_id}/faults`、`/topologies/{topology_id}/analyze`：
  拓扑作用域下的故障注入、查询与分析。
- `/faults/{fault_id}`、`/faults/{fault_id}/recover`：故障详情与恢复。

依赖方向与传播方向的约定见 `app/services/propagation_service.py`。
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.analysis import AnalysisRequest, AnalysisResult
from app.schemas.fault import FaultEventCreate, FaultEventRead
from app.services import fault_service, propagation_service

# 拓扑作用域：/topologies/{id}/faults、/analyze、/analysis/latest
topology_router = APIRouter(prefix="/topologies", tags=["fault"])
# 故障作用域：/faults/{id}
fault_router = APIRouter(prefix="/faults", tags=["fault"])


# --------------------------------------------------------------------------- #
# 故障注入与查询
# --------------------------------------------------------------------------- #
@topology_router.post(
    "/{topology_id}/faults",
    response_model=FaultEventRead,
    status_code=status.HTTP_201_CREATED,
    summary="注入故障",
)
def create_fault(
    topology_id: int, payload: FaultEventCreate, db: Session = Depends(get_db)
) -> FaultEventRead:
    return fault_service.create_fault(db, topology_id, payload)


@topology_router.get(
    "/{topology_id}/faults",
    response_model=list[FaultEventRead],
    summary="查询拓扑的故障事件",
)
def list_faults(topology_id: int, db: Session = Depends(get_db)) -> list[FaultEventRead]:
    return fault_service.list_faults(db, topology_id)


# --------------------------------------------------------------------------- #
# 传播分析
# --------------------------------------------------------------------------- #
@topology_router.post(
    "/{topology_id}/analyze",
    response_model=AnalysisResult,
    summary="执行故障传播分析",
)
def analyze(
    topology_id: int,
    payload: AnalysisRequest | None = None,
    db: Session = Depends(get_db),
) -> AnalysisResult:
    fault_ids = payload.fault_ids if payload is not None else None
    return propagation_service.run_analysis(db, topology_id, fault_ids)


@topology_router.get(
    "/{topology_id}/analysis/latest",
    response_model=AnalysisResult,
    summary="读取最近一次传播分析结果",
)
def latest_analysis(topology_id: int, db: Session = Depends(get_db)) -> AnalysisResult:
    return propagation_service.get_latest_analysis(db, topology_id)


# --------------------------------------------------------------------------- #
# 故障详情与恢复
# --------------------------------------------------------------------------- #
@fault_router.get("/{fault_id}", response_model=FaultEventRead, summary="查询故障详情")
def get_fault(fault_id: int, db: Session = Depends(get_db)) -> FaultEventRead:
    return fault_service.get_fault(db, fault_id)


@fault_router.post(
    "/{fault_id}/recover",
    response_model=FaultEventRead,
    summary="恢复故障",
)
def recover_fault(fault_id: int, db: Session = Depends(get_db)) -> FaultEventRead:
    return fault_service.recover_fault(db, fault_id)
