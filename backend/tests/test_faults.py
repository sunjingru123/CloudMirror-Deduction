"""故障注入与恢复接口测试。

覆盖：注入校验、重复激活故障拦截、不同类型并存、恢复流程与历史保留、
持久化、节点删除级联、以及与其他拓扑的隔离。
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.fault import FaultEvent

BASE = "/api/topologies"
FAULTS = "/api/faults"


# --------------------------------------------------------------------------- #
# 辅助函数
# --------------------------------------------------------------------------- #
def _create_topology(client: TestClient, name: str = "电商系统") -> dict:
    response = client.post(BASE, json={"name": name, "description": "示例拓扑"})
    assert response.status_code == 201, response.text
    return response.json()


def _create_node(
    client: TestClient, topology_id: int, name: str, node_type: str = "app_server"
) -> dict:
    response = client.post(
        f"{BASE}/{topology_id}/nodes", json={"name": name, "type": node_type}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _inject(
    client: TestClient,
    topology_id: int,
    node_id: int,
    fault_type: str = "node_down",
    severity: str = "high",
    description: str | None = None,
) -> dict:
    payload = {
        "source_node_id": node_id,
        "fault_type": fault_type,
        "severity": severity,
        "description": description,
    }
    response = client.post(f"{BASE}/{topology_id}/faults", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# 注入
# --------------------------------------------------------------------------- #
def test_inject_fault_success(client: TestClient) -> None:
    topology = _create_topology(client)
    node = _create_node(client, topology["id"], "数据库", node_type="database")

    fault = _inject(
        client, topology["id"], node["id"], "service_unavailable", "critical", "数据库不可用"
    )

    assert fault["id"] > 0
    assert fault["topology_id"] == topology["id"]
    assert fault["source_node_id"] == node["id"]
    assert fault["source_node_name"] == "数据库"
    assert fault["fault_type"] == "service_unavailable"
    assert fault["severity"] == "critical"
    assert fault["status"] == "active"
    assert fault["recovered_at"] is None
    assert fault["created_at"]


def test_inject_fault_invalid_type_rejected(client: TestClient) -> None:
    topology = _create_topology(client)
    node = _create_node(client, topology["id"], "应用")

    response = client.post(
        f"{BASE}/{topology['id']}/faults",
        json={"source_node_id": node["id"], "fault_type": "not_a_type"},
    )

    assert response.status_code == 422


def test_inject_fault_missing_topology_rejected(client: TestClient) -> None:
    response = client.post(
        f"{BASE}/9999/faults", json={"source_node_id": 1, "fault_type": "node_down"}
    )

    assert response.status_code == 404
    assert "拓扑不存在" in response.json()["detail"]


def test_inject_fault_missing_node_rejected(client: TestClient) -> None:
    topology = _create_topology(client)

    response = client.post(
        f"{BASE}/{topology['id']}/faults",
        json={"source_node_id": 9999, "fault_type": "node_down"},
    )

    assert response.status_code == 404
    assert "节点不存在" in response.json()["detail"]


def test_inject_fault_across_topology_rejected(client: TestClient) -> None:
    first = _create_topology(client, "系统1")
    second = _create_topology(client, "系统2")
    node_in_second = _create_node(client, second["id"], "B")

    response = client.post(
        f"{BASE}/{first['id']}/faults",
        json={"source_node_id": node_in_second["id"], "fault_type": "node_down"},
    )

    assert response.status_code == 404


def test_duplicate_active_fault_type_rejected(client: TestClient) -> None:
    topology = _create_topology(client)
    node = _create_node(client, topology["id"], "数据库", node_type="database")
    _inject(client, topology["id"], node["id"], "node_down")

    response = client.post(
        f"{BASE}/{topology['id']}/faults",
        json={"source_node_id": node["id"], "fault_type": "node_down"},
    )

    assert response.status_code == 409
    assert "同类型" in response.json()["detail"]


def test_different_fault_types_coexist(client: TestClient) -> None:
    topology = _create_topology(client)
    node = _create_node(client, topology["id"], "应用")
    _inject(client, topology["id"], node["id"], "node_down")
    _inject(client, topology["id"], node["id"], "network_latency")

    faults = client.get(f"{BASE}/{topology['id']}/faults").json()

    assert len(faults) == 2
    assert {fault["fault_type"] for fault in faults} == {"node_down", "network_latency"}


# --------------------------------------------------------------------------- #
# 查询
# --------------------------------------------------------------------------- #
def test_list_faults_includes_recovered_history(client: TestClient) -> None:
    topology = _create_topology(client)
    node = _create_node(client, topology["id"], "缓存", node_type="cache")
    fault = _inject(client, topology["id"], node["id"], "node_down")
    client.post(f"{FAULTS}/{fault['id']}/recover")

    faults = client.get(f"{BASE}/{topology['id']}/faults").json()

    assert len(faults) == 1
    assert faults[0]["status"] == "recovered"
    assert faults[0]["recovered_at"] is not None


def test_get_fault_detail_and_missing(client: TestClient) -> None:
    topology = _create_topology(client)
    node = _create_node(client, topology["id"], "应用")
    fault = _inject(client, topology["id"], node["id"])

    response = client.get(f"{FAULTS}/{fault['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == fault["id"]
    assert client.get(f"{FAULTS}/9999").status_code == 404


# --------------------------------------------------------------------------- #
# 恢复
# --------------------------------------------------------------------------- #
def test_recover_fault_updates_status(client: TestClient) -> None:
    topology = _create_topology(client)
    node = _create_node(client, topology["id"], "应用")
    fault = _inject(client, topology["id"], node["id"])

    response = client.post(f"{FAULTS}/{fault['id']}/recover")

    assert response.status_code == 200
    recovered = response.json()
    assert recovered["status"] == "recovered"
    assert recovered["recovered_at"] is not None

    # 记录仍然存在（不删除历史）
    assert client.get(f"{FAULTS}/{fault['id']}").status_code == 200


def test_recover_missing_fault_rejected(client: TestClient) -> None:
    assert client.post(f"{FAULTS}/9999/recover").status_code == 404


def test_recover_twice_rejected(client: TestClient) -> None:
    topology = _create_topology(client)
    node = _create_node(client, topology["id"], "应用")
    fault = _inject(client, topology["id"], node["id"])
    client.post(f"{FAULTS}/{fault['id']}/recover")

    response = client.post(f"{FAULTS}/{fault['id']}/recover")

    assert response.status_code == 409


def test_can_reinject_after_recovery(client: TestClient) -> None:
    topology = _create_topology(client)
    node = _create_node(client, topology["id"], "应用")
    fault = _inject(client, topology["id"], node["id"], "node_down")
    client.post(f"{FAULTS}/{fault['id']}/recover")

    # 同类型故障在恢复后可再次注入
    response = client.post(
        f"{BASE}/{topology['id']}/faults",
        json={"source_node_id": node["id"], "fault_type": "node_down"},
    )

    assert response.status_code == 201
    assert response.json()["status"] == "active"


# --------------------------------------------------------------------------- #
# 持久化与级联
# --------------------------------------------------------------------------- #
def test_fault_is_persisted(client: TestClient, db_session: Session) -> None:
    topology = _create_topology(client)
    node = _create_node(client, topology["id"], "应用")
    fault = _inject(client, topology["id"], node["id"])

    row = db_session.get(FaultEvent, fault["id"])

    assert row is not None
    assert row.fault_type == "node_down"
    assert row.status == "active"


def test_delete_node_cascades_faults(client: TestClient) -> None:
    topology = _create_topology(client)
    node = _create_node(client, topology["id"], "应用")
    fault = _inject(client, topology["id"], node["id"])

    assert client.delete(f"{BASE}/{topology['id']}/nodes/{node['id']}").status_code == 204

    assert client.get(f"{FAULTS}/{fault['id']}").status_code == 404
    assert client.get(f"{BASE}/{topology['id']}/faults").json() == []


def test_delete_topology_cascades_faults(client: TestClient) -> None:
    topology = _create_topology(client)
    node = _create_node(client, topology["id"], "应用")
    _inject(client, topology["id"], node["id"])

    assert client.delete(f"{BASE}/{topology['id']}").status_code == 204

    # 拓扑删除后，其故障无法通过接口访问
    assert client.get(f"{BASE}/{topology['id']}/faults").status_code == 404
