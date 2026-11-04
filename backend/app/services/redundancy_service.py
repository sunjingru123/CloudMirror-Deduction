"""冗余关系业务服务层。

负责冗余组与成员的增删改查、结构校验，以及为恢复策略（`failover`）提供
「显式主备关系」查询。所有校验失败都会抛出 `app.services.exceptions` 中定义的
业务异常，并在消息中说明具体原因。

关键约定
--------

- 冗余组只能引用**本拓扑**节点；跨拓扑引用返回 404。
- 同一节点不能在同一冗余组中重复出现（409）。
- 主备 / 手动备用模式：必须有且只有一个 `primary`，至少一个 `standby`，
  且每个 `standby` 必须明确指定 `priority`（数值越小优先级越高）。
- 双活模式：至少两个 `active` 成员。
- **当前版本限制**：同一拓扑内一个节点最多只能加入一个冗余组，跨组复用返回 409。

删除节点时，`cleanup_node_references` 会清理该节点的成员行，并删除因此不再满足
模式约束的冗余组（例如主备组的主节点被删除）。
"""

from dataclasses import dataclass
from typing import Iterable, Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.redundancy import RedundancyGroup, RedundancyMember
from app.models.topology import Topology, TopologyNode
from app.schemas.redundancy import (
    MemberRole,
    RedundancyGroupCreate,
    RedundancyGroupRead,
    RedundancyGroupUpdate,
    RedundancyMemberRead,
    RedundancyType,
)
from app.services.exceptions import ConflictError, InvalidOperationError, NotFoundError

ACTIVE = MemberRole.ACTIVE.value
PRIMARY = MemberRole.PRIMARY.value
STANDBY = MemberRole.STANDBY.value

# 展示顺序：主节点 → 备用节点 → 双活成员
_ROLE_ORDER = {PRIMARY: 0, STANDBY: 1, ACTIVE: 2}


# --------------------------------------------------------------------------- #
# 恢复策略使用的只读结构
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RedundancyMemberInfo:
    """供恢复策略使用的成员快照。"""

    node_id: int
    node_name: str
    node_type: str
    node_status: str
    member_role: str
    priority: int | None


@dataclass(frozen=True)
class RedundancyGroupInfo:
    """供恢复策略使用的冗余组快照。"""

    group_id: int
    group_name: str
    redundancy_type: str
    members: tuple[RedundancyMemberInfo, ...]

    def by_role(self, role: str) -> list[RedundancyMemberInfo]:
        return [member for member in self.members if member.member_role == role]


# --------------------------------------------------------------------------- #
# 内部辅助
# --------------------------------------------------------------------------- #
def _get_topology_or_404(db: Session, topology_id: int) -> Topology:
    topology = db.get(Topology, topology_id)
    if topology is None:
        raise NotFoundError(f"拓扑不存在：id={topology_id}")
    return topology


def _get_group_or_404(db: Session, group_id: int) -> RedundancyGroup:
    group = db.get(RedundancyGroup, group_id)
    if group is None:
        raise NotFoundError(f"冗余组不存在：id={group_id}")
    return group


def _node_name_map(db: Session, node_ids: set[int]) -> dict[int, str]:
    if not node_ids:
        return {}
    rows = (
        db.query(TopologyNode.id, TopologyNode.name)
        .filter(TopologyNode.id.in_(node_ids))
        .all()
    )
    return {int(node_id): name for node_id, name in rows}


def _member_rows(db: Session, group_id: int) -> list[RedundancyMember]:
    return (
        db.query(RedundancyMember)
        .filter(RedundancyMember.redundancy_group_id == group_id)
        .order_by(RedundancyMember.id)
        .all()
    )


def _sort_members(rows: Sequence[RedundancyMember]) -> list[RedundancyMember]:
    return sorted(
        rows,
        key=lambda row: (
            _ROLE_ORDER.get(row.member_role, 9),
            row.priority if row.priority is not None else 0,
            row.id,
        ),
    )


