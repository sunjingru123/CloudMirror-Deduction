"""拓扑管理接口。

依赖方向约定：边 A → B 表示「A 依赖 B」，即 source 为依赖方、target 为被依赖方。
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.topology import (
    TopologyCreate,
    TopologyDetail,
    TopologyEdgeCreate,
    TopologyEdgeRead,
    TopologyNodeCreate,
    TopologyNodeRead,
    TopologyNodeUpdate,
    TopologyRead,
    TopologyUpdate,
)
from app.services import topology_service

router = APIRouter(prefix="/topologies", tags=["topology"])


# ------------------------------- 拓扑 ------------------------------- #
@router.post(
    "",
    response_model=TopologyRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建拓扑",
)
def create_topology(payload: TopologyCreate, db: Session = Depends(get_db)) -> TopologyRead:
    return topology_service.create_topology(db, payload)


@router.get("", response_model=list[TopologyRead], summary="查询拓扑列表")
def list_topologies(db: Session = Depends(get_db)) -> list[TopologyRead]:
    return topology_service.list_topologies(db)


@router.get("/{topology_id}", response_model=TopologyDetail, summary="获取拓扑详情")
def get_topology(topology_id: int, db: Session = Depends(get_db)) -> TopologyDetail:
    return topology_service.get_topology_detail(db, topology_id)


@router.put("/{topology_id}", response_model=TopologyRead, summary="更新拓扑基本信息")
def update_topology(
    topology_id: int, payload: TopologyUpdate, db: Session = Depends(get_db)
) -> TopologyRead:
    return topology_service.update_topology(db, topology_id, payload)


@router.delete(
    "/{topology_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除拓扑",
)
def delete_topology(topology_id: int, db: Session = Depends(get_db)) -> None:
    topology_service.delete_topology(db, topology_id)


# ------------------------------- 节点 ------------------------------- #
@router.post(
    "/{topology_id}/nodes",
    response_model=TopologyNodeRead,
    status_code=status.HTTP_201_CREATED,
    summary="添加节点",
)
def add_node(
    topology_id: int, payload: TopologyNodeCreate, db: Session = Depends(get_db)
) -> TopologyNodeRead:
    return topology_service.add_node(db, topology_id, payload)


@router.put(
    "/{topology_id}/nodes/{node_id}",
    response_model=TopologyNodeRead,
    summary="编辑节点",
)
def update_node(
    topology_id: int,
    node_id: int,
    payload: TopologyNodeUpdate,
    db: Session = Depends(get_db),
) -> TopologyNodeRead:
    return topology_service.update_node(db, topology_id, node_id, payload)


@router.delete(
    "/{topology_id}/nodes/{node_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除节点",
)
def delete_node(topology_id: int, node_id: int, db: Session = Depends(get_db)) -> None:
    topology_service.delete_node(db, topology_id, node_id)


# ---------------------------- 依赖关系 ---------------------------- #
@router.post(
    "/{topology_id}/edges",
    response_model=TopologyEdgeRead,
    status_code=status.HTTP_201_CREATED,
    summary="添加依赖关系",
)
def add_edge(
    topology_id: int, payload: TopologyEdgeCreate, db: Session = Depends(get_db)
) -> TopologyEdgeRead:
    return topology_service.add_edge(db, topology_id, payload)


@router.delete(
    "/{topology_id}/edges/{edge_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除依赖关系",
)
def delete_edge(topology_id: int, edge_id: int, db: Session = Depends(get_db)) -> None:
    topology_service.delete_edge(db, topology_id, edge_id)
