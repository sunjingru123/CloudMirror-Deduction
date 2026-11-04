"""故障传播分析服务（核心算法）。

依赖方向与传播方向
------------------

拓扑依赖边约定：`source_node_id = A` 依赖 `target_node_id = B`（记作 A → B）。

**故障传播方向与依赖方向相反**：当 B 发生故障时，A 可能受影响，
因此传播路径为 B → A。算法构建「反向邻接表」：

    对每条依赖边 (A → B)，令 dependents[B].append(A)

即「哪些节点依赖我」，从故障源出发沿 dependents 逐层扩散。

算法说明
--------

- 使用 **多源 BFS**（广度优先），所有边权重为 1，故首次被发现的节点
  即为其最短传播距离。
- **多故障源**：所有激活故障源作为距离 0 的根同时入队，按 `fault_id`
  升序、邻接按 `node_id` 升序处理，保证结果**确定、可复现**。
- **环路**：以「已发现集合」（`best`）做访问控制，节点只在首次发现时
  写入并再次入队，因此环路不会导致死循环，也不会重复统计。
- **去重**：受影响节点以 `node_id` 为键去重；同一节点被多个故障源触达时，
  保留距离最小者；距离相同则保留最先（按上述确定顺序）触达的故障源。
- **影响等级**：距离 1 为 `direct`（直接依赖故障源），距离 ≥ 2 为 `indirect`。
- 故障源节点本身不计入受影响节点。
- 无激活故障时返回空结果（不报错）。
- 不涉及随机数、外部模型；结果完全由「拓扑结构 + 故障记录」决定。
"""

from collections import deque

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.analysis import (
    AnalysisAffectedNode,
    AnalysisFaultSource,
    AnalysisPathStep,
    PropagationAnalysis,
)
from app.models.fault import FaultEvent
from app.models.topology import Topology, TopologyEdge, TopologyNode, utcnow
from app.schemas.analysis import (
    AffectedNodeRead,
    AnalysisHistoryItem,
    AnalysisHistoryPage,
    AnalysisResult,
    FaultSourceRead,
    ImpactLevel,
    PathStepRead,
    PropagationPathRead,
)
from app.schemas.fault import FaultSeverity, FaultStatus, FaultType
from app.services.exceptions import InvalidOperationError, NotFoundError


# --------------------------------------------------------------------------- #
# 内部数据结构
# --------------------------------------------------------------------------- #
class _NodeState:
    """BFS 过程中记录某节点的最短距离、来源故障与传播路径。"""

    __slots__ = ("distance", "fault_id", "source_node_id", "path")

    def __init__(
        self,
        distance: int,
        fault_id: int | None,
        source_node_id: int | None,
        path: list[int],
    ) -> None:
        self.distance = distance
        self.fault_id = fault_id
        self.source_node_id = source_node_id
        self.path = path


# --------------------------------------------------------------------------- #
# 数据加载与校验
# --------------------------------------------------------------------------- #
def _get_topology_or_404(db: Session, topology_id: int) -> Topology:
    topology = db.get(Topology, topology_id)
    if topology is None:
        raise NotFoundError(f"拓扑不存在：id={topology_id}")
    return topology


def _load_nodes(db: Session, topology_id: int) -> list[TopologyNode]:
    return (
        db.query(TopologyNode)
        .filter(TopologyNode.topology_id == topology_id)
        .order_by(TopologyNode.id)
        .all()
    )


def _load_edges(db: Session, topology_id: int) -> list[TopologyEdge]:
    return (
        db.query(TopologyEdge)
        .filter(TopologyEdge.topology_id == topology_id)
        .order_by(TopologyEdge.id)
        .all()
    )


def _resolve_fault_sources(
    db: Session, topology_id: int, fault_ids: list[int] | None
) -> list[FaultEvent]:
    """确定参与本次分析的故障源。

    - 未指定 `fault_ids`（或为空）：使用该拓扑全部激活故障；
    - 指定时：逐一校验存在性、所属拓扑、是否处于激活状态，任一不满足即报错，
      避免把「其他拓扑的故障」或「已恢复故障」计入传播。
    """
    if not fault_ids:
        return (
            db.query(FaultEvent)
            .filter(
                FaultEvent.topology_id == topology_id,
                FaultEvent.status == FaultStatus.ACTIVE.value,
            )
            .order_by(FaultEvent.id)
            .all()
        )

    unique_ids = list(dict.fromkeys(fault_ids))
    faults = db.query(FaultEvent).filter(FaultEvent.id.in_(unique_ids)).all()
    found = {fault.id: fault for fault in faults}

    resolved: list[FaultEvent] = []
    for fault_id in unique_ids:
        fault = found.get(fault_id)
        if fault is None:
            raise NotFoundError(f"故障事件不存在：id={fault_id}")
        if fault.topology_id != topology_id:
            raise NotFoundError(
                f"故障事件不属于该拓扑：fault_id={fault_id}, topology_id={topology_id}"
            )
        if fault.status != FaultStatus.ACTIVE.value:
            raise InvalidOperationError(
                f"故障事件不是激活状态，无法参与分析：fault_id={fault_id}"
            )
        resolved.append(fault)

    resolved.sort(key=lambda item: item.id)
    return resolved


