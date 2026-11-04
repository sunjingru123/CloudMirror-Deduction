"""基于显式冗余关系的 failover（备用节点切换）适用性测试。

Phase 5 的核心变更：备用节点**只**来自显式冗余组，不再按「同类型且未受影响
节点」推断。本文件覆盖显式冗余下的选择与前置条件检查规则。

覆盖：

1. 主节点故障 + 存在可用备用节点 → 生成切换方案并被推荐
2. 没有冗余组 → 不适用（并给出原因）
3. 存在同类型节点但没有冗余关系 → 不适用（不推断备用节点）
4. 备用节点自身有激活故障 → 不适用
5. 备用节点受到传播影响 → 不适用
6. 多个备用节点 → 按 priority 选择
7. 优先级相同时 → 按 node_id 稳定的次级规则选择
8. 故障节点不是主节点（而是备用节点）→ 不适用
9. 备用节点状态异常（降级）→ 不适用
10. 冗余组为双活模式 → 当前版本不适用
11. 多个故障源中只要有一个缺少隐式冗余 → 不适用
12. 删除冗余组后不再认为存在备用节点
13. 备用节点存在无关的正常依赖 → 仍然适用（不产生误判）
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
    client: TestClient, topology_id: int, label: str, node_type: str = "database"
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


def _group(
    client: TestClient,
    topology_id: int,
    *,
    name: str = "主备组",
    members: list[dict],
    redundancy_type: str = "active_standby",
) -> int:
    response = client.post(
        f"{BASE}/{topology_id}/redundancy-groups",
        json={"name": name, "redundancy_type": redundancy_type, "members": members},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _fault(
    client: TestClient, topology_id: int, node_id: int, fault_type: str = "node_down"
) -> int:
    response = client.post(
        f"{BASE}/{topology_id}/faults",
        json={"source_node_id": node_id, "fault_type": fault_type, "severity": "high"},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _recommend(client: TestClient, topology_id: int) -> dict:
    analyze = client.post(f"{BASE}/{topology_id}/analyze", json={})
    assert analyze.status_code == 200, analyze.text
    response = client.post(f"{BASE}/{topology_id}/recovery/recommend", json={})
    assert response.status_code == 201, response.text
    return response.json()


def _failover(result: dict) -> dict:
    return next(item for item in result["strategies"] if item["strategy_type"] == "failover")


def _checks(failover: dict) -> dict[str, list[tuple[bool, str]]]:
    """把前置条件检查按 check_name 归并。"""
    grouped: dict[str, list[tuple[bool, str]]] = {}
    for item in failover["prerequisite_checks"]:
        grouped.setdefault(item["check_name"], []).append((item["passed"], item["detail"]))
    return grouped


def _layer(
    client: TestClient, name: str, *, standby_of_app: bool = False
) -> tuple[int, dict[str, int]]:
    """入口 → 应用 → 主库，应用 → 备库（备库可选地依赖应用）。"""
    topology_id = _topology(client, name)
    entry = _node(client, topology_id, "用户入口", "user_entry")
    app = _node(client, topology_id, "应用服务器", "app_server")
    primary = _node(client, topology_id, "主数据库")
    standby = _node(client, topology_id, "备数据库")
    _edge(client, topology_id, entry, app)
    _edge(client, topology_id, app, primary)
    if standby_of_app:
        _edge(client, topology_id, standby, app)
    else:
        _edge(client, topology_id, app, standby)
    return topology_id, {"entry": entry, "app": app, "primary": primary, "standby": standby}


# --------------------------------------------------------------------------- #
# 1. 适用：主节点故障 + 可用备用节点
# --------------------------------------------------------------------------- #
def test_failover_applicable_with_explicit_standby(client: TestClient) -> None:
    topology_id, ids = _layer(client, "显式主备拓扑")
    group_id = _group(
        client,
        topology_id,
        name="数据库主备",
        members=[
            {"node_id": ids["primary"], "member_role": "primary"},
            {"node_id": ids["standby"], "member_role": "standby", "priority": 1},
        ],
    )
    _fault(client, topology_id, ids["primary"])

    result = _recommend(client, topology_id)
    failover = _failover(result)

    assert failover["applicable"] is True
    assert failover["redundancy_group_id"] == group_id
    assert failover["redundancy_group_name"] == "数据库主备"
    assert failover["primary_node_id"] == ids["primary"]
    assert failover["selected_standby_node_id"] == ids["standby"]
    assert failover["selection_reason"]
    assert "priority" in failover["selection_reason"]
    # 可用性提示：仅模拟判定，不代表真实生产已验证
    assert "不代表真实生产环境" in failover["selection_reason"]

    candidates = failover["standby_candidates"]
    assert [item["node_id"] for item in candidates] == [ids["standby"]]
    assert candidates[0]["eligible"] is True

    checks = _checks(failover)
    assert all(passed for passed, _ in checks["是否存在显式主备关系"])
    assert all(passed for passed, _ in checks["故障节点是否为主节点"])
    assert all(passed for passed, _ in checks["备用节点是否存在激活故障"])
    assert all(passed for passed, _ in checks["备用节点是否受到传播影响"])
    assert all(passed for passed, _ in checks["是否满足节点类型要求"])
    assert all(passed for passed, _ in checks["备用节点是否存在故障依赖"])

    assert result["recommended_strategy_type"] == "failover"


# --------------------------------------------------------------------------- #
# 2. 不适用：没有冗余组
# --------------------------------------------------------------------------- #
def test_failover_inapplicable_without_any_group(client: TestClient) -> None:
    topology_id, ids = _layer(client, "无冗余组拓扑")
    _fault(client, topology_id, ids["primary"])

    failover = _failover(_recommend(client, topology_id))

    assert failover["applicable"] is False
    assert "显式冗余关系" in failover["inapplicable_reason"]
    assert failover["redundancy_group_id"] is None
    assert failover["selected_standby_node_id"] is None
    checks = _checks(failover)
    assert [passed for passed, _ in checks["是否存在显式主备关系"]] == [False]


def test_same_type_node_without_redundancy_is_not_standby(client: TestClient) -> None:
    """拓扑里存在同类型、未受影响的节点，但没有冗余关系 → 不推断为备用节点。"""
    topology_id, ids = _layer(client, "同类型但无冗余拓扑")
    _fault(client, topology_id, ids["primary"])

    failover = _failover(_recommend(client, topology_id))

    assert failover["applicable"] is False
    assert failover["selected_standby_node_id"] is None
    assert failover["standby_candidates"] == []


# --------------------------------------------------------------------------- #
# 3. 不适用：备用节点自身异常
# --------------------------------------------------------------------------- #
def test_standby_with_active_fault_cannot_be_used(client: TestClient) -> None:
    topology_id, ids = _layer(client, "备用节点故障拓扑")
    _group(
        client,
        topology_id,
        members=[
            {"node_id": ids["primary"], "member_role": "primary"},
            {"node_id": ids["standby"], "member_role": "standby", "priority": 1},
        ],
    )
    _fault(client, topology_id, ids["primary"])
    _fault(client, topology_id, ids["standby"])

    failover = _failover(_recommend(client, topology_id))

    assert failover["applicable"] is False
    checks = _checks(failover)
    assert [passed for passed, _ in checks["备用节点是否存在激活故障"]] == [False]
    assert failover["standby_candidates"][0]["eligible"] is False


def test_degraded_standby_cannot_be_used(client: TestClient) -> None:
    topology_id, ids = _layer(client, "备用节点降级拓扑")
    _group(
        client,
        topology_id,
        members=[
            {"node_id": ids["primary"], "member_role": "primary"},
            {"node_id": ids["standby"], "member_role": "standby", "priority": 1},
        ],
    )
    updated = client.put(
        f"{BASE}/{topology_id}/nodes/{ids['standby']}", json={"status": "degraded"}
    )
    assert updated.status_code == 200, updated.text
    _fault(client, topology_id, ids["primary"])

    failover = _failover(_recommend(client, topology_id))

    assert failover["applicable"] is False
    checks = _checks(failover)
    assert [passed for passed, _ in checks["备用节点是否正常"]] == [False]


def test_standby_affected_by_propagation_cannot_be_used(client: TestClient) -> None:
    """备用节点自身依赖了受影响节点 → 被传播影响，且有故障依赖。"""
    topology_id, ids = _layer(client, "备用节点受影响拓扑", standby_of_app=True)
    _group(
        client,
        topology_id,
        members=[
            {"node_id": ids["primary"], "member_role": "primary"},
            {"node_id": ids["standby"], "member_role": "standby", "priority": 1},
        ],
    )
    _fault(client, topology_id, ids["primary"])

    failover = _failover(_recommend(client, topology_id))

    assert failover["applicable"] is False
    checks = _checks(failover)
    assert [passed for passed, _ in checks["备用节点是否受到传播影响"]] == [False]
    assert [passed for passed, _ in checks["备用节点是否存在故障依赖"]] == [False]


def test_standby_with_unrelated_dependency_is_still_usable(client: TestClient) -> None:
    """备用节点存在无关的正常依赖时不应被误判。"""
    topology_id, ids = _layer(client, "备用节点无关依赖拓扑")
    cache = _node(client, topology_id, "缓存", "cache")
    _edge(client, topology_id, ids["standby"], cache)

    _group(
        client,
        topology_id,
        members=[
            {"node_id": ids["primary"], "member_role": "primary"},
            {"node_id": ids["standby"], "member_role": "standby", "priority": 1},
        ],
    )
    _fault(client, topology_id, ids["primary"])

    failover = _failover(_recommend(client, topology_id))

    assert failover["applicable"] is True
    checks = _checks(failover)
    assert all(passed for passed, _ in checks["备用节点是否存在故障依赖"])


# --------------------------------------------------------------------------- #
# 4. 备用节点选择规则
# --------------------------------------------------------------------------- #
def test_highest_priority_standby_selected(client: TestClient) -> None:
    topology_id = _topology(client, "优先级选择拓扑")
    primary = _node(client, topology_id, "主库")
    low_priority = _node(client, topology_id, "备库-次选")
    high_priority = _node(client, topology_id, "备库-首选")
    _edge(client, topology_id, primary, high_priority)

    _group(
        client,
        topology_id,
        members=[
            {"node_id": primary, "member_role": "primary"},
            {"node_id": low_priority, "member_role": "standby", "priority": 5},
            {"node_id": high_priority, "member_role": "standby", "priority": 1},
        ],
    )
    _fault(client, topology_id, primary)

    failover = _failover(_recommend(client, topology_id))

    assert failover["applicable"] is True
    # priority 数值越小优先级越高
    assert failover["selected_standby_node_id"] == high_priority
    assert [item["node_id"] for item in failover["standby_candidates"]] == [
        high_priority,
        low_priority,
    ]
    assert all(item["eligible"] for item in failover["standby_candidates"])


def test_equal_priority_uses_stable_secondary_order(client: TestClient) -> None:
    topology_id = _topology(client, "同优先级选择拓扑")
    primary = _node(client, topology_id, "主库")
    first = _node(client, topology_id, "备库一")
    second = _node(client, topology_id, "备库二")
    _edge(client, topology_id, primary, first)

    _group(
        client,
        topology_id,
        members=[
            {"node_id": primary, "member_role": "primary"},
            {"node_id": first, "member_role": "standby", "priority": 1},
            {"node_id": second, "member_role": "standby", "priority": 1},
        ],
    )
    _fault(client, topology_id, primary)

    first_run = _failover(_recommend(client, topology_id))
    second_run = _failover(_recommend(client, topology_id))

    # 优先级相同 → 按 node_id 升序（first < second），且结果可复现
    assert first_run["selected_standby_node_id"] == first
    assert first_run["selected_standby_node_id"] == second_run["selected_standby_node_id"]
    assert first_run["selection_reason"] == second_run["selection_reason"]


# --------------------------------------------------------------------------- #
# 5. 其他不适用场景
# --------------------------------------------------------------------------- #
def test_faulty_standby_is_not_switched(client: TestClient) -> None:
    topology_id, ids = _layer(client, "故障节点为备用拓扑")
    _group(
        client,
        topology_id,
        members=[
            {"node_id": ids["primary"], "member_role": "primary"},
            {"node_id": ids["standby"], "member_role": "standby", "priority": 1},
        ],
    )
    _fault(client, topology_id, ids["standby"])

    failover = _failover(_recommend(client, topology_id))

    assert failover["applicable"] is False
    checks = _checks(failover)
    assert [passed for passed, _ in checks["故障节点是否为主节点"]] == [False]


def test_active_active_group_not_switched(client: TestClient) -> None:
    topology_id = _topology(client, "双活组拓扑")
    first = _node(client, topology_id, "双活库一")
    second = _node(client, topology_id, "双活库二")

    _group(
        client,
        topology_id,
        name="双活组",
        redundancy_type="active_active",
        members=[
            {"node_id": first, "member_role": "active"},
            {"node_id": second, "member_role": "active"},
        ],
    )
    _fault(client, topology_id, first)

    failover = _failover(_recommend(client, topology_id))

    assert failover["applicable"] is False
    checks = _checks(failover)
    assert [passed for passed, _ in checks["冗余模式是否支持切换"]] == [False]


def test_multiple_fault_sources_one_without_group(client: TestClient) -> None:
    topology_id, ids = _layer(client, "多故障源拓扑")
    _group(
        client,
        topology_id,
        members=[
            {"node_id": ids["primary"], "member_role": "primary"},
            {"node_id": ids["standby"], "member_role": "standby", "priority": 1},
        ],
    )
    _fault(client, topology_id, ids["primary"])
    _fault(client, topology_id, ids["app"], "service_unavailable")

    failover = _failover(_recommend(client, topology_id))

    # 应用服务器没有显式冗余组，切换方案整体不适用
    assert failover["applicable"] is False
    assert "应用服务器" in failover["inapplicable_reason"]


def test_group_deletion_removes_standby_from_failover(client: TestClient) -> None:
    topology_id, ids = _layer(client, "删除冗余组拓扑")
    group_id = _group(
        client,
        topology_id,
        members=[
            {"node_id": ids["primary"], "member_role": "primary"},
            {"node_id": ids["standby"], "member_role": "standby", "priority": 1},
        ],
    )
    _fault(client, topology_id, ids["primary"])

    before = _failover(_recommend(client, topology_id))
    assert before["applicable"] is True

    assert client.delete(f"/api/redundancy-groups/{group_id}").status_code == 204

    after = _failover(_recommend(client, topology_id))
    assert after["applicable"] is False
    assert after["redundancy_group_id"] is None
    assert after["selected_standby_node_id"] is None
