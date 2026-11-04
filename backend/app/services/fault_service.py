"""故障事件业务服务层。

负责故障注入、查询与恢复，并进行「拓扑 / 节点是否存在」「重复的同类激活故障」
等校验。恢复故障只更新状态与恢复时间，不删除历史记录。
"""

from sqlalchemy.orm import Session

from app.models.fault import FaultEvent
from app.models.topology import Topology, TopologyNode, utcnow
from app.schemas.fault import (
    FaultEventCreate,
    FaultEventRead,
    FaultSeverity,
    FaultStatus,
    FaultType,
)
from app.services.exceptions import ConflictError, NotFoundError


# --------------------------------------------------------------------------- #
# 内部辅助函数
# --------------------------------------------------------------------------- #
def _get_topology_or_404(db: Session, topology_id: int) -> Topology:
    topology = db.get(Topology, topology_id)
    if topology is None:
        raise NotFoundError(f"拓扑不存在：id={topology_id}")
    return topology


def _get_fault_or_404(db: Session, fault_id: int) -> FaultEvent:
    fault = db.get(FaultEvent, fault_id)
    if fault is None:
        raise NotFoundError(f"故障事件不存在：id={fault_id}")
    return fault


def _node_name_map(db: Session, node_ids: set[int]) -> dict[int, str]:
    if not node_ids:
        return {}
    rows = (
        db.query(TopologyNode.id, TopologyNode.name)
        .filter(TopologyNode.id.in_(node_ids))
        .all()
    )
    return {int(node_id): name for node_id, name in rows}


def _to_read(fault: FaultEvent, node_name: str | None) -> FaultEventRead:
    return FaultEventRead(
        id=fault.id,
        topology_id=fault.topology_id,
        source_node_id=fault.source_node_id,
        source_node_name=node_name,
        fault_type=FaultType(fault.fault_type),
        severity=FaultSeverity(fault.severity),
        description=fault.description,
        status=FaultStatus(fault.status),
        created_at=fault.created_at,
        recovered_at=fault.recovered_at,
    )


# --------------------------------------------------------------------------- #
# 查询
# --------------------------------------------------------------------------- #
def list_faults(db: Session, topology_id: int) -> list[FaultEventRead]:
    """返回指定拓扑的全部故障事件（含已恢复的历史记录）。"""
    _get_topology_or_404(db, topology_id)
    faults = (
        db.query(FaultEvent)
        .filter(FaultEvent.topology_id == topology_id)
        .order_by(FaultEvent.id)
        .all()
    )
    names = _node_name_map(db, {f.source_node_id for f in faults})
    return [_to_read(f, names.get(f.source_node_id)) for f in faults]


def list_active_faults(db: Session, topology_id: int) -> list[FaultEvent]:
    """返回指定拓扑当前激活的故障事件（供传播分析使用）。"""
    return (
        db.query(FaultEvent)
        .filter(FaultEvent.topology_id == topology_id, FaultEvent.status == FaultStatus.ACTIVE.value)
        .order_by(FaultEvent.id)
        .all()
    )


def get_fault(db: Session, fault_id: int) -> FaultEventRead:
    """获取故障事件详情。"""
    fault = _get_fault_or_404(db, fault_id)
    names = _node_name_map(db, {fault.source_node_id})
    return _to_read(fault, names.get(fault.source_node_id))


# --------------------------------------------------------------------------- #
# 注入与恢复
# --------------------------------------------------------------------------- #
def create_fault(
    db: Session, topology_id: int, payload: FaultEventCreate
) -> FaultEventRead:
    """对指定拓扑中的节点注入故障。

    校验：
    - 拓扑必须存在；
    - 节点必须存在且属于该拓扑；
    - 同一节点不允许存在同类型的**激活**故障（避免重复统计），
      但允许不同类型故障并存；已恢复的同类型故障不影响再次注入。
    """
    topology = _get_topology_or_404(db, topology_id)

    node = db.get(TopologyNode, payload.source_node_id)
    if node is None or node.topology_id != topology_id:
        raise NotFoundError(
            f"节点不存在于该拓扑：node_id={payload.source_node_id}"
        )

    duplicate = (
        db.query(FaultEvent)
        .filter(
            FaultEvent.topology_id == topology_id,
            FaultEvent.source_node_id == payload.source_node_id,
            FaultEvent.fault_type == payload.fault_type.value,
            FaultEvent.status == FaultStatus.ACTIVE.value,
        )
        .first()
    )
    if duplicate is not None:
        raise ConflictError(
            f"该节点已存在同类型的激活故障：fault_type={payload.fault_type.value}"
        )

    fault = FaultEvent(
        topology_id=topology_id,
        source_node_id=payload.source_node_id,
        fault_type=payload.fault_type.value,
        severity=payload.severity.value,
        description=payload.description,
        status=FaultStatus.ACTIVE.value,
    )
    db.add(fault)
    db.commit()
    db.refresh(fault)
    return _to_read(fault, node.name)


def recover_fault(db: Session, fault_id: int) -> FaultEventRead:
    """恢复故障，更新状态与 `recovered_at`，保留历史记录。"""
    fault = _get_fault_or_404(db, fault_id)
    if fault.status == FaultStatus.RECOVERED.value:
        raise ConflictError("该故障已处于恢复状态，无需重复恢复")

    fault.status = FaultStatus.RECOVERED.value
    fault.recovered_at = utcnow()
    db.commit()
    db.refresh(fault)
    names = _node_name_map(db, {fault.source_node_id})
    return _to_read(fault, names.get(fault.source_node_id))
