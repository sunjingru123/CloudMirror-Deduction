"""回归测试：数据库故障沿依赖反方向传播（用户报告的 6 节点场景）。

背景
----

用户在浏览器中搭建了如下拓扑（依赖方向：source 依赖 target）：

```
校园负载均衡器 → 应用服务器 A → PostgreSQL 数据库
应用服务器 A → Redis 缓存
应用服务器 A → 消息队列
```

对 PostgreSQL 数据库注入 `node_down` 后，期望：

- PostgreSQL 数据库：故障源
- 应用服务器 A：直接受影响
- 校园负载均衡器：间接受影响
- 应用服务器 B / Redis 缓存 / 消息队列：不受影响

本测试锁定该行为，防止回归。若未来有人改动传播方向或边语义，此测试会失败。
"""

from fastapi.testclient import TestClient

BASE = "/api/topologies"


# --------------------------------------------------------------------------- #
# 辅助函数（与 test_propagation.py 保持一致：source 依赖 target）
# --------------------------------------------------------------------------- #
def _topology(client: TestClient, name: str) -> int:
    response = client.post(BASE, json={"name": name})
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _node(client: TestClient, topology_id: int, label: str, node_type: str) -> int:
    response = client.post(
        f"{BASE}/{topology_id}/nodes", json={"name": label, "type": node_type}
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _edge(client: TestClient, topology_id: int, source: int, target: int) -> None:
    response = client.post(
        f"{BASE}/{topology_id}/edges",
        json={"source_node_id": source, "target_node_id": target},
    )
    assert response.status_code == 201, response.text


def _fault(client: TestClient, topology_id: int, node_id: int, fault_type: str = "node_down") -> int:
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


def _build_scenario(client: TestClient) -> dict[str, int]:
    """构建用户报告中的 6 节点 / 4 条依赖拓扑，返回节点 id 映射。"""
    topology_id = _topology(client, "校园综合服务平台")

    lb = _node(client, topology_id, "校园负载均衡器", "load_balancer")
    app_a = _node(client, topology_id, "应用服务器 A", "app_server")
    app_b = _node(client, topology_id, "应用服务器 B", "app_server")
    database = _node(client, topology_id, "PostgreSQL数据库", "database")
    queue = _node(client, topology_id, "消息队列", "message_queue")
    cache = _node(client, topology_id, "Redis缓存", "cache")

    # 依赖方向：A → B 表示 A 依赖 B
    _edge(client, topology_id, lb, app_a)  # 负载均衡器依赖应用服务器 A
    _edge(client, topology_id, app_a, database)  # 应用服务器 A 依赖数据库
    _edge(client, topology_id, app_a, queue)  # 应用服务器 A 依赖消息队列
    _edge(client, topology_id, app_a, cache)  # 应用服务器 A 依赖 Redis

    return {
        "topology_id": topology_id,
        "lb": lb,
        "app_a": app_a,
        "app_b": app_b,
        "database": database,
        "queue": queue,
        "cache": cache,
    }


# --------------------------------------------------------------------------- #
# 用例
# --------------------------------------------------------------------------- #
def test_database_fault_propagates_to_app_and_balancer(client: TestClient) -> None:
    """数据库故障：应用服务器 A 直接受影响，负载均衡器间接受影响。"""
    ids = _build_scenario(client)
    topology_id = ids["topology_id"]

    # 只对数据库注入故障
    _fault(client, topology_id, ids["database"])
    result = _analyze(client, topology_id)

    # 故障源数量
    assert len(result["fault_sources"]) == 1
    assert result["fault_sources"][0]["source_node_name"] == "PostgreSQL数据库"

    by_name = {item["node_name"]: item for item in result["affected_nodes"]}
    levels = {name: item["impact_level"] for name, item in by_name.items()}
    distances = {name: item["distance"] for name, item in by_name.items()}

    # 应用服务器 A：直接影响
    assert levels.get("应用服务器 A") == "direct"
    assert distances.get("应用服务器 A") == 1

    # 校园负载均衡器：间接受影响
    assert levels.get("校园负载均衡器") == "indirect"
    assert distances.get("校园负载均衡器") == 2

    # 无关节点不得被标记
    assert "应用服务器 B" not in levels
    assert "Redis缓存" not in levels
    assert "消息队列" not in levels

    # 故障源自身不计入受影响节点
    assert "PostgreSQL数据库" not in levels

    # 层级统计
    assert result["direct_affected_count"] == 1
    assert result["indirect_affected_count"] == 1
    assert result["total_affected_count"] == 2
    assert result["total_node_count"] == 6


def test_database_fault_impact_ratio(client: TestClient) -> None:
    """影响比例口径：受影响节点数 / 节点总数（2 / 6）。"""
    ids = _build_scenario(client)
    _fault(client, ids["topology_id"], ids["database"])
    result = _analyze(client, ids["topology_id"])

    assert result["impact_ratio"] == round(2 / 6, 4)


def test_database_fault_propagation_path(client: TestClient) -> None:
    """传播路径应与依赖反向一致：数据库 → 应用服务器 A → 校园负载均衡器。"""
    ids = _build_scenario(client)
    _fault(client, ids["topology_id"], ids["database"])
    result = _analyze(client, ids["topology_id"])

    by_target = {path["target_node_name"]: path for path in result["propagation_paths"]}
    assert set(by_target) == {"应用服务器 A", "校园负载均衡器"}

    app_path = by_target["应用服务器 A"]
    assert app_path["distance"] == 1
    assert [step["node_name"] for step in app_path["steps"]] == [
        "PostgreSQL数据库",
        "应用服务器 A",
    ]

    lb_path = by_target["校园负载均衡器"]
    assert lb_path["distance"] == 2
    assert [step["node_name"] for step in lb_path["steps"]] == [
        "PostgreSQL数据库",
        "应用服务器 A",
        "校园负载均衡器",
    ]


def test_reversed_edges_do_not_propagate(client: TestClient) -> None:
    """方向敏感的守护测试。

    若把依赖边建反（被依赖方 → 依赖方），则数据库故障不会传播到任何节点。
    该用例说明：**算法忠实于边方向**，前端必须按「依赖方向」创建连线，
    否则会出现用户报告的「受影响节点为 0」现象。
    """
    topology_id = _topology(client, "反向边拓扑")
    app = _node(client, topology_id, "应用服务器 A", "app_server")
    database = _node(client, topology_id, "PostgreSQL数据库", "database")

    # 反向：数据库 → 应用服务器 A（即「数据库依赖应用服务器 A」）
    _edge(client, topology_id, database, app)
    _fault(client, topology_id, database)
    result = _analyze(client, topology_id)

    assert result["total_affected_count"] == 0
    assert result["affected_nodes"] == []
