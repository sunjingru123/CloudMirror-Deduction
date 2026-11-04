"""恢复策略推荐测试。

覆盖：

1. 正常进程级故障可以生成「服务重启」策略并被推荐
2. 缺少备用节点时「备用节点切换」不适用（并给出原因）
3. 存在明确同类型备用节点时才考虑切换策略
4. 高风险隔离策略（用户入口失去全部依赖）不能被推荐
5. 策略评分可复现（相同输入 → 相同输出）
6. 不适用策略不能被选为推荐策略
7. 错误 / 跨拓扑 analysis_id 返回明确错误
8. 无分析记录、无激活故障源时返回明确错误
9. 策略配置接口返回权重与估算参数
"""

from fastapi.testclient import TestClient

BASE = "/api/topologies"


# --------------------------------------------------------------------------- #
# 辅助函数
# --------------------------------------------------------------------------- #
def _topology(client: TestClient, name: str) -> int:
    response = client.post(BASE, json={"name": name})
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _node(
    client: TestClient, topology_id: int, label: str, node_type: str = "app_server"
) -> int:
    response = client.post(
        f"{BASE}/{topology_id}/nodes", json={"name": label, "type": node_type}
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _edge(client: TestClient, topology_id: int, source: int, target: int) -> None:
    """source 依赖 target（source → target）。"""
    response = client.post(
        f"{BASE}/{topology_id}/edges",
        json={"source_node_id": source, "target_node_id": target},
    )
    assert response.status_code == 201, response.text


def _fault(
    client: TestClient, topology_id: int, node_id: int, fault_type: str = "node_down"
) -> int:
    response = client.post(
        f"{BASE}/{topology_id}/faults",
        json={"source_node_id": node_id, "fault_type": fault_type, "severity": "high"},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _analyze(client: TestClient, topology_id: int) -> dict:
    response = client.post(f"{BASE}/{topology_id}/analyze", json={})
    assert response.status_code == 200, response.text
    return response.json()


def _recommend(
    client: TestClient, topology_id: int, analysis_id: int | None = None
) -> dict:
    payload = {} if analysis_id is None else {"analysis_id": analysis_id}
    response = client.post(f"{BASE}/{topology_id}/recovery/recommend", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _by_type(result: dict) -> dict[str, dict]:
    return {item["strategy_type"]: item for item in result["strategies"]}


def _chain(client: TestClient, name: str = "链式拓扑") -> tuple[int, dict[str, int]]:
    """入口 → 负载均衡 → 应用 → 数据库（source 依赖 target）。"""
    topology_id = _topology(client, name)
    entry = _node(client, topology_id, "用户入口", "user_entry")
    balancer = _node(client, topology_id, "负载均衡器", "load_balancer")
    app = _node(client, topology_id, "应用服务器", "app_server")
    database = _node(client, topology_id, "数据库", "database")
    _edge(client, topology_id, entry, balancer)
    _edge(client, topology_id, balancer, app)
    _edge(client, topology_id, app, database)
    return topology_id, {
        "entry": entry,
        "balancer": balancer,
        "app": app,
        "database": database,
    }


# --------------------------------------------------------------------------- #
# 1. 重启策略
# --------------------------------------------------------------------------- #
def test_restart_strategy_available_and_recommended(client: TestClient) -> None:
    topology_id, ids = _chain(client)
    _fault(client, topology_id, ids["database"], "node_down")
    analysis = _analyze(client, topology_id)

    result = _recommend(client, topology_id, analysis["analysis_id"])
    strategies = _by_type(result)

    restart = strategies["restart_service"]
    assert restart["applicable"] is True
    assert restart["inapplicable_reason"] is None
    assert restart["estimated_recovery_time"] > 0
    assert restart["estimated_affected_nodes"] == 1
    assert restart["estimated_resource_cost"] == "low"

    # 单库且无备用节点，切换不适用；隔离会切断应用依赖但不至于高风险
    assert strategies["failover"]["applicable"] is False
    assert strategies["isolate_node"]["applicable"] is True

    assert result["recommended_strategy_type"] == "restart_service"
    assert result["recommended_strategy_id"] == restart["strategy_id"]
    assert "服务重启" in result["recommendation_reason"]
    assert "模拟估算值" in result["estimation_notice"]


def test_restart_inapplicable_for_network_faults(client: TestClient) -> None:
    topology_id, ids = _chain(client, "网络故障拓扑")
    _fault(client, topology_id, ids["database"], "network_latency")
    analysis = _analyze(client, topology_id)

    result = _recommend(client, topology_id, analysis["analysis_id"])
    restart = _by_type(result)["restart_service"]

    assert restart["applicable"] is False
    assert restart["inapplicable_reason"] is not None
    assert "网络" in restart["inapplicable_reason"]
    assert result["recommended_strategy_type"] != "restart_service"


# --------------------------------------------------------------------------- #
# 2. 缺少 / 存在备用节点
# --------------------------------------------------------------------------- #
def test_failover_inapplicable_without_standby(client: TestClient) -> None:
    topology_id, ids = _chain(client, "无备用节点拓扑")
    _fault(client, topology_id, ids["database"], "node_down")
    analysis = _analyze(client, topology_id)

    result = _recommend(client, topology_id, analysis["analysis_id"])
    failover = _by_type(result)["failover"]

    assert failover["applicable"] is False
    assert failover["inapplicable_reason"] is not None
    assert "缺少备用节点" in failover["inapplicable_reason"]
    assert result["recommended_strategy_type"] != "failover"


def test_failover_applicable_with_standby(client: TestClient) -> None:
    topology_id = _topology(client, "双数据库拓扑")
    entry = _node(client, topology_id, "用户入口", "user_entry")
    app = _node(client, topology_id, "应用服务器", "app_server")
    db_primary = _node(client, topology_id, "主数据库", "database")
    db_standby = _node(client, topology_id, "备数据库", "database")
    _edge(client, topology_id, entry, app)
    _edge(client, topology_id, app, db_primary)
    _edge(client, topology_id, app, db_standby)

    _fault(client, topology_id, db_primary, "node_down")
    analysis = _analyze(client, topology_id)

    result = _recommend(client, topology_id, analysis["analysis_id"])
    failover = _by_type(result)["failover"]

    assert failover["applicable"] is True
    assert failover["inapplicable_reason"] is None
    assert failover["estimated_resource_cost"] == "high"
    assert failover["risk_level"] == "low"
    # 备用节点存在时，切换的业务恢复度更高，应被推荐
    assert result["recommended_strategy_type"] == "failover"


# --------------------------------------------------------------------------- #
# 3. 高风险隔离
# --------------------------------------------------------------------------- #
def test_high_risk_isolation_never_recommended(client: TestClient) -> None:
    topology_id = _topology(client, "单依赖入口拓扑")
    entry = _node(client, topology_id, "用户入口", "user_entry")
    database = _node(client, topology_id, "数据库", "database")
    _edge(client, topology_id, entry, database)  # 入口只依赖这一个数据库

    _fault(client, topology_id, database, "node_down")
    analysis = _analyze(client, topology_id)

    result = _recommend(client, topology_id, analysis["analysis_id"])
    isolate = _by_type(result)["isolate_node"]

    assert isolate["applicable"] is False
    assert isolate["risk_level"] == "high"
    assert isolate["inapplicable_reason"] is not None
    assert "失去全部可用依赖" in isolate["inapplicable_reason"]
    assert result["recommended_strategy_type"] != "isolate_node"
    assert result["recommended_strategy_id"] != isolate["strategy_id"]


def test_isolate_applicable_when_entry_keeps_dependency(client: TestClient) -> None:
    topology_id, ids = _chain(client, "多依赖入口拓扑")
    _fault(client, topology_id, ids["database"], "node_down")
    analysis = _analyze(client, topology_id)

    result = _recommend(client, topology_id, analysis["analysis_id"])
    isolate = _by_type(result)["isolate_node"]

    assert isolate["applicable"] is True
    assert isolate["risk_level"] in {"low", "medium"}
    # 隔离会切断直接依赖方（应用服务器）的服务，影响节点数至少为故障源 + 1
    assert isolate["estimated_affected_nodes"] >= 2


# --------------------------------------------------------------------------- #
# 4. 评分可复现、不适用策略不被推荐
# --------------------------------------------------------------------------- #
def test_scores_are_reproducible(client: TestClient) -> None:
    topology_id, ids = _chain(client, "可复现拓扑")
    _fault(client, topology_id, ids["app"], "service_unavailable")
    analysis = _analyze(client, topology_id)
    analysis_id = analysis["analysis_id"]

    first = _recommend(client, topology_id, analysis_id)
    second = _recommend(client, topology_id, analysis_id)

    def signature(payload: dict) -> list[tuple[str, float, float, int, str, str]]:
        return [
            (
                item["strategy_type"],
                item["recommendation_score"],
                item["estimated_recovery_time"],
                item["estimated_affected_nodes"],
                item["estimated_resource_cost"],
                item["risk_level"],
            )
            for item in payload["strategies"]
        ]

    assert signature(first) == signature(second)
    assert first["recommended_strategy_type"] == second["recommended_strategy_type"]
    # 两次推荐生成不同的计划记录，但评估结果一致
    assert first["plan_id"] != second["plan_id"]


def test_inapplicable_strategy_never_selected(client: TestClient) -> None:
    topology_id, ids = _chain(client, "适用性校验拓扑")
    _fault(client, topology_id, ids["database"], "network_unreachable")
    analysis = _analyze(client, topology_id)

    result = _recommend(client, topology_id, analysis["analysis_id"])

    recommended_id = result["recommended_strategy_id"]
    assert recommended_id is not None
    chosen = next(
        item for item in result["strategies"] if item["strategy_id"] == recommended_id
    )
    assert chosen["applicable"] is True
    for item in result["strategies"]:
        if not item["applicable"]:
            assert item["strategy_id"] != recommended_id


# --------------------------------------------------------------------------- #
# 5. 错误场景
# --------------------------------------------------------------------------- #
def test_unknown_analysis_id_rejected(client: TestClient) -> None:
    topology_id, ids = _chain(client, "未知分析拓扑")
    _fault(client, topology_id, ids["database"], "node_down")
    _analyze(client, topology_id)

    response = client.post(
        f"{BASE}/{topology_id}/recovery/recommend", json={"analysis_id": 999999}
    )
    assert response.status_code == 404
    assert "分析结果不存在" in response.json()["detail"]


def test_cross_topology_analysis_id_rejected(client: TestClient) -> None:
    topology_a, ids_a = _chain(client, "拓扑A")
    _fault(client, topology_a, ids_a["database"], "node_down")
    analysis_a = _analyze(client, topology_a)

    topology_b, ids_b = _chain(client, "拓扑B")
    _fault(client, topology_b, ids_b["database"], "node_down")
    _analyze(client, topology_b)

    response = client.post(
        f"{BASE}/{topology_b}/recovery/recommend",
        json={"analysis_id": analysis_a["analysis_id"]},
    )
    assert response.status_code == 404
    assert "不属于该拓扑" in response.json()["detail"]


def test_recommend_without_analysis_rejected(client: TestClient) -> None:
    topology_id, _ = _chain(client, "无分析拓扑")
    response = client.post(f"{BASE}/{topology_id}/recovery/recommend", json={})
    assert response.status_code == 404
    assert "尚无传播分析结果" in response.json()["detail"]


def test_recommend_with_empty_analysis_rejected(client: TestClient) -> None:
    topology_id, _ = _chain(client, "无故障拓扑")
    analysis = _analyze(client, topology_id)
    assert analysis["fault_sources"] == []

    response = client.post(
        f"{BASE}/{topology_id}/recovery/recommend",
        json={"analysis_id": analysis["analysis_id"]},
    )
    assert response.status_code == 400
    assert "没有激活故障源" in response.json()["detail"]


def test_unknown_topology_rejected(client: TestClient) -> None:
    response = client.post(f"{BASE}/999999/recovery/recommend", json={})
    assert response.status_code == 404
    assert "拓扑不存在" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# 6. 策略配置
# --------------------------------------------------------------------------- #
def test_strategy_config_endpoint(client: TestClient) -> None:
    topology_id, _ = _chain(client, "配置查询拓扑")
    response = client.get(f"{BASE}/{topology_id}/recovery/strategies")
    assert response.status_code == 200, response.text
    data = response.json()

    types = {item["strategy_type"] for item in data["strategy_types"]}
    assert types == {"restart_service", "failover", "isolate_node"}

    weights = data["scoring_weights"]
    total = (
        weights["recovery_time"]
        + weights["impact"]
        + weights["cost"]
        + weights["risk"]
        + weights["business_recovery"]
    )
    assert abs(total - 1.0) < 1e-9
    assert data["reference_recovery_seconds"] > 0
    assert "模拟估算值" in data["estimation_notice"]


def test_strategy_config_unknown_topology(client: TestClient) -> None:
    response = client.get(f"{BASE}/999999/recovery/strategies")
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# 7. 恢复故障后可重新分析并重新推荐
# --------------------------------------------------------------------------- #
def test_recommend_after_fault_recovered(client: TestClient) -> None:
    topology_id, ids = _chain(client, "恢复后推荐拓扑")
    fault_id = _fault(client, topology_id, ids["database"], "node_down")
    _analyze(client, topology_id)

    recover = client.post(f"/api/faults/{fault_id}/recover")
    assert recover.status_code == 200, recover.text

    emptied = _analyze(client, topology_id)
    assert emptied["fault_sources"] == []

    response = client.post(f"{BASE}/{topology_id}/recovery/recommend", json={})
    # 最近一次分析没有激活故障，应明确报错，而不是编造策略
    assert response.status_code == 400
    assert "没有激活故障源" in response.json()["detail"]
