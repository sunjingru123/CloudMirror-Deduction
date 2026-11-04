"""恢复策略推荐服务。

输入
----

- 拓扑（节点与依赖边）
- 一次传播分析结果（含故障源快照、受影响节点）

输出
----

- 每种候选策略（重启 / 切换 / 隔离）的估算指标、适用性与不适用原因、风险等级
- 推荐策略与推荐理由

算法性质
--------

全部为**可解释的规则 + 配置参数**计算：

- 不使用随机数，不依赖时间 / 外部服务；
- 不使用机器学习或大模型；
- 相同输入必然得到相同输出（可复现）。

估算参数与评分权重集中定义在 `services/recovery_config.py`，
并在 `docs/技术方案.md` 中说明。

依赖方向约定
------------

边 `source_node_id = A`、`target_node_id = B` 表示 **A 依赖 B**。
因此「依赖 B 的节点」为边集合中 `target_node_id == B` 的 `source_node_id`。
"""

from sqlalchemy.orm import Session

from app.models.analysis import PropagationAnalysis
from app.models.recovery import RecoveryPlan, RecoveryStrategy, RecoveryStrategyNote
from app.models.topology import Topology, TopologyEdge, TopologyNode
from app.schemas.analysis import AnalysisResult
from app.schemas.recovery import (
    RecoveryRequest,
    RecoveryRecommendation,
    RecoveryStrategyRead,
    RecoveryStrategyType,
    ResourceCost,
    RiskLevel,
    ScoringWeights,
    StrategyConfigResponse,
    StrategyTypeInfo,
)
from app.services import propagation_service
from app.services import recovery_config as cfg
from app.services.exceptions import InvalidOperationError, NotFoundError

COST_LABELS: dict[str, str] = {
    ResourceCost.LOW.value: "低",
    ResourceCost.MEDIUM.value: "中",
    ResourceCost.HIGH.value: "高",
}
RISK_LABELS: dict[str, str] = {
    RiskLevel.LOW.value: "低",
    RiskLevel.MEDIUM.value: "中",
    RiskLevel.HIGH.value: "高",
}

# 用于「隔离会切断用户入口全部依赖」判断的节点类型
USER_ENTRY_NODE_TYPE = "user_entry"


# --------------------------------------------------------------------------- #
# 基础数据加载
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


def _build_dependency_map(edges: list[TopologyEdge]) -> dict[int, list[int]]:
    """source → [target]：某节点依赖哪些节点。"""
    result: dict[int, list[int]] = {}
    for edge in edges:
        result.setdefault(edge.source_node_id, []).append(edge.target_node_id)
    return {key: sorted(set(value)) for key, value in result.items()}


def _build_dependents_map(edges: list[TopologyEdge]) -> dict[int, list[int]]:
    """target → [source]：哪些节点依赖该节点（即故障传播方向）。"""
    result: dict[int, list[int]] = {}
    for edge in edges:
        result.setdefault(edge.target_node_id, []).append(edge.source_node_id)
    return {key: sorted(set(value)) for key, value in result.items()}


# --------------------------------------------------------------------------- #
# 分析结果解析
# --------------------------------------------------------------------------- #
def _resolve_analysis(
    db: Session, topology_id: int, analysis_id: int | None
) -> PropagationAnalysis:
    """定位要使用的分析记录，并校验其归属于当前拓扑。"""
    if analysis_id is None:
        latest = (
            db.query(PropagationAnalysis)
            .filter(PropagationAnalysis.topology_id == topology_id)
            .order_by(PropagationAnalysis.id.desc())
            .first()
        )
        if latest is None:
            raise NotFoundError(
                f"该拓扑尚无传播分析结果，无法生成恢复策略：topology_id={topology_id}"
            )
        return latest

    record = db.get(PropagationAnalysis, analysis_id)
    if record is None:
        raise NotFoundError(f"分析结果不存在：analysis_id={analysis_id}")
    if record.topology_id != topology_id:
        raise NotFoundError(
            f"分析结果不属于该拓扑：analysis_id={analysis_id}, topology_id={topology_id}"
        )
    return record


# --------------------------------------------------------------------------- #
# 评分
# --------------------------------------------------------------------------- #
def _score(
    recovery_time: float,
    affected_nodes: int,
    total_nodes: int,
    cost: str,
    risk: str,
    strategy_type: str,
) -> float:
    """规则加权评分（0-100）。

    每个分项均归一化到 [0, 1] 后按固定权重加权求和，再放大到 0-100。
    """
    time_score = 1.0 - min(recovery_time, cfg.REFERENCE_RECOVERY_SECONDS) / (
        cfg.REFERENCE_RECOVERY_SECONDS
    )
    if total_nodes > 0:
        impact_score = 1.0 - min(affected_nodes, total_nodes) / total_nodes
    else:
        impact_score = 1.0

    weighted = (
        cfg.RECOVERY_TIME_WEIGHT * time_score
        + cfg.IMPACT_WEIGHT * impact_score
        + cfg.COST_WEIGHT * cfg.COST_SCORE[cost]
        + cfg.RISK_WEIGHT * cfg.RISK_SCORE[risk]
        + cfg.BUSINESS_RECOVERY_WEIGHT * cfg.BUSINESS_RECOVERY[strategy_type]
    )
    return round(100.0 * weighted, 2)