# --------------------------------------------------------------------------- #
# 图构建与 BFS
# --------------------------------------------------------------------------- #
def _build_dependents(edges: list[TopologyEdge]) -> dict[int, list[int]]:
    """构建反向邻接表：dependents[B] = [A, ...]（A 依赖 B）。

    即「依赖 B 的节点」集合，用于从故障源 B 向依赖方扩散。
    """
    dependents: dict[int, list[int]] = {}
    for edge in edges:
        dependents.setdefault(edge.target_node_id, []).append(edge.source_node_id)
    for node_id in dependents:
        dependents[node_id] = sorted(set(dependents[node_id]))
    return dependents


def _bfs(
    dependents: dict[int, list[int]], roots: list[tuple[int, int]]
) -> dict[int, _NodeState]:
    """多源 BFS。

    `roots` 为 (source_node_id, fault_id) 序列，须已按 fault_id 升序排列。
    返回被触达节点（不含源节点自身）的状态字典。
    """
    best: dict[int, _NodeState] = {}
    queue: deque[int] = deque()

    for source_node_id, fault_id in roots:
        if source_node_id in best:
            # 同一节点存在多条激活故障：保留最先（fault_id 最小）的一条作为来源
            continue
        best[source_node_id] = _NodeState(
            distance=0, fault_id=fault_id, source_node_id=source_node_id, path=[source_node_id]
        )
        queue.append(source_node_id)

    while queue:
        current = queue.popleft()
        current_state = best[current]
        for dependent in dependents.get(current, []):
            if dependent in best:
                continue
            best[dependent] = _NodeState(
                distance=current_state.distance + 1,
                fault_id=current_state.fault_id,
                source_node_id=current_state.source_node_id,
                path=current_state.path + [dependent],
            )
            queue.append(dependent)

    return best


# --------------------------------------------------------------------------- #
# 分析执行
# --------------------------------------------------------------------------- #
def run_analysis(
    db: Session, topology_id: int, fault_ids: list[int] | None = None
) -> AnalysisResult:
    """执行一次故障传播分析，持久化结果并返回。"""
    _get_topology_or_404(db, topology_id)

    nodes = _load_nodes(db, topology_id)
    edges = _load_edges(db, topology_id)
    node_names = {node.id: node.name for node in nodes}

    faults = _resolve_fault_sources(db, topology_id, fault_ids)

    # 每个故障源节点保留 fault_id 最小的一条作为 BFS 来源
    roots: list[tuple[int, int]] = []
    seen_source_nodes: set[int] = set()
    for fault in faults:
        if fault.source_node_id in seen_source_nodes:
            continue
        seen_source_nodes.add(fault.source_node_id)
        roots.append((fault.source_node_id, fault.id))

    dependents = _build_dependents(edges)
    best = _bfs(dependents, roots)

    # 受影响节点 = 所有被触达且非故障源自身的节点
    affected_states = {
        node_id: state
        for node_id, state in best.items()
        if state.distance > 0 and node_id in node_names
    }

    # 排序：距离升序 → 节点 id 升序，保证输出稳定
    ordered = sorted(affected_states.items(), key=lambda item: (item[1].distance, item[0]))

    direct_count = sum(1 for _, state in ordered if state.distance == 1)
    indirect_count = len(ordered) - direct_count
    total_node_count = len(nodes)
    total_affected = len(ordered)
    impact_ratio = round(total_affected / total_node_count, 4) if total_node_count else 0.0

    analysis_time = utcnow()

    # ---- 持久化：汇总 ----
    record = PropagationAnalysis(
        topology_id=topology_id,
        fault_source_count=len(faults),
        direct_affected_count=direct_count,
        indirect_affected_count=indirect_count,
        total_affected_count=total_affected,
        total_node_count=total_node_count,
        impact_ratio=impact_ratio,
        analysis_time=analysis_time,
    )
    db.add(record)
    db.flush()  # 取得 analysis_id

    # ---- 持久化：故障源快照 ----
    for fault in faults:
        db.add(
            AnalysisFaultSource(
                analysis_id=record.id,
                fault_id=fault.id,
                node_id=fault.source_node_id,
                node_name=node_names.get(fault.source_node_id, ""),
                fault_type=fault.fault_type,
                severity=fault.severity,
            )
        )

    # ---- 持久化：受影响节点与传播路径 ----
    for node_id, state in ordered:
        is_direct = state.distance == 1
        affected = AnalysisAffectedNode(
            analysis_id=record.id,
            node_id=node_id,
            node_name=node_names.get(node_id, ""),
            impact_level=(ImpactLevel.DIRECT.value if is_direct else ImpactLevel.INDIRECT.value),
            distance=state.distance,
            source_fault_id=state.fault_id,
            source_node_id=state.source_node_id,
        )
        db.add(affected)
        db.flush()
        for index, step_node_id in enumerate(state.path):
            db.add(
                AnalysisPathStep(
                    affected_node_id=affected.id,
                    step_index=index,
                    node_id=step_node_id,
                    node_name=node_names.get(step_node_id, ""),
                )
            )

    db.commit()
    return _load_result(db, record.id)


