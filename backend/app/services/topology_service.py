"""拓扑业务服务层。

集中处理拓扑、节点与依赖关系的增删改查，并在数据非法时抛出
`app.services.exceptions` 中定义的业务异常。

依赖方向：source_node_id 依赖 target_node_id（source → target）。
"""

from enum import Enum

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.topology import Topology, TopologyEdge, TopologyNode
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
from app.services.exceptions import ConflictError, InvalidOperationError, NotFoundError


# --------------------------------------------------------------------------- #
# 内部辅助函数
# --------------------------------------------------------------------------- #
def _get_topology_or_404(db: Session, topology_id: int) -> Topology:
    topology = db.get(Topology, topology_id)
    if topology is None:
        raise NotFoundError(f"拓扑不存在：id={topology_id}")
    return topology


def _get_node_or_404(db: Session, topology_id: int, node_id: int) -> TopologyNode:
    node = db.get(TopologyNode, node_id)
    if node is None or node.topology_id != topology_id:
        raise NotFoundError(f"节点不存在：topology_id={topology_id}, node_id={node_id}")
    return node


def _topology_counts(db: Session, topology_id: int) -> tuple[int, int]:
    node_count = (
        db.query(func.count(TopologyNode.id))
        .filter(TopologyNode.topology_id == topology_id)
        .scalar()
        or 0
    )
    edge_count = (
        db.query(func.count(TopologyEdge.id))
        .filter(TopologyEdge.topology_id == topology_id)
        .scalar()
        or 0
    )
    return int(node_count), int(edge_count)


def _to_read(db: Session, topology: Topology) -> TopologyRead:
    node_count, edge_count = _topology_counts(db, topology.id)
    return TopologyRead(
        id=topology.id,
        name=topology.name,
        description=topology.description,
        created_at=topology.created_at,
        updated_at=topology.updated_at,
        node_count=node_count,
        edge_count=edge_count,
    )


def _ensure_topology_name_available(
    db: Session, name: str, exclude_id: int | None = None
) -> None:
    query = db.query(Topology).filter(Topology.name == name)
    if exclude_id is not None:
        query = query.filter(Topology.id != exclude_id)
    if query.first() is not None:
        raise ConflictError(f"拓扑名称已存在：{name}")


# --------------------------------------------------------------------------- #
# 拓扑
# --------------------------------------------------------------------------- #
def list_topologies(db: Session) -> list[TopologyRead]:
    """返回全部拓扑的摘要信息（含节点与依赖数量）。"""
    topologies = db.query(Topology).order_by(Topology.id).all()
    node_counts = dict(
        db.query(TopologyNode.topology_id, func.count(TopologyNode.id))
        .group_by(TopologyNode.topology_id)
        .all()
    )
    edge_counts = dict(
        db.query(TopologyEdge.topology_id, func.count(TopologyEdge.id))
        .group_by(TopologyEdge.topology_id)
        .all()
    )
    return [
        TopologyRead(
            id=t.id,
            name=t.name,
            description=t.description,
            created_at=t.created_at,
            updated_at=t.updated_at,
            node_count=int(node_counts.get(t.id, 0)),
            edge_count=int(edge_counts.get(t.id, 0)),
        )
        for t in topologies
    ]


def create_topology(db: Session, payload: TopologyCreate) -> TopologyRead:
    """创建拓扑。"""
    _ensure_topology_name_available(db, payload.name)
    topology = Topology(name=payload.name, description=payload.description)
    db.add(topology)
    db.commit()
    db.refresh(topology)
    return _to_read(db, topology)


def get_topology_detail(db: Session, topology_id: int) -> TopologyDetail:
    """获取拓扑详情，包含全部节点与依赖关系。"""
    topology = (
        db.query(Topology)
        .options(selectinload(Topology.nodes), selectinload(Topology.edges))
        .filter(Topology.id == topology_id)
        .first()
    )
    if topology is None:
        raise NotFoundError(f"拓扑不存在：id={topology_id}")

    nodes = sorted(topology.nodes, key=lambda n: n.id)
    edges = sorted(topology.edges, key=lambda e: e.id)
    return TopologyDetail(
        id=topology.id,
        name=topology.name,
        description=topology.description,
        created_at=topology.created_at,
        updated_at=topology.updated_at,
        nodes=[TopologyNodeRead.model_validate(n) for n in nodes],
        edges=[TopologyEdgeRead.model_validate(e) for e in edges],
    )