def _make_strategy(
    strategy_type: str,
    *,
    applicable: bool,
    inapplicable_reason: str | None,
    recovery_time: float,
    affected_nodes: int,
    cost: str,
    risk: str,
    total_nodes: int,
) -> dict:
    config = cfg.STRATEGY_CONFIG[strategy_type]
    notes = cfg.STRATEGY_NOTES[strategy_type]
    return {
        "strategy_type": strategy_type,
        "strategy_name": config["strategy_name"],
        "description": config["description"],
        "applicable": applicable,
        "inapplicable_reason": inapplicable_reason,
        "estimated_recovery_time": round(recovery_time, 1),
        "estimated_affected_nodes": affected_nodes,
        "estimated_resource_cost": cost,
        "risk_level": risk,
        "recommendation_score": _score(
            recovery_time, affected_nodes, total_nodes, cost, risk, strategy_type
        ),
        "advantages": list(notes["advantages"]),
        "disadvantages": list(notes["disadvantages"]),
        "prerequisites": list(notes["prerequisites"]),
    }


# --------------------------------------------------------------------------- #
# 各策略的评估
# --------------------------------------------------------------------------- #
def _evaluate_restart(
    faulty_types: dict[int, set[str]], total_nodes: int
) -> dict:
    """服务重启：仅对进程级故障有意义。"""
    config = cfg.STRATEGY_CONFIG[RecoveryStrategyType.RESTART_SERVICE.value]
    candidates = [
        node_id
        for node_id, types in faulty_types.items()
        if types & cfg.RESTARTABLE_FAULT_TYPES
    ]
    applicable = len(candidates) > 0
    reason = None
    if not applicable:
        reason = "当前故障均为网络类故障（网络延迟 / 网络不可达），重启服务无法解决该问题"

    recovery_time = config["base_recovery_seconds"] + config["per_node_seconds"] * len(
        candidates
    )
    return _make_strategy(
        RecoveryStrategyType.RESTART_SERVICE.value,
        applicable=applicable,
        inapplicable_reason=reason,
        recovery_time=recovery_time,
        affected_nodes=len(candidates),
        cost=config["base_resource_cost"],
        risk=config["base_risk_level"],
        total_nodes=total_nodes,
    )


def _evaluate_failover(
    faulty_node_ids: list[int],
    nodes: list[TopologyNode],
    affected_node_ids: set[int],
    total_nodes: int,
) -> dict:
    """备用节点切换：必须逐个故障节点确认存在可用备用节点。"""
    config = cfg.STRATEGY_CONFIG[RecoveryStrategyType.FAILOVER.value]
    faulty_set = set(faulty_node_ids)
    nodes_by_id = {node.id: node for node in nodes}

    missing: list[str] = []
    for node_id in faulty_node_ids:
        node = nodes_by_id.get(node_id)
        if node is None:
            missing.append(f"节点(id={node_id})")
            continue
        standby_exists = any(
            other.id != node.id
            and other.type == node.type
            and other.id not in faulty_set
            and other.id not in affected_node_ids
            for other in nodes
        )
        if not standby_exists:
            missing.append(f"节点「{node.name}」")

    applicable = len(missing) == 0
    reason = None
    if not applicable:
        reason = (
            "缺少备用节点或冗余关系信息，无法执行切换："
            + "、".join(missing)
            + " 不存在可用的同类型备用节点"
        )

    recovery_time = config["base_recovery_seconds"] + config["per_node_seconds"] * len(
        faulty_node_ids
    )
    return _make_strategy(
        RecoveryStrategyType.FAILOVER.value,
        applicable=applicable,
        inapplicable_reason=reason,
        recovery_time=recovery_time,
        affected_nodes=len(faulty_node_ids),
        cost=config["base_resource_cost"],
        risk=config["base_risk_level"],
        total_nodes=total_nodes,
    )