# --------------------------------------------------------------------------- #
# 结果组装 / 读取
# --------------------------------------------------------------------------- #
def _load_result(db: Session, analysis_id: int) -> AnalysisResult:
    """从数据库重建分析结果对象。"""
    record = (
        db.query(PropagationAnalysis).filter(PropagationAnalysis.id == analysis_id).first()
    )
    if record is None:
        raise NotFoundError(f"分析结果不存在：id={analysis_id}")

    fault_sources = sorted(record.fault_sources, key=lambda item: (item.fault_id or 0, item.id))
    affected_nodes = sorted(
        record.affected_nodes, key=lambda item: (item.distance, item.node_id or 0, item.id)
    )

    source_reads = [
        FaultSourceRead(
            fault_id=item.fault_id,
            source_node_id=item.node_id,
            source_node_name=item.node_name,
            fault_type=FaultType(item.fault_type),
            severity=FaultSeverity(item.severity),
        )
        for item in fault_sources
    ]

    affected_reads: list[AffectedNodeRead] = []
    path_reads: list[PropagationPathRead] = []
    for item in affected_nodes:
        steps = sorted(item.path_steps, key=lambda step: (step.step_index, step.id))
        step_reads = [
            PathStepRead(node_id=step.node_id, node_name=step.node_name) for step in steps
        ]
        affected_reads.append(
            AffectedNodeRead(
                node_id=item.node_id,
                node_name=item.node_name,
                impact_level=ImpactLevel(item.impact_level),
                distance=item.distance,
                source_fault_id=item.source_fault_id,
                source_node_id=item.source_node_id,
                propagation_path=step_reads,
            )
        )
        path_reads.append(
            PropagationPathRead(
                source_fault_id=item.source_fault_id,
                source_node_id=item.source_node_id,
                target_node_id=item.node_id,
                target_node_name=item.node_name,
                distance=item.distance,
                steps=step_reads,
            )
        )

    return AnalysisResult(
        analysis_id=record.id,
        topology_id=record.topology_id,
        fault_sources=source_reads,
        affected_nodes=affected_reads,
        direct_affected_count=record.direct_affected_count,
        indirect_affected_count=record.indirect_affected_count,
        total_affected_count=record.total_affected_count,
        total_node_count=record.total_node_count,
        impact_ratio=record.impact_ratio,
        propagation_paths=path_reads,
        analysis_time=record.analysis_time,
    )


def get_latest_analysis(db: Session, topology_id: int) -> AnalysisResult:
    """读取指定拓扑最近一次的分析结果。"""
    _get_topology_or_404(db, topology_id)
    record = (
        db.query(PropagationAnalysis)
        .filter(PropagationAnalysis.topology_id == topology_id)
        .order_by(PropagationAnalysis.id.desc())
        .first()
    )
    if record is None:
        raise NotFoundError(f"该拓扑尚无分析记录：topology_id={topology_id}")
    return _load_result(db, record.id)


def get_analysis(db: Session, topology_id: int, analysis_id: int) -> AnalysisResult:
    """读取指定拓扑下某一次分析的完整结果。

    同时校验分析记录确实属于该拓扑，避免跨拓扑越权读取。
    """
    _get_topology_or_404(db, topology_id)
    record = db.get(PropagationAnalysis, analysis_id)
    if record is None:
        raise NotFoundError(f"分析结果不存在：analysis_id={analysis_id}")
    if record.topology_id != topology_id:
        raise NotFoundError(
            f"分析结果不属于该拓扑：analysis_id={analysis_id}, topology_id={topology_id}"
        )
    return _load_result(db, record.id)


def list_analyses(
    db: Session, topology_id: int, page: int = 1, page_size: int = 20
) -> AnalysisHistoryPage:
    """分页查询指定拓扑的历史分析记录（按时间倒序）。"""
    topology = _get_topology_or_404(db, topology_id)

    total = (
        db.query(func.count(PropagationAnalysis.id))
        .filter(PropagationAnalysis.topology_id == topology_id)
        .scalar()
        or 0
    )

    rows = (
        db.query(PropagationAnalysis)
        .filter(PropagationAnalysis.topology_id == topology_id)
        .order_by(PropagationAnalysis.analysis_time.desc(), PropagationAnalysis.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [
        AnalysisHistoryItem(
            analysis_id=row.id,
            topology_id=row.topology_id,
            topology_name=topology.name,
            analysis_time=row.analysis_time,
            fault_source_count=row.fault_source_count,
            direct_affected_count=row.direct_affected_count,
            indirect_affected_count=row.indirect_affected_count,
            total_affected_count=row.total_affected_count,
            total_node_count=row.total_node_count,
            impact_ratio=row.impact_ratio,
        )
        for row in rows
    ]

    return AnalysisHistoryPage(
        total=int(total), page=page, page_size=page_size, items=items
    )
