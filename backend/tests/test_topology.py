"""拓扑管理接口测试。

覆盖：拓扑增删改查、节点增删改、依赖关系增删、错误处理与持久化。
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import init_db
from app.models.topology import Topology

BASE = "/api/topologies"


# --------------------------------------------------------------------------- #
# 辅助函数
# --------------------------------------------------------------------------- #
def _create_topology(client: TestClient, name: str = "电商系统") -> dict:
    response = client.post(BASE, json={"name": name, "description": "示例拓扑"})
    assert response.status_code == 201, response.text
    return response.json()


def _create_node(
    client: TestClient,
    topology_id: int,
    name: str,
    node_type: str = "app_server",
    **extra,
) -> dict:
    payload = {"name": name, "type": node_type}
    payload.update(extra)
    response = client.post(f"{BASE}/{topology_id}/nodes", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# 拓扑 CRUD
# --------------------------------------------------------------------------- #
def test_create_topology(client: TestClient) -> None:
    data = _create_topology(client, "订单系统")

    assert data["id"] > 0
    assert data["name"] == "订单系统"
    assert data["description"] == "示例拓扑"
    assert data["node_count"] == 0
    assert data["edge_count"] == 0
    assert data["created_at"]
    assert data["updated_at"]


def test_create_duplicate_topology_name_rejected(client: TestClient) -> None:
    _create_topology(client, "重复名称")

    response = client.post(BASE, json={"name": "重复名称"})

    assert response.status_code == 409
    assert "已存在" in response.json()["detail"]


def test_list_topologies(client: TestClient) -> None:
    _create_topology(client, "系统A")
    _create_topology(client, "系统B")

    response = client.get(BASE)

    assert response.status_code == 200
    names = [item["name"] for item in response.json()]
    assert names == ["系统A", "系统B"]


def test_update_topology(client: TestClient) -> None:
    created = _create_topology(client, "旧名称")

    response = client.put(f"{BASE}/{created['id']}", json={"name": "新名称"})

    assert response.status_code == 200
    assert response.json()["name"] == "新名称"


def test_get_topology_not_found(client: TestClient) -> None:
    response = client.get(f"{BASE}/9999")

    assert response.status_code == 404
    assert "不存在" in response.json()["detail"]


def test_delete_topology_cascades_nodes_and_edges(client: TestClient) -> None:
    topology = _create_topology(client)
    a = _create_node(client, topology["id"], "A")
    b = _create_node(client, topology["id"], "B", node_type="database")
    client.post(
        f"{BASE}/{topology['id']}/edges",
        json={"source_node_id": a["id"], "target_node_id": b["id"]},
    )

    response = client.delete(f"{BASE}/{topology['id']}")

    assert response.status_code == 204
    assert client.get(f"{BASE}/{topology['id']}").status_code == 404
    assert client.get(BASE).json() == []


# --------------------------------------------------------------------------- #
# 节点
# --------------------------------------------------------------------------- #
def test_add_and_query_nodes(client: TestClient) -> None:
    topology = _create_topology(client)
    _create_node(client, topology["id"], "网关", node_type="load_balancer")
    _create_node(client, topology["id"], "数据库", node_type="database")

    detail = client.get(f"{BASE}/{topology['id']}").json()

    assert len(detail["nodes"]) == 2
    types = {node["type"] for node in detail["nodes"]}
    assert types == {"load_balancer", "database"}
    for node in detail["nodes"]:
        assert node["status"] == "healthy"
        assert node["position_x"] == 0.0


def test_add_node_to_missing_topology_rejected(client: TestClient) -> None:
    response = client.post(f"{BASE}/9999/nodes", json={"name": "X", "type": "cache"})

    assert response.status_code == 404
    assert "拓扑不存在" in response.json()["detail"]


def test_add_node_invalid_type_rejected(client: TestClient) -> None:
    topology = _create_topology(client)

    response = client.post(
        f"{BASE}/{topology['id']}/nodes",
        json={"name": "X", "type": "not_a_type"},
    )

    assert response.status_code == 422


def test_update_node(client: TestClient) -> None:
    topology = _create_topology(client)
    node = _create_node(client, topology["id"], "旧节点", node_type="cache")

    response = client.put(
        f"{BASE}/{topology['id']}/nodes/{node['id']}",
        json={
            "name": "新节点",
            "type": "message_queue",
            "status": "degraded",
            "position_x": 120.5,
            "position_y": 80.0,
        },
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == "新节点"
    assert updated["type"] == "message_queue"
    assert updated["status"] == "degraded"
    assert updated["position_x"] == 120.5
    assert updated["position_y"] == 80.0


def test_update_missing_node_rejected(client: TestClient) -> None:
    topology = _create_topology(client)

    response = client.put(f"{BASE}/{topology['id']}/nodes/9999", json={"name": "X"})

    assert response.status_code == 404
    assert "节点不存在" in response.json()["detail"]


def test_delete_node_removes_related_edges(client: TestClient) -> None:
    topology = _create_topology(client)
    a = _create_node(client, topology["id"], "A")
    b = _create_node(client, topology["id"], "B")
    c = _create_node(client, topology["id"], "C")
    client.post(
        f"{BASE}/{topology['id']}/edges",
        json={"source_node_id": a["id"], "target_node_id": b["id"]},
    )
    client.post(
        f"{BASE}/{topology['id']}/edges",
        json={"source_node_id": c["id"], "target_node_id": b["id"]},
    )

    response = client.delete(f"{BASE}/{topology['id']}/nodes/{b['id']}")

    assert response.status_code == 204
    detail = client.get(f"{BASE}/{topology['id']}").json()
    assert [node["id"] for node in detail["nodes"]] == [a["id"], c["id"]]
    assert detail["edges"] == []


# --------------------------------------------------------------------------- #
# 依赖关系
# --------------------------------------------------------------------------- #
def test_add_edge_and_direction(client: TestClient) -> None:
    topology = _create_topology(client)
    app_server = _create_node(client, topology["id"], "应用", node_type="app_server")
    database = _create_node(client, topology["id"], "数据库", node_type="database")

    # 应用依赖数据库：source=应用，target=数据库
    response = client.post(
        f"{BASE}/{topology['id']}/edges",
        json={
            "source_node_id": app_server["id"],
            "target_node_id": database["id"],
            "description": "读写数据",
        },
    )

    assert response.status_code == 201
    edge = response.json()
    assert edge["source_node_id"] == app_server["id"]
    assert edge["target_node_id"] == database["id"]
    assert edge["description"] == "读写数据"

    detail = client.get(f"{BASE}/{topology['id']}").json()
    assert len(detail["edges"]) == 1
    assert detail["edges"][0]["source_node_id"] == app_server["id"]


def test_duplicate_edge_rejected(client: TestClient) -> None:
    topology = _create_topology(client)
    a = _create_node(client, topology["id"], "A")
    b = _create_node(client, topology["id"], "B")
    payload = {"source_node_id": a["id"], "target_node_id": b["id"]}
    assert client.post(f"{BASE}/{topology['id']}/edges", json=payload).status_code == 201

    response = client.post(f"{BASE}/{topology['id']}/edges", json=payload)

    assert response.status_code == 409
    assert "已存在" in response.json()["detail"]


def test_self_dependency_rejected(client: TestClient) -> None:
    topology = _create_topology(client)
    a = _create_node(client, topology["id"], "A")

    response = client.post(
        f"{BASE}/{topology['id']}/edges",
        json={"source_node_id": a["id"], "target_node_id": a["id"]},
    )

    assert response.status_code == 400
    assert "自身" in response.json()["detail"]


def test_edge_with_missing_node_rejected(client: TestClient) -> None:
    topology = _create_topology(client)
    a = _create_node(client, topology["id"], "A")

    response = client.post(
        f"{BASE}/{topology['id']}/edges",
        json={"source_node_id": a["id"], "target_node_id": 9999},
    )

    assert response.status_code == 404
    assert "不存在" in response.json()["detail"]


def test_edge_across_topologies_rejected(client: TestClient) -> None:
    first = _create_topology(client, "系统1")
    second = _create_topology(client, "系统2")
    node_in_first = _create_node(client, first["id"], "A")
    node_in_second = _create_node(client, second["id"], "B")

    response = client.post(
        f"{BASE}/{first['id']}/edges",
        json={
            "source_node_id": node_in_first["id"],
            "target_node_id": node_in_second["id"],
        },
    )

    assert response.status_code == 404


def test_delete_edge(client: TestClient) -> None:
    topology = _create_topology(client)
    a = _create_node(client, topology["id"], "A")
    b = _create_node(client, topology["id"], "B")
    edge = client.post(
        f"{BASE}/{topology['id']}/edges",
        json={"source_node_id": a["id"], "target_node_id": b["id"]},
    ).json()

    response = client.delete(f"{BASE}/{topology['id']}/edges/{edge['id']}")

    assert response.status_code == 204
    assert client.get(f"{BASE}/{topology['id']}").json()["edges"] == []


def test_delete_missing_edge_rejected(client: TestClient) -> None:
    topology = _create_topology(client)

    response = client.delete(f"{BASE}/{topology['id']}/edges/9999")

    assert response.status_code == 404


def test_cycle_is_allowed(client: TestClient) -> None:
    """允许拓扑存在环路，传播算法需自行处理。"""
    topology = _create_topology(client)
    a = _create_node(client, topology["id"], "A")
    b = _create_node(client, topology["id"], "B")
    c = _create_node(client, topology["id"], "C")

    statuses = [
        client.post(
            f"{BASE}/{topology['id']}/edges",
            json={"source_node_id": a["id"], "target_node_id": b["id"]},
        ).status_code,
        client.post(
            f"{BASE}/{topology['id']}/edges",
            json={"source_node_id": b["id"], "target_node_id": c["id"]},
        ).status_code,
        client.post(
            f"{BASE}/{topology['id']}/edges",
            json={"source_node_id": c["id"], "target_node_id": a["id"]},
        ).status_code,
    ]

    assert statuses == [201, 201, 201]
    assert len(client.get(f"{BASE}/{topology['id']}").json()["edges"]) == 3


# --------------------------------------------------------------------------- #
# 持久化与初始化
# --------------------------------------------------------------------------- #
def test_topology_is_persisted(client: TestClient, db_session: Session) -> None:
    created = _create_topology(client, "持久化拓扑")
    _create_node(client, created["id"], "节点")

    # 直接查询数据库，确认数据已写入
    row = db_session.get(Topology, created["id"])
    assert row is not None
    assert row.name == "持久化拓扑"

    # 新的客户端会话仍能读取到同一数据
    with TestClient(client.app) as another_client:
        detail = another_client.get(f"{BASE}/{created['id']}")
        assert detail.status_code == 200
        assert detail.json()["name"] == "持久化拓扑"
        assert len(detail.json()["nodes"]) == 1


def test_init_db_is_idempotent(client: TestClient) -> None:
    created = _create_topology(client, "幂等测试")

    init_db()
    init_db()

    data = client.get(BASE).json()
    assert [item["id"] for item in data] == [created["id"]]