def update_topology(
    db: Session, topology_id: int, payload: TopologyUpdate
) -> TopologyRead:
    """更新拓扑基本信息。"""
    topology = _get_topology_or_404(db, topology_id)
    data = payload.model_dump(exclude_unset=True)

    new_name = data.get("name")
    if new_name is not None and new_name != topology.name:
        _ensure_topology_name_available(db, new_name, exclude_id=topology.id)

    for field, value in data.items():
        setattr(topology, field, value)

    db.commit()
    db.refresh(topology)
    return _to_read(db, topology)


def delete_topology(db: Session, topology_id: int) -> None:
    """删除拓扑，其节点与依赖关系一并删除。"""
    topology = _get_topology_or_404(db, topology_id)
    db.delete(topology)
    db.commit()


# --------------------------------------------------------------------------- #
# 节点
# --------------------------------------------------------------------------- #
def add_node(
    db: Session, topology_id: int, payload: TopologyNodeCreate
) -> TopologyNodeRead:
    """在指定拓扑中添加节点。"""
    topology = _get_topology_or_404(db, topology_id)
    node = TopologyNode(
        topology_id=topology.id,
        name=payload.name,
        type=payload.type.value,
        description=payload.description,
        status=payload.status.value,
        position_x=payload.position_x,
        position_y=payload.position_y,
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return TopologyNodeRead.model_validate(node)


def update_node(
    db: Session, topology_id: int, node_id: int, payload: TopologyNodeUpdate
) -> TopologyNodeRead:
    """编辑节点属性。"""
    node = _get_node_or_404(db, topology_id, node_id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        if isinstance(value, Enum):
            value = value.value
        setattr(node, field, value)

    db.commit()
    db.refresh(node)
    return TopologyNodeRead.model_validate(node)


def delete_node(db: Session, topology_id: int, node_id: int) -> None:
    """删除节点，并级联删除与其相关的依赖关系。"""
    node = _get_node_or_404(db, topology_id, node_id)
    db.query(TopologyEdge).filter(
        or_(
            TopologyEdge.source_node_id == node.id,
            TopologyEdge.target_node_id == node.id,
        )
    ).delete(synchronize_session=False)
    db.delete(node)
    db.commit()


# --------------------------------------------------------------------------- #
# 依赖关系
# --------------------------------------------------------------------------- #
def add_edge(
    db: Session, topology_id: int, payload: TopologyEdgeCreate
) -> TopologyEdgeRead:
    """创建依赖关系：source 依赖 target。"""
    topology = _get_topology_or_404(db, topology_id)

    if payload.source_node_id == payload.target_node_id:
        raise InvalidOperationError("节点不能依赖自身（source 与 target 不能相同）")

    source = db.get(TopologyNode, payload.source_node_id)
    if source is None or source.topology_id != topology.id:
        raise NotFoundError(
            f"源节点不存在于该拓扑：node_id={payload.source_node_id}"
        )

    target = db.get(TopologyNode, payload.target_node_id)
    if target is None or target.topology_id != topology.id:
        raise NotFoundError(
            f"目标节点不存在于该拓扑：node_id={payload.target_node_id}"
        )

    duplicate = (
        db.query(TopologyEdge)
        .filter(
            TopologyEdge.topology_id == topology.id,
            TopologyEdge.source_node_id == payload.source_node_id,
            TopologyEdge.target_node_id == payload.target_node_id,
        )
        .first()
    )
    if duplicate is not None:
        raise ConflictError("依赖关系已存在（不允许重复边）")

    edge = TopologyEdge(
        topology_id=topology.id,
        source_node_id=payload.source_node_id,
        target_node_id=payload.target_node_id,
        description=payload.description,
    )
    db.add(edge)
    try:
        db.commit()
    except IntegrityError as exc:  # 数据库层约束兜底
        db.rollback()
        raise ConflictError("依赖关系已存在或非法") from exc

    db.refresh(edge)
    return TopologyEdgeRead.model_validate(edge)


def delete_edge(db: Session, topology_id: int, edge_id: int) -> None:
    """删除依赖关系。"""
    _get_topology_or_404(db, topology_id)
    edge = (
        db.query(TopologyEdge)
        .filter(TopologyEdge.id == edge_id, TopologyEdge.topology_id == topology_id)
        .first()
    )
    if edge is None:
        raise NotFoundError(f"依赖关系不存在：edge_id={edge_id}")
    db.delete(edge)
    db.commit()