def _evaluate_isolate(
    faulty_node_ids: list[int],
    nodes: list[TopologyNode],
    dependency_map: dict[int, list[int]],
    dependents_map: dict[int, list[int]],
    total_nodes: int,
) -> dict:
    """故障节点隔离：需检查是否会让用户入口彻底失去依赖。"""
    config = cfg.STRATEGY_CONFIG[RecoveryStrategyType.ISOLATE_NODE.value]
    faulty_set = set(faulty_node_ids)

    blocking: list[str] = []
    for node in nodes:
        if node.type != USER_ENTRY_NODE_TYPE:
            continue
        if node.id in faulty_set:
            blocking.append(f"用户入口「{node.name}」自身处于故障状态")
            continue
        dependencies = dependency_map.get(node.id, [])
        if dependencies and all(dep in faulty_set for dep in dependencies):
            blocking.append(f"隔离后用户入口「{node.name}」将失去全部可用依赖")

    if blocking:
        return _make_strategy(
            RecoveryStrategyType.ISOLATE_NODE.value,
            applicable=False,
            inapplicable_reason="隔离风险过高：" + "；".join(blocking),
            recovery_time=config["base_recovery_seconds"]
            + config["per_node_seconds"] * len(faulty_node_ids),
            affected_nodes=len(faulty_node_ids),
            cost=config["base_resource_cost"],
            risk=RiskLevel.HIGH.value,
            total_nodes=total_nodes,
        )

    directly_cut: set[int] = set()
    for node_id in faulty_node_ids:
        directly_cut.update(dependents_map.get(node_id, []))
    affected = faulty_set | directly_cut

    return _make_strategy(
        RecoveryStrategyType.ISOLATE_NODE.value,
        applicable=True,
        inapplicable_reason=None,
        recovery_time=config["base_recovery_seconds"]
        + config["per_node_seconds"] * len(faulty_node_ids),
        affected_nodes=len(affected),
        cost=config["base_resource_cost"],
        risk=RiskLevel.MEDIUM.value if directly_cut else RiskLevel.LOW.value,
        total_nodes=total_nodes,
    )


# --------------------------------------------------------------------------- #
# 策略配置查询
# --------------------------------------------------------------------------- #
def list_strategy_config(db: Session, topology_id: int) -> StrategyConfigResponse:
    """返回策略类型、估算参数与评分权重的说明。"""
    _get_topology_or_404(db, topology_id)

    strategy_types = [
        StrategyTypeInfo(
            strategy_type=RecoveryStrategyType(strategy_type),
            strategy_name=cfg.STRATEGY_CONFIG[strategy_type]["strategy_name"],
            description=cfg.STRATEGY_CONFIG[strategy_type]["description"],
            base_recovery_seconds=cfg.STRATEGY_CONFIG[strategy_type]["base_recovery_seconds"],
            per_node_seconds=cfg.STRATEGY_CONFIG[strategy_type]["per_node_seconds"],
            base_resource_cost=ResourceCost(
                cfg.STRATEGY_CONFIG[strategy_type]["base_resource_cost"]
            ),
            base_risk_level=RiskLevel(cfg.STRATEGY_CONFIG[strategy_type]["base_risk_level"]),
            prerequisites=list(cfg.STRATEGY_CONFIG[strategy_type]["prerequisites"]),
            notes=list(cfg.STRATEGY_CONFIG[strategy_type]["notes"]),
        )
        for strategy_type in cfg.STRATEGY_ORDER
    ]

    return StrategyConfigResponse(
        topology_id=topology_id,
        strategy_types=strategy_types,
        scoring_weights=ScoringWeights(
            recovery_time=cfg.RECOVERY_TIME_WEIGHT,
            impact=cfg.IMPACT_WEIGHT,
            cost=cfg.COST_WEIGHT,
            risk=cfg.RISK_WEIGHT,
            business_recovery=cfg.BUSINESS_RECOVERY_WEIGHT,
        ),
        reference_recovery_seconds=cfg.REFERENCE_RECOVERY_SECONDS,
        estimation_notice=cfg.ESTIMATION_NOTICE,
    )


# --------------------------------------------------------------------------- #
# 推荐
# --------------------------------------------------------------------------- #
def _build_recommendation_reason(
    strategies: list[dict], recommended: dict | None
) -> str:
    if recommended is None:
        details = "；".join(
            f"{item['strategy_name']}（{item['inapplicable_reason']}）"
            for item in strategies
        )
        return f"当前没有可安全执行的恢复策略：{details}"

    return (
        f"推荐「{recommended['strategy_name']}」：在适用策略中综合评分最高"
        f"（{recommended['recommendation_score']} 分），"
        f"预计恢复时间 {recommended['estimated_recovery_time']} 秒，"
        f"影响节点 {recommended['estimated_affected_nodes']} 个，"
        f"资源成本{COST_LABELS[recommended['estimated_resource_cost']]}，"
        f"风险{RISK_LABELS[recommended['risk_level']]}。"
    )


