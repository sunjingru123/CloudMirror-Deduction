"""故障传播分析算法测试。

使用**独立构造的测试拓扑**（而非固定演示数据）验证算法：

1. 单条依赖链
2. 分支结构（一个数据库被多个应用依赖）
3. 环路（算法必须终止且不重复统计）
4. 多个故障源（去重与来源归因）
5. 无关节点不被误标记
6. 故障恢复后重新分析
7. 无激活故障时返回空结果
8. 无效故障 ID 被拒绝

依赖方向：`_edge(source, target)` 表示 source 依赖 target（source → target）。
"""

from fastapi.testclient import TestClient

BASE = "/api/topologies"
FAULTS = "/api/faults"


# --------------------------------------------------------------------------- #
# 辅助函数
# --------------------------------------------------------------------------- #
def _topology(client: TestClient, name: str = "测试拓扑") -> int:
    response = client.post(BASE, json={"name": name})
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _node(client: TestClient, topology_id: int, label: str, node_type: str = "app_server") -> int:
    response = client.post(
        f"{BASE}/{topology_id}/nodes", json={"name": label, "type": node_type}
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _edge(client: TestClient, topology_id: int, source: int, target: int) -> None:
    """创建依赖关系：source 依赖 target。"""
    response = client.post(
        f"{BASE}/{topology_id}/edges",
        json={"source_node_id": source, "target_node_id": target},
    )
    assert response.status_code == 201, response.text


def _fault(
    client: TestClient,
    topology_id: int,
    node_id: int,
    fault_type: str = "node_down",
    severity: str = "high",
) -> int:
    response = client.post(
        f"{BASE}/{topology_id}/faults",
        json={"source_node_id": node_id, "fault_type": fault_type, "severity": severity},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _analyze(
    client: TestClient, topology_id: int, fault_ids: list[int] | None = None
) -> dict:
    payload = {} if fault_ids is None else {"fault_ids": fault_ids}
    response = client.post(f"{BASE}/{topology_id}/analyze", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def _affected_map(result: dict) -> dict[int, dict]:
    return {item["node_id"]: item for item in result["affected_nodes"]}


def _path_names(result: dict, node_id: int) -> list[str]:
    for item in result["affected_nodes"]:
        if item["node_id"] == node_id:
            return [step["node_name"] for step in item["propagation_path"]]
    raise AssertionError(f"结果中不存在受影响节点：{node_id}")


# --------------------------------------------------------------------------- #
# 测试 1：单条依赖链
# --------------------------------------------------------------------------- #
def test_single_chain(client: TestClient) -> None:
    """数据库故障 → 应用服务器 → 负载均衡器 → 用户入口。"""
    topology_id = _topology(client, "单链")
    entry = _node(client, topology_id, "用户入口", "user_entry")
    lb = _node(client, topology_id, "负载均衡器", "load_balancer")
    app = _node(client, topology_id, "应用服务器", "app_server")
    database = _node(client, topology_id, "数据库", "database")

    # 依赖方向：entry → lb → app → database
    _edge(client, topology_id, entry, lb)
    _edge(client, topology_id, lb, app)
    _edge(client, topology_id, app, database)

    fault_id = _fault(client, topology_id, database)
    result = _analyze(client, topology_id)

    assert len(result["fault_sources"]) == 1
    assert result["fault_sources"][0]["source_node_id"] == database
    assert result["fault_sources"][0]["fault_id"] == fault_id

    affected = _affected_map(result)
    # 故障源自身不计入受影响节点
    assert database not in affected
    # 直接受影响：应用服务器（依赖数据库）
    assert affected[app]["impact_level"] == "direct"
    assert affected[app]["distance"] == 1
    # 间接受影响：负载均衡器、用户入口
    assert affected[lb]["impact_level"] == "indirect"
    assert affected[lb]["distance"] == 2
    assert affected[entry]["impact_level"] == "indirect"
    assert affected[entry]["distance"] == 3

    assert result["direct_affected_count"] == 1
    assert result["indirect_affected_count"] == 2
    assert result["total_affected_count"] == 3
    assert result["total_node_count"] == 4
    assert result["impact_ratio"] == 0.75

    # 传播路径：数据库 → 应用服务器 → 负载均衡器 → 用户入口
    assert _path_names(result, app) == ["数据库", "应用服务器"]
    assert _path_names(result, entry) == ["数据库", "应用服务器", "负载均衡器", "用户入口"]
    assert len(result["propagation_paths"]) == 3


# --------------------------------------------------------------------------- #
# 测试 2：分支结构
# --------------------------------------------------------------------------- #
def test_branch_all_dependents_affected(client: TestClient) -> None:
    """一个数据库被多个应用依赖，所有上游依赖节点都应被识别。"""
    topology_id = _topology(client, "分支")
    database = _node(client, topology_id, "共享数据库", "database")
    app1 = _node(client, topology_id, "应用1")
    app2 = _node(client, topology_id, "应用2")
    app3 = _node(client, topology_id, "应用3")

    _edge(client, topology_id, app1, database)
    _edge(client, topology_id, app2, database)
    _edge(client, topology_id, app3, database)

    _fault(client, topology_id, database)
    result = _analyze(client, topology_id)

    affected = _affected_map(result)
    assert set(affected) == {app1, app2, app3}
    assert all(affected[node]["impact_level"] == "direct" for node in (app1, app2, app3))
    assert result["direct_affected_count"] == 3
    assert result["indirect_affected_count"] == 0
    assert result["total_affected_count"] == 3


# --------------------------------------------------------------------------- #
# 测试 3：环路
# --------------------------------------------------------------------------- #
def test_cycle_terminates_without_duplicates(client: TestClient) -> None:
    """A → B → C → A（A 依赖 B，B 依赖 C，C 依赖 A），注入 C 故障。"""
    topology_id = _topology(client, "环路")
    a = _node(client, topology_id, "A")
    b = _node(client, topology_id, "B")
    c = _node(client, topology_id, "C")

    _edge(client, topology_id, a, b)
    _edge(client, topology_id, b, c)
    _edge(client, topology_id, c, a)

    _fault(client, topology_id, c)
    result = _analyze(client, topology_id)

    affected = _affected_map(result)
    # C 故障 → B（依赖 C）→ A（依赖 B）→ 再回到 C 已被访问，终止
    assert set(affected) == {a, b}
    assert affected[b]["distance"] == 1
    assert affected[a]["distance"] == 2
    assert result["total_affected_count"] == 2
    # 每个节点只统计一次
    assert len(result["affected_nodes"]) == 2


# --------------------------------------------------------------------------- #
# 测试 4：多个故障源
# --------------------------------------------------------------------------- #
def test_multiple_fault_sources_dedup_and_attribution(client: TestClient) -> None:
    """两个故障源，受影响节点去重，且路径来源归因正确。"""
    topology_id = _topology(client, "多源")
    a_db = _node(client, topology_id, "数据库A", "database")
    b_db = _node(client, topology_id, "数据库B", "database")
    a_lb = _node(client, topology_id, "负载A", "load_balancer")
    a_entry = _node(client, topology_id, "入口A", "user_entry")
    b_entry = _node(client, topology_id, "入口B", "user_entry")
    shared = _node(client, topology_id, "共享应用")

    _edge(client, topology_id, a_lb, a_db)
    _edge(client, topology_id, a_entry, a_lb)
    _edge(client, topology_id, b_entry, b_db)
    # 共享应用同时依赖两个数据库：应被两个故障源触达，但只统计一次
    _edge(client, topology_id, shared, a_db)
    _edge(client, topology_id, shared, b_db)

    fault_a = _fault(client, topology_id, a_db)
    fault_b = _fault(client, topology_id, b_db)
    result = _analyze(client, topology_id)

    assert len(result["fault_sources"]) == 2
    affected = _affected_map(result)
    assert set(affected) == {a_lb, a_entry, b_entry, shared}

    # 共享应用只出现一次，来源归因到 fault_id 较小者（fault_a）
    assert affected[shared]["distance"] == 1
    assert affected[shared]["source_fault_id"] == fault_a
    # 各自路径来源正确
    assert affected[a_lb]["source_fault_id"] == fault_a
    assert affected[a_entry]["source_fault_id"] == fault_a
    assert affected[b_entry]["source_fault_id"] == fault_b

    assert result["total_affected_count"] == 4
    assert result["direct_affected_count"] == 3
    assert result["indirect_affected_count"] == 1


def test_analyze_subset_of_faults(client: TestClient) -> None:
    """指定 fault_ids 时只分析所选故障。"""
    topology_id = _topology(client, "子集")
    a_db = _node(client, topology_id, "数据库A", "database")
    b_db = _node(client, topology_id, "数据库B", "database")
    a_app = _node(client, topology_id, "应用A")
    b_app = _node(client, topology_id, "应用B")
    _edge(client, topology_id, a_app, a_db)
    _edge(client, topology_id, b_app, b_db)
    fault_a = _fault(client, topology_id, a_db)
    _fault(client, topology_id, b_db)

    result = _analyze(client, topology_id, fault_ids=[fault_a])

    assert len(result["fault_sources"]) == 1
    affected = _affected_map(result)
    assert set(affected) == {a_app}
    assert result["total_affected_count"] == 1


# --------------------------------------------------------------------------- #
# 测试 5：无关节点
# --------------------------------------------------------------------------- #
def test_unrelated_nodes_not_marked(client: TestClient) -> None:
    topology_id = _topology(client, "无关节点")
    database = _node(client, topology_id, "数据库", "database")
    app = _node(client, topology_id, "应用")
    unrelated = _node(client, topology_id, "孤立节点", "cache")
    unrelated_target = _node(client, topology_id, "孤立依赖", "external_api")
    # 无关子图：unrelated → unrelated_target，与故障源不连通
    _edge(client, topology_id, app, database)
    _edge(client, topology_id, unrelated, unrelated_target)

    _fault(client, topology_id, database)
    result = _analyze(client, topology_id)

    affected = _affected_map(result)
    assert set(affected) == {app}
    assert unrelated not in affected
    assert unrelated_target not in affected


# --------------------------------------------------------------------------- #
# 测试 6：故障恢复
# --------------------------------------------------------------------------- #
def test_after_recovery_node_is_not_source(client: TestClient) -> None:
    topology_id = _topology(client, "恢复")
    database = _node(client, topology_id, "数据库", "database")
    app = _node(client, topology_id, "应用")
    _edge(client, topology_id, app, database)

    fault_id = _fault(client, topology_id, database)
    first = _analyze(client, topology_id)
    assert first["total_affected_count"] == 1

    assert client.post(f"{FAULTS}/{fault_id}/recover").status_code == 200

    second = _analyze(client, topology_id)
    assert second["fault_sources"] == []
    assert second["affected_nodes"] == []
    assert second["total_affected_count"] == 0
    assert second["impact_ratio"] == 0.0


def test_specifying_recovered_fault_rejected(client: TestClient) -> None:
    topology_id = _topology(client, "已恢复")
    database = _node(client, topology_id, "数据库", "database")
    _node(client, topology_id, "应用")
    fault_id = _fault(client, topology_id, database)
    client.post(f"{FAULTS}/{fault_id}/recover")

    response = client.post(
        f"{BASE}/{topology_id}/analyze", json={"fault_ids": [fault_id]}
    )

    assert response.status_code == 400


# --------------------------------------------------------------------------- #
# 测试 7：无故障场景
# --------------------------------------------------------------------------- #
def test_no_active_faults_returns_empty(client: TestClient) -> None:
    topology_id = _topology(client, "无故障")
    database = _node(client, topology_id, "数据库", "database")
    app = _node(client, topology_id, "应用")
    _edge(client, topology_id, app, database)

    result = _analyze(client, topology_id)

    assert result["analysis_id"] > 0
    assert result["fault_sources"] == []
    assert result["affected_nodes"] == []
    assert result["propagation_paths"] == []
    assert result["direct_affected_count"] == 0
    assert result["indirect_affected_count"] == 0
    assert result["total_affected_count"] == 0
    assert result["total_node_count"] == 2
    assert result["impact_ratio"] == 0.0


def test_analyze_missing_topology_rejected(client: TestClient) -> None:
    assert client.post(f"{BASE}/9999/analyze", json={}).status_code == 404


# --------------------------------------------------------------------------- #
# 测试 8：无效故障 ID
# --------------------------------------------------------------------------- #
def test_nonexistent_fault_id_rejected(client: TestClient) -> None:
    topology_id = _topology(client, "无效故障")
    _node(client, topology_id, "应用")

    response = client.post(
        f"{BASE}/{topology_id}/analyze", json={"fault_ids": [9999]}
    )

    assert response.status_code == 404


def test_fault_id_from_other_topology_rejected(client: TestClient) -> None:
    first = _topology(client, "拓扑1")
    second = _topology(client, "拓扑2")
    node_in_first = _node(client, first, "应用")
    _node(client, second, "应用")
    fault_in_first = _fault(client, first, node_in_first)

    response = client.post(
        f"{BASE}/{second}/analyze", json={"fault_ids": [fault_in_first]}
    )

    assert response.status_code == 404
    assert "不属于该拓扑" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# 结果持久化与可复现
# --------------------------------------------------------------------------- #
def test_analysis_is_persisted_and_latest(client: TestClient) -> None:
    topology_id = _topology(client, "持久化分析")
    database = _node(client, topology_id, "数据库", "database")
    app = _node(client, topology_id, "应用")
    _edge(client, topology_id, app, database)
    _fault(client, topology_id, database)

    result = _analyze(client, topology_id)

    latest = client.get(f"{BASE}/{topology_id}/analysis/latest")
    assert latest.status_code == 200
    assert latest.json()["analysis_id"] == result["analysis_id"]
    assert latest.json()["total_affected_count"] == 1


def test_latest_without_analysis_rejected(client: TestClient) -> None:
    topology_id = _topology(client, "无分析记录")

    assert client.get(f"{BASE}/{topology_id}/analysis/latest").status_code == 404


def test_analysis_is_reproducible(client: TestClient) -> None:
    """相同拓扑与故障记录应得到相同结果。"""
    topology_id = _topology(client, "可复现")
    entry = _node(client, topology_id, "入口", "user_entry")
    app = _node(client, topology_id, "应用")
    database = _node(client, topology_id, "数据库", "database")
    _edge(client, topology_id, entry, app)
    _edge(client, topology_id, app, database)
    _fault(client, topology_id, database)

    first = _analyze(client, topology_id)
    second = _analyze(client, topology_id)

    def signature(result: dict) -> list[tuple]:
        return sorted(
            (item["node_id"], item["distance"], item["impact_level"], item["source_fault_id"])
            for item in result["affected_nodes"]
        )

    assert signature(first) == signature(second)
    assert first["total_affected_count"] == second["total_affected_count"] == 2
