"""冗余关系（显式主备 / 双活）接口。

两组路由：

- `/topologies/{topology_id}/redundancy-groups`：拓扑作用域下的冗余组创建与列表。
- `/redundancy-groups/{group_id}`：单个冗余组的详情、更新与删除。

冗余关系与依赖边（`topology_edge`）语义不同：前者是恢复策略 `failover` 的输入，
后者是故障传播分析的输入。详见 `app/models/redundancy.py`。
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.redundancy import (
    RedundancyGroupCreate,
    RedundancyGroupRead,
    RedundancyGroupUpdate,
)
from app.services import redundancy_service

topology_router = APIRouter(prefix="/topologies", tags=["redundancy"])
group_router = APIRouter(prefix="/redundancy-groups", tags=["redundancy"])


@topology_router.post(
    "/{topology_id}/redundancy-groups",
    response_model=RedundancyGroupRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建冗余组（一次提交完整主备结构）",
)
def create_group(
    topology_id: int, payload: RedundancyGroupCreate, db: Session = Depends(get_db)
) -> RedundancyGroupRead:
    return redundancy_service.create_group(db, topology_id, payload)


@topology_router.get(
    "/{topology_id}/redundancy-groups",
    response_model=list[RedundancyGroupRead],
    summary="查询拓扑的冗余组列表",
)
def list_groups(topology_id: int, db: Session = Depends(get_db)) -> list[RedundancyGroupRead]:
    return redundancy_service.list_groups(db, topology_id)


@group_router.get("/{group_id}", response_model=RedundancyGroupRead, summary="查询冗余组详情")
def get_group(group_id: int, db: Session = Depends(get_db)) -> RedundancyGroupRead:
    return redundancy_service.get_group(db, group_id)


@group_router.put("/{group_id}", response_model=RedundancyGroupRead, summary="更新冗余组")
def update_group(
    group_id: int, payload: RedundancyGroupUpdate, db: Session = Depends(get_db)
) -> RedundancyGroupRead:
    return redundancy_service.update_group(db, group_id, payload)


@group_router.delete(
    "/{group_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除冗余组"
)
def delete_group(group_id: int, db: Session = Depends(get_db)) -> None:
    redundancy_service.delete_group(db, group_id)