def _persist(
    db: Session,
    topology_id: int,
    analysis_id: int,
    strategies: list[dict],
    recommended: dict | None,
    reason: str,
) -> tuple[RecoveryPlan, dict[str, RecoveryStrategy]]:
    plan = RecoveryPlan(
        topology_id=topology_id,
        analysis_id=analysis_id,
        recommendation_reason=reason,
        estimation_notice=cfg.ESTIMATION_NOTICE,
    )
    db.add(plan)
    db.flush()

    rows: dict[str, RecoveryStrategy] = {}
    for item in strategies:
        row = RecoveryStrategy(
            plan_id=plan.id,
            strategy_type=item["strategy_type"],
            strategy_name=item["strategy_name"],
            description=item["description"],
            applicable=item["applicable"],
            inapplicable_reason=item["inapplicable_reason"],
            estimated_recovery_time=item["estimated_recovery_time"],
            estimated_affected_nodes=item["estimated_affected_nodes"],
            estimated_resource_cost=item["estimated_resource_cost"],
            risk_level=item["risk_level"],
            recommendation_score=item["recommendation_score"],
        )
        db.add(row)
        db.flush()
        rows[item["strategy_type"]] = row

        for kind, contents in (
            ("advantage", item["advantages"]),
            ("disadvantage", item["disadvantages"]),
            ("prerequisite", item["prerequisites"]),
        ):
            for position, content in enumerate(contents):
                db.add(
                    RecoveryStrategyNote(
                        strategy_id=row.id,
                        kind=kind,
                        position=position,
                        content=content,
                    )
                )

    if recommended is not None:
        plan.recommended_strategy_id = rows[recommended["strategy_type"]].id

    db.commit()
    db.refresh(plan)
    return plan, rows


def recommend(
    db: Session, topology_id: int, payload: RecoveryRequest | None = None
) -> RecoveryRecommendation:
    """针对一次传播分析结果生成恢复策略并给出推荐。"""
    _get_topology_or_404(db, topology_id)

    requested_id = payload.analysis_id if payload is not None else None
    record = _resolve_analysis(db, topology_id, requested_id)
    analysis: AnalysisResult = propagation_service.get_analysis(db, topology_id, record.id)

    if not analysis.fault_sources:
        raise InvalidOperationError(
            f"该分析没有激活故障源，无法生成恢复策略：analysis_id={record.id}"
        )

    nodes = _load_nodes(db, topology_id)
    edges = _load_edges(db, topology_id)
    total_nodes = len(nodes)

    faulty_types: dict[int, set[str]] = {}
    for source in analysis.fault_sources:
        if source.source_node_id is None:
            continue
        faulty_types.setdefault(source.source_node_id, set()).add(source.fault_type.value)
    faulty_node_ids = sorted(faulty_types)

    affected_node_ids = {
        item.node_id for item in analysis.affected_nodes if item.node_id is not None
    }

    dependency_map = _build_dependency_map(edges)
    dependents_map = _build_dependents_map(edges)

    strategies = [
        _evaluate_restart(faulty_types, total_nodes),
        _evaluate_failover(faulty_node_ids, nodes, affected_node_ids, total_nodes),
        _evaluate_isolate(
            faulty_node_ids, nodes, dependency_map, dependents_map, total_nodes
        ),
    ]

    applicable = [item for item in strategies if item["applicable"]]
    recommended: dict | None = None
    if applicable:
        order_index = {value: index for index, value in enumerate(cfg.STRATEGY_ORDER)}
        recommended = max(
            applicable,
            key=lambda item: (
                item["recommendation_score"],
                -order_index[item["strategy_type"]],
            ),
        )

    reason = _build_recommendation_reason(strategies, recommended)
    plan, rows = _persist(db, topology_id, record.id, strategies, recommended, reason)

    strategy_reads = [
        RecoveryStrategyRead(
            strategy_id=rows[item["strategy_type"]].id,
            strategy_type=RecoveryStrategyType(item["strategy_type"]),
            strategy_name=item["strategy_name"],
            description=item["description"],
            applicable=item["applicable"],
            inapplicable_reason=item["inapplicable_reason"],
            estimated_recovery_time=item["estimated_recovery_time"],
            estimated_affected_nodes=item["estimated_affected_nodes"],
            estimated_resource_cost=ResourceCost(item["estimated_resource_cost"]),
            risk_level=RiskLevel(item["risk_level"]),
            advantages=item["advantages"],
            disadvantages=item["disadvantages"],
            prerequisites=item["prerequisites"],
            recommendation_score=item["recommendation_score"],
        )
        for item in strategies
    ]

    return RecoveryRecommendation(
        plan_id=plan.id,
        analysis_id=record.id,
        topology_id=topology_id,
        strategies=strategy_reads,
        recommended_strategy_id=plan.recommended_strategy_id,
        recommended_strategy_type=(
            RecoveryStrategyType(recommended["strategy_type"]) if recommended else None
        ),
        recommendation_reason=reason,
        estimation_notice=cfg.ESTIMATION_NOTICE,
        created_at=plan.created_at,
    )