def _to_read(db: Session, group: RedundancyGroup) -> RedundancyGroupRead:
    rows = _sort_members(_member_rows(db, group.id))
    names = _node_name_map(db, {row.node_id for row in rows})
    return RedundancyGroupRead(
        id=group.id,
        topology_id=group.topology_id,
        name=group.name,
        redundancy_type=RedundancyType(group.redundancy_type),
        description=group.description,
        members=[
            RedundancyMemberRead(
                id=row.id,
                redundancy_group_id=row.redundancy_group_id,
                node_id=row.node_id,
                node_name=names.get(row.node_id, f"节点#{row.node_id}"),
                member_role=MemberRole(row.member_role),
                priority=row.priority,
                created_at=row.created_at,
            )
            for row in rows
        ],
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


# --------------------------------------------------------------------------- #
# 结构校验
# --------------------------------------------------------------------------- #
def _invariant_error(
    redundancy_type: str, members: Iterable[tuple[str, int | None]]
) -> str | None:
    """检查成员结构是否满足冗余模式的约束，返回错误信息（合法时为 None）。"""
    rows = list(members)
    if not rows:
        return "冗余组至少需要一个成员"

    roles = [role for role, _ in rows]

    if redundancy_type == RedundancyType.ACTIVE_ACTIVE.value:
        if any(role != ACTIVE for role in roles):
            return "双活模式的成员角色必须全部为 active"
        if roles.count(ACTIVE) < 2:
            return "双活模式至少需要两个 active 成员"
        return None

    # 主备 / 手动备用：一个主节点 + 至少一个带优先级的备用节点
    if any(role == ACTIVE for role in roles):
        return "主备模式不允许 active 角色成员（active 仅用于双活模式）"
    if roles.count(PRIMARY) != 1:
        return "主备模式必须且只能有一个主节点（primary）"
    standbys = [priority for role, priority in rows if role == STANDBY]
    if not standbys:
        return "主备模式至少需要一个备用节点（standby）"
    if any(priority is None for priority in standbys):
        return "主备模式下备用节点必须明确指定优先级 priority"
    return None


def _validate_nodes(
    db: Session,
    topology_id: int,
    node_ids: list[int],
    *,
    exclude_group_id: int | None = None,
) -> None:
    """校验节点属于本拓扑，且当前未加入其他冗余组。"""
    if len(set(node_ids)) != len(node_ids):
        raise ConflictError("同一节点不能在同一冗余组中重复出现")

    nodes = db.query(TopologyNode).filter(TopologyNode.id.in_(node_ids)).all()
    found = {node.id: node for node in nodes}
    for node_id in node_ids:
        node = found.get(node_id)
        if node is None or node.topology_id != topology_id:
            raise NotFoundError(f"节点不存在于该拓扑：node_id={node_id}")

    query = (
        db.query(RedundancyMember.node_id)
        .join(RedundancyGroup, RedundancyGroup.id == RedundancyMember.redundancy_group_id)
        .filter(
            RedundancyGroup.topology_id == topology_id,
            RedundancyMember.node_id.in_(node_ids),
        )
    )
    if exclude_group_id is not None:
        query = query.filter(RedundancyGroup.id != exclude_group_id)
    conflict = query.first()
    if conflict is not None:
        raise ConflictError(
            f"节点已加入该拓扑中的其他冗余组（当前版本一个节点最多属于一个冗余组）："
            f"node_id={conflict[0]}"
        )


def _validated_pairs(
    db: Session,
    topology_id: int,
    redundancy_type: str,
    members: Sequence,
    *,
    exclude_group_id: int | None = None,
) -> list[tuple[object, str, int | None]]:
    """统一校验成员并返回 (node_id, role, priority) 列表。"""
    node_ids = [int(member.node_id) for member in members]
    _validate_nodes(db, topology_id, node_ids, exclude_group_id=exclude_group_id)

    pairs = [
        (int(member.node_id), member.member_role.value, member.priority)
        for member in members
    ]
    error = _invariant_error(redundancy_type, [(role, priority) for _, role, priority in pairs])
    if error is not None:
        raise InvalidOperationError(error)
    return pairs


# --------------------------------------------------------------------------- #
# 查询
# --------------------------------------------------------------------------- #
def list_groups(db: Session, topology_id: int) -> list[RedundancyGroupRead]:
    """返回指定拓扑的全部冗余组（含成员）。"""
    _get_topology_or_404(db, topology_id)
    groups = (
        db.query(RedundancyGroup)
        .filter(RedundancyGroup.topology_id == topology_id)
        .order_by(RedundancyGroup.id)
        .all()
    )
    return [_to_read(db, group) for group in groups]


def get_group(db: Session, group_id: int) -> RedundancyGroupRead:
    """获取冗余组详情。"""
    return _to_read(db, _get_group_or_404(db, group_id))


# --------------------------------------------------------------------------- #
# 写入
# --------------------------------------------------------------------------- #
def create_group(
    db: Session, topology_id: int, payload: RedundancyGroupCreate
) -> RedundancyGroupRead:
    """创建冗余组：一次请求内提交完整的主备结构。"""
    topology = _get_topology_or_404(db, topology_id)
    redundancy_type = payload.redundancy_type.value
    pairs = _validated_pairs(db, topology.id, redundancy_type, payload.members)

    group = RedundancyGroup(
        topology_id=topology.id,
        name=payload.name,
        redundancy_type=redundancy_type,
        description=payload.description,
    )
    db.add(group)
    try:
        db.flush()
        for node_id, role, priority in pairs:
            db.add(
                RedundancyMember(
                    redundancy_group_id=group.id,
                    node_id=node_id,
                    member_role=role,
                    priority=priority,
                )
            )
        db.commit()
    except IntegrityError as exc:  # 数据库层约束兜底
        db.rollback()
        raise ConflictError("冗余组创建失败：成员重复或节点非法") from exc

    db.refresh(group)
    return _to_read(db, group)


def update_group(
    db: Session, group_id: int, payload: RedundancyGroupUpdate
) -> RedundancyGroupRead:
    """更新冗余组基本信息，并可选地整体替换成员列表。"""
    group = _get_group_or_404(db, group_id)
    provided = payload.model_fields_set

    redundancy_type = (
        payload.redundancy_type.value
        if payload.redundancy_type is not None
        else group.redundancy_type
    )

    if "members" in provided and payload.members is not None:
        pairs = _validated_pairs(
            db,
            group.topology_id,
            redundancy_type,
            payload.members,
            exclude_group_id=group.id,
        )
    else:
        # 未提供成员时，沿用现有成员，但仍需保证新模式与现有结构相容
        existing = _member_rows(db, group.id)
        error = _invariant_error(
            redundancy_type, [(row.member_role, row.priority) for row in existing]
        )
        if error is not None:
            raise InvalidOperationError(
                f"当前成员结构与新的冗余模式不兼容：{error}"
            )
        pairs = None

    if payload.name is not None:
        group.name = payload.name
    if "description" in provided:
        group.description = payload.description
    group.redundancy_type = redundancy_type

    try:
        if pairs is not None:
            db.query(RedundancyMember).filter(
                RedundancyMember.redundancy_group_id == group.id
            ).delete(synchronize_session=False)
            db.flush()
            for node_id, role, priority in pairs:
                db.add(
                    RedundancyMember(
                        redundancy_group_id=group.id,
                        node_id=node_id,
                        member_role=role,
                        priority=priority,
                    )
                )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("冗余组更新失败：成员重复或节点非法") from exc

    db.refresh(group)
    return _to_read(db, group)


def delete_group(db: Session, group_id: int) -> None:
    """删除冗余组及其成员。"""
    group = _get_group_or_404(db, group_id)
    db.query(RedundancyMember).filter(
        RedundancyMember.redundancy_group_id == group.id
    ).delete(synchronize_session=False)
    db.delete(group)
    db.commit()


# --------------------------------------------------------------------------- #
# 节点删除时的引用清理
# --------------------------------------------------------------------------- #
def cleanup_node_references(db: Session, topology_id: int, node_id: int) -> list[str]:
    """删除某节点的冗余成员行，并清理因此失效的冗余组。

    返回被一并删除的冗余组名称列表（供调用方记录日志）。

    规则：
    - 删除该节点在所有冗余组中的成员行；
    - 若某个冗余组因此不再满足其模式的成员约束（如主备组失去主节点），
      则整个冗余组一并删除，避免留下语义不完整的冗余关系。

    本函数只 flush，不提交事务，由调用方统一提交。
    """
    groups = (
        db.query(RedundancyGroup)
        .join(RedundancyMember, RedundancyMember.redundancy_group_id == RedundancyGroup.id)
        .filter(
            RedundancyGroup.topology_id == topology_id,
            RedundancyMember.node_id == node_id,
        )
        .all()
    )

    removed_groups: list[str] = []
    for group in groups:
        db.query(RedundancyMember).filter(
            RedundancyMember.redundancy_group_id == group.id,
            RedundancyMember.node_id == node_id,
        ).delete(synchronize_session=False)
        db.flush()

        remaining = _member_rows(db, group.id)
        error = _invariant_error(
            group.redundancy_type, [(row.member_role, row.priority) for row in remaining]
        )
        if error is not None:
            db.query(RedundancyMember).filter(
                RedundancyMember.redundancy_group_id == group.id
            ).delete(synchronize_session=False)
            db.delete(group)
            removed_groups.append(group.name)

    return removed_groups


# --------------------------------------------------------------------------- #
# 供恢复策略使用
# --------------------------------------------------------------------------- #
def load_groups_for_recovery(
    db: Session, topology_id: int
) -> dict[int, RedundancyGroupInfo]:
    """返回 `node_id -> RedundancyGroupInfo` 映射。

    由于当前限制「一个节点最多属于一个冗余组」，映射中每个节点只会对应一个组。
    """
    groups = (
        db.query(RedundancyGroup)
        .filter(RedundancyGroup.topology_id == topology_id)
        .order_by(RedundancyGroup.id)
        .all()
    )
    if not groups:
        return {}

    group_ids = [group.id for group in groups]
    rows = (
        db.query(RedundancyMember, TopologyNode)
        .join(TopologyNode, TopologyNode.id == RedundancyMember.node_id)
        .filter(RedundancyMember.redundancy_group_id.in_(group_ids))
        .order_by(RedundancyMember.id)
        .all()
    )

    members_by_group: dict[int, list[RedundancyMemberInfo]] = {}
    for member, node in rows:
        members_by_group.setdefault(member.redundancy_group_id, []).append(
            RedundancyMemberInfo(
                node_id=member.node_id,
                node_name=node.name,
                node_type=node.type,
                node_status=node.status,
                member_role=member.member_role,
                priority=member.priority,
            )
        )

    mapping: dict[int, RedundancyGroupInfo] = {}
    for group in groups:
        info = RedundancyGroupInfo(
            group_id=group.id,
            group_name=group.name,
            redundancy_type=group.redundancy_type,
            members=tuple(members_by_group.get(group.id, [])),
        )
        for member in info.members:
            mapping[member.node_id] = info
    return mapping
