"""推演历史（传播分析记录）测试。

覆盖：

1. 分析结果落库后可在历史列表查询到
2. 列表按时间倒序、支持分页、total 正确
3. 可读取单条分析的完整详情
4. 恢复故障后历史分析仍可完整查看（快照生效）
5. 不同拓扑的历史记录相互隔离，禁止跨拓扑读取
6. 非法页码 / 页大小被拒绝
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
    response = client.post(
        f"{BASE}/{topology_id}/edges",
        json={"source_node_id": source, "target_node_id": target},
    )
    assert response.status_code == 201, response.text


def _fault(client: TestClient, topology_id: int, node_id: int) -> int:
    response = client.post(
        f"{BASE}/{topology_id}/faults",
        json={"source_node_id": node_id, "fault_type": "node_down", "severity": "high"},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _analyze(client: TestClient, topology_id: int) -> dict:
    response = client.post(f"{BASE}/{topology_id}/analyze", json={})
    assert response.status_code == 200, response.text
    return response.json()


def _history(
    client: TestClient, topology_id: int, page: int = 1, page_size: int = 20
) -> dict:
    response = client.get(
        f"{BASE}/{topology_id}/analyses",
        params={"page": page, "page_size": page_size},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _chain(client: TestClient, name: str) -> tuple[int, dict[str, int]]:
    topology_id = _topology(client, name)
    entry = _node(client, topology_id, "用户入口", "user_entry")
    app = _node(client, topology_id, "应用服务器", "app_server")
    database = _node(client, topology_id, "数据库", "database")
    _edge(client, topology_id, entry, app)
    _edge(client, topology_id, app, database)
    return topology_id, {"entry": entry, "app": app, "database": database}


# --------------------------------------------------------------------------- #
# 1. 保存与查询
# --------------------------------------------------------------------------- #
def test_analysis_saved_and_listed(client: TestClient) -> None:
    topology_id, ids = _chain(client, "历史拓扑")
    _fault(client, topology_id, ids["database"])
    analysis = _analyze(client, topology_id)

    page = _history(client, topology_id)
    assert page["total"] == 1
    assert len(page["items"]) == 1

    item = page["items"][0]
    assert item["analysis_id"] == analysis["analysis_id"]
    assert item["topology_id"] == topology_id
    assert item["topology_name"] == "历史拓扑"
    assert item["fault_source_count"] == 1
    assert item["total_affected_count"] == analysis["total_affected_count"]
    assert item["total_node_count"] == analysis["total_node_count"]
    assert item["impact_ratio"] == analysis["impact_ratio"]


def test_history_empty_for_new_topology(client: TestClient) -> None:
    topology_id, _ = _chain(client, "空历史拓扑")
    page = _history(client, topology_id)
    assert page["total"] == 0
    assert page["items"] == []
    assert page["page"] == 1
    assert page["page_size"] == 20


def test_history_unknown_topology(client: TestClient) -> None:
    response = client.get(f"{BASE}/999999/analyses")
    assert response.status_code == 404
    assert "拓扑不存在" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# 2. 倒序与分页
# --------------------------------------------------------------------------- #
def test_history_pagination_and_order(client: TestClient) -> None:
    topology_id, ids = _chain(client, "分页拓扑")
    _fault(client, topology_id, ids["database"])

    created: list[int] = []
    for _ in range(5):
        created.append(_analyze(client, topology_id)["analysis_id"])

    first_page = _history(client, topology_id, page=1, page_size=2)
    assert first_page["total"] == 5
    assert first_page["page"] == 1
    assert first_page["page_size"] == 2
    assert len(first_page["items"]) == 2
    # 时间倒序：最新（最后创建）在前
    assert first_page["items"][0]["analysis_id"] == created[-1]
    assert first_page["items"][1]["analysis_id"] == created[-2]

    second_page = _history(client, topology_id, page=2, page_size=2)
    assert [item["analysis_id"] for item in second_page["items"]] == [
        created[-3],
        created[-4],
    ]

    third_page = _history(client, topology_id, page=3, page_size=2)
    assert [item["analysis_id"] for item in third_page["items"]] == [created[0]]

    beyond = _history(client, topology_id, page=4, page_size=2)
    assert beyond["total"] == 5
    assert beyond["items"] == []


def test_history_invalid_pagination_rejected(client: TestClient) -> None:
    topology_id, _ = _chain(client, "非法分页拓扑")

    assert client.get(f"{BASE}/{topology_id}/analyses", params={"page": 0}).status_code == 422
    assert (
        client.get(f"{BASE}/{topology_id}/analyses", params={"page_size": 0}).status_code
        == 422
    )
    assert (
        client.get(f"{BASE}/{topology_id}/analyses", params={"page_size": 500}).status_code
        == 422
    )


# --------------------------------------------------------------------------- #
# 3. 详情
# --------------------------------------------------------------------------- #
def test_analysis_detail(client: TestClient) -> None:
    topology_id, ids = _chain(client, "详情拓扑")
    _fault(client, topology_id, ids["database"])
    analysis = _analyze(client, topology_id)

    response = client.get(f"{BASE}/{topology_id}/analyses/{analysis['analysis_id']}")
    assert response.status_code == 200, response.text
    detail = response.json()

    assert detail["analysis_id"] == analysis["analysis_id"]
    assert detail["topology_id"] == topology_id
    assert detail["fault_sources"][0]["source_node_name"] == "数据库"
    affected_names = {item["node_name"] for item in detail["affected_nodes"]}
    assert affected_names == {"应用服务器", "用户入口"}
    assert len(detail["propagation_paths"]) == 2


def test_analysis_detail_not_found(client: TestClient) -> None:
    topology_id, _ = _chain(client, "缺失详情拓扑")
    response = client.get(f"{BASE}/{topology_id}/analyses/999999")
    assert response.status_code == 404
    assert "分析结果不存在" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# 4. 故障恢复后历史仍可查看
# --------------------------------------------------------------------------- #
def test_history_survives_fault_recovery(client: TestClient) -> None:
    topology_id, ids = _chain(client, "恢复历史拓扑")
    fault_id = _fault(client, topology_id, ids["database"])
    analysis = _analyze(client, topology_id)

    recover = client.post(f"/api/faults/{fault_id}/recover")
    assert recover.status_code == 200, recover.text

    detail = client.get(
        f"{BASE}/{topology_id}/analyses/{analysis['analysis_id']}"
    ).json()
    # 故障恢复后，当时参与分析的故障源快照与影响结果仍然完整
    assert detail["fault_sources"][0]["source_node_id"] == ids["database"]
    assert detail["fault_sources"][0]["source_node_name"] == "数据库"
    assert detail["fault_sources"][0]["fault_type"] == "node_down"
    assert detail["total_affected_count"] == 2

    page = _history(client, topology_id)
    assert page["total"] == 1
    assert page["items"][0]["fault_source_count"] == 1


def test_history_survives_node_deletion(client: TestClient) -> None:
    topology_id, ids = _chain(client, "节点删除历史拓扑")
    _fault(client, topology_id, ids["database"])
    analysis = _analyze(client, topology_id)

    deleted = client.delete(f"{BASE}/{topology_id}/nodes/{ids['database']}")
    assert deleted.status_code == 204, deleted.text

    detail = client.get(
        f"{BASE}/{topology_id}/analyses/{analysis['analysis_id']}"
    ).json()
    # 节点被删除后名称快照仍保留
    assert detail["fault_sources"][0]["source_node_name"] == "数据库"
    assert detail["total_affected_count"] == 2


# --------------------------------------------------------------------------- #
# 5. 拓扑隔离
# --------------------------------------------------------------------------- #
def test_history_isolated_between_topologies(client: TestClient) -> None:
    topology_a, ids_a = _chain(client, "隔离拓扑A")
    _fault(client, topology_a, ids_a["database"])
    analysis_a = _analyze(client, topology_a)
    _analyze(client, topology_a)

    topology_b, ids_b = _chain(client, "隔离拓扑B")
    _fault(client, topology_b, ids_b["database"])
    analysis_b = _analyze(client, topology_b)

    page_a = _history(client, topology_a)
    page_b = _history(client, topology_b)

    assert page_a["total"] == 2
    assert page_b["total"] == 1
    assert analysis_b["analysis_id"] not in [
        item["analysis_id"] for item in page_a["items"]
    ]

    # 跨拓扑读取详情应被拒绝
    cross = client.get(f"{BASE}/{topology_b}/analyses/{analysis_a['analysis_id']}")
    assert cross.status_code == 404
    assert "不属于该拓扑" in cross.json()["detail"]
