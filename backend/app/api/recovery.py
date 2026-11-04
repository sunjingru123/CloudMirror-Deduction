"""恢复策略推荐接口。

路由均挂在 `/topologies` 前缀下：

- `POST /topologies/{topology_id}/recovery/recommend`：生成恢复策略并推荐
- `GET  /topologies/{topology_id}/recovery/strategies`：查询策略类型与评分配置

所有估算值均为规则模拟结果，详见 `services/recovery_service.py`。
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.recovery import (
    RecoveryRecommendation,
    RecoveryRequest,
    StrategyConfigResponse,
)
from app.services import recovery_service

router = APIRouter(prefix="/topologies", tags=["recovery"])


@router.post(
    "/{topology_id}/recovery/recommend",
    response_model=RecoveryRecommendation,
    status_code=status.HTTP_201_CREATED,
    summary="生成恢复策略并给出推荐",
)
def recommend(
    topology_id: int,
    payload: RecoveryRequest | None = None,
    db: Session = Depends(get_db),
) -> RecoveryRecommendation:
    return recovery_service.recommend(db, topology_id, payload)


@router.get(
    "/{topology_id}/recovery/strategies",
    response_model=StrategyConfigResponse,
    summary="查询恢复策略类型与评分配置",
)
def list_strategies(
    topology_id: int, db: Session = Depends(get_db)
) -> StrategyConfigResponse:
    return recovery_service.list_strategy_config(db, topology_id)
