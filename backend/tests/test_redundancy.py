"""显式冗余关系（冗余组 / 成员）测试。

覆盖：

1. 一次请求创建完整的 active_standby 主备组（主节点 + 多个备用节点及优先级）
2. 列表 / 详情 / 更新 / 删除
3. 结构约束：主备模式缺主节点 / 缺备用节点 / 备用缺优先级均被拒绝
4. 同一节点在同一组重复出现被拒绝
5. 跨拓扑节点、跨冗余组复用被拒绝
6. 双活模式的角色与数量约束
7. 删除节点后的成员清理与冗余组一致性
8. 删除拓扑后冗余组与成员级联删除
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.redundancy import RedundancyGroup, RedundancyMember

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


def _standby_group(
    client: TestClient,
    topology_id: int,
    *,
    name: str = "主备组",
    primary: int,
    standbys: list[int],
    redundancy_type: str = "active_standby",
    description: str | None = None,
):
    members = [{"node_id": primary, "member_role": "primary"}]
    members += [
        {"node_id": node_id, "member_role": "standby", "priority": index + 1}
        for index, node_id in enumerate(standbys)
    ]
    return client.post(
        f"{BASE}/{topology_id}/redundancy-groups",
        json={
            "name": name,
            "redundancy_type": redundancy_type,
            "description": description,
            "members": members,
        },
    )


def _main_pair(client: TestClient, name: str = "冗余拓扑") -> tuple[int, dict[str, int]]:
    topology_id = _topology(client, name)
    primary = _node(client, topology_id, "主数据库")
    standby = _node(client, topology_id, "备数据库")
    return topology_id, {"primary": primary, "standby": standby}


# --------------------------------------------------------------------------- #
# 1. 创建 / 列表 / 详情
# --------------------------------------------------------------------------- #
def test_create_active_standby_group(client: TestClient) -> None:
    topology_id, ids = _main_pair(client, "创建冗余组拓扑")
    third = _node(client, topology_id, "备数据库二")

    response = _standby_group(
        client,
        topology_id,
        name="数据库主备",
        primary=ids["primary"],
        standbys=[ids["standby"], third],
        description="主库 + 两个备库",
    )
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["topology_id"] == topology_id
    assert body["name"] == "数据库主备"
    assert body["redundancy_type"] == "active_standby"
    assert body["description"] == "主库 + 两个备库"
    assert len(body["members"]) == 3

    # 展示顺序：主节点在前，备用节点按优先级
    roles = [item["member_role"] for item in body["members"]]
    assert roles == ["primary", "standby", "standby"]
    assert body["members"][0]["node_id"] == ids["primary"]
    assert [item["priority"] for item in body["members"][1:]] == [1, 2]
    assert body["members"][0]["node_name"] == "主数据库"


def test_list_and_get_groups(client: TestClient) -> None:
    topology_id, ids = _main_pair(client, "列表冗余拓扑")
    created = _standby_group(
        client, topology_id, primary=ids["primary"], standbys=[ids["standby"]]
    ).json()

    listed = client.get(f"{BASE}/{topology_id}/redundancy-groups")
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()] == [created["id"]]

    detail = client.get(f"/api/redundancy-groups/{created['id']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["id"] == created["id"]

    missing = client.get("/api/redundancy-groups/999999")
    assert missing.status_code == 404
    assert "冗余组不存在" in missing.json()["detail"]


def test_list_groups_unknown_topology(client: TestClient) -> None:
    response = client.get(f"{BASE}/999999/redundancy-groups")
    assert response.status_code == 404
    assert "拓扑不存在" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# 2. 更新 / 删除
# --------------------------------------------------------------------------- #
def test_update_group_replaces_members(client: TestClient) -> None:
    topology_id, ids = _main_pair(client, "更新冗余拓扑")
    third = _node(client, topology_id, "备数据库二")
    created = _standby_group(
        client, topology_id, primary=ids["primary"], standbys=[ids["standby"]]
    ).json()

    response = client.put(
        f"/api/redundancy-groups/{created['id']}",
        json={
            "name": "数据库主备（更新）",
            "members": [
                {"node_id": ids["primary"], "member_role": "primary"},
                {"node_id": third, "member_role": "standby", "priority": 3},
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "数据库主备（更新）"
    assert [item["node_id"] for item in body["members"]] == [ids["primary"], third]


def test_update_group_without_members_keeps_members(client: TestClient) -> None:
    topology_id, ids = _main_pair(client, "保留成员拓扑")
    created = _standby_group(
        client, topology_id, primary=ids["primary"], standbys=[ids["standby"]]
    ).json()

    response = client.put(
        f"/api/redundancy-groups/{created['id']}", json={"description": "仅改描述"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["description"] == "仅改描述"
    assert len(body["members"]) == 2


def test_update_group_to_incompatible_members_rejected(client: TestClient) -> None:
    topology_id, ids = _main_pair(client, "模式不兼容拓扑")
    created = _standby_group(
        client, topology_id, primary=ids["primary"], standbys=[ids["standby"]]
    ).json()

    # 只提供成员列表时沿用现有模式（active_standby），缺少备用节点 → 400
    response = client.put(
        f"/api/redundancy-groups/{created['id']}",
        json={"members": [{"node_id": ids["primary"], "member_role": "primary"}]},
    )
    assert response.status_code == 400
    assert "备用节点" in response.json()["detail"]


def test_delete_group(client: TestClient) -> None:
    topology_id, ids = _main_pair(client, "删除冗余拓扑")
    created = _standby_group(
        client, topology_id, primary=ids["primary"], standbys=[ids["standby"]]
    ).json()

    removed = client.delete(f"/api/redundancy-groups/{created['id']}")
    assert removed.status_code == 204, removed.text
    assert client.get(f"{BASE}/{topology_id}/redundancy-groups").json() == []
    assert client.get(f"/api/redundancy-groups/{created['id']}").status_code == 404


# --------------------------------------------------------------------------- #
# 3. 结构约束
# --------------------------------------------------------------------------- #
def test_active_standby_requires_primary(client: TestClient) -> None:
    topology_id, ids = _main_pair(client, "缺主节点拓扑")
    response = client.post(
        f"{BASE}/{topology_id}/redundancy-groups",
        json={
            "name": "缺主节点组",
            "redundancy_type": "active_standby",
            "members": [
                {"node_id": ids["standby"], "member_role": "standby", "priority": 1}
            ],
        },
    )
    assert response.status_code == 400
    assert "主节点" in response.json()["detail"]


def test_active_standby_requires_standby(client: TestClient) -> None:
    topology_id, ids = _main_pair(client, "缺备用节点拓扑")
    response = client.post(
        f"{BASE}/{topology_id}/redundancy-groups",
        json={
            "name": "缺备用节点组",
            "redundancy_type": "active_standby",
            "members": [{"node_id": ids["primary"], "member_role": "primary"}],
        },
    )
    assert response.status_code == 400
    assert "备用节点" in response.json()["detail"]


def test_standby_requires_priority(client: TestClient) -> None:
    topology_id, ids = _main_pair(client, "缺优先级拓扑")
    response = client.post(
        f"{BASE}/{topology_id}/redundancy-groups",
        json={
            "name": "缺优先级组",
            "redundancy_type": "active_standby",
            "members": [
                {"node_id": ids["primary"], "member_role": "primary"},
                {"node_id": ids["standby"], "member_role": "standby"},
            ],
        },
    )
    assert response.status_code == 400
    assert "优先级" in response.json()["detail"]


def test_two_primaries_rejected(client: TestClient) -> None:
    topology_id, ids = _main_pair(client, "双主节点拓扑")
    response = client.post(
        f"{BASE}/{topology_id}/redundancy-groups",
        json={
            "name": "双主节点组",
            "redundancy_type": "active_standby",
            "members": [
                {"node_id": ids["primary"], "member_role": "primary"},
                {"node_id": ids["standby"], "member_role": "primary"},
            ],
        },
    )
    assert response.status_code == 400
    assert "只能有一个主节点" in response.json()["detail"]


def test_duplicate_node_in_group_rejected(client: TestClient) -> None:
    topology_id, ids = _main_pair(client, "重复成员拓扑")
    response = client.post(
        f"{BASE}/{topology_id}/redundancy-groups",
        json={
            "name": "重复成员组",
            "redundancy_type": "active_standby",
            "members": [
                {"node_id": ids["primary"], "member_role": "primary"},
                {"node_id": ids["primary"], "member_role": "standby", "priority": 1},
            ],
        },
    )
    assert response.status_code == 409
    assert "重复" in response.json()["detail"]


def test_empty_members_rejected(client: TestClient) -> None:
    topology_id, _ = _main_pair(client, "空成员拓扑")
    response = client.post(
        f"{BASE}/{topology_id}/redundancy-groups",
        json={"name": "空成员组", "redundancy_type": "active_standby", "members": []},
    )
    assert response.status_code == 400
    assert "至少需要一个成员" in response.json()["detail"]


def test_active_active_constraints(client: TestClient) -> None:
    topology_id = _topology(client, "双活约束拓扑")
    first = _node(client, topology_id, "双活节点一")
    second = _node(client, topology_id, "双活节点二")

    too_few = client.post(
        f"{BASE}/{topology_id}/redundancy-groups",
        json={
            "name": "双活单节点",
            "redundancy_type": "active_active",
            "members": [{"node_id": first, "member_role": "active"}],
        },
    )
    assert too_few.status_code == 400
    assert "两个 active" in too_few.json()["detail"]

    wrong_role = client.post(
        f"{BASE}/{topology_id}/redundancy-groups",
        json={
            "name": "双活错误角色",
            "redundancy_type": "active_active",
            "members": [
                {"node_id": first, "member_role": "active"},
                {"node_id": second, "member_role": "primary"},
            ],
        },
    )
    assert wrong_role.status_code == 400
    assert "active" in wrong_role.json()["detail"]

    ok = client.post(
        f"{BASE}/{topology_id}/redundancy-groups",
        json={
            "name": "双活合法组",
            "redundancy_type": "active_active",
            "members": [
                {"node_id": first, "member_role": "active"},
                {"node_id": second, "member_role": "active"},
            ],
        },
    )
    assert ok.status_code == 201, ok.text
    assert [item["member_role"] for item in ok.json()["members"]] == ["active", "active"]


# --------------------------------------------------------------------------- #
# 4. 跨拓扑 / 跨组
# --------------------------------------------------------------------------- #
def test_cross_topology_node_rejected(client: TestClient) -> None:
    topology_a, ids_a = _main_pair(client, "跨拓扑A")
    topology_b = _topology(client, "跨拓扑B")
    foreign = _node(client, topology_b, "外部数据库")

    response = client.post(
        f"{BASE}/{topology_a}/redundancy-groups",
        json={
            "name": "跨拓扑组",
            "redundancy_type": "active_standby",
            "members": [
                {"node_id": ids_a["primary"], "member_role": "primary"},
                {"node_id": foreign, "member_role": "standby", "priority": 1},
            ],
        },
    )
    assert response.status_code == 404
    assert "不存在于该拓扑" in response.json()["detail"]


def test_node_cannot_join_two_groups(client: TestClient) -> None:
    topology_id, ids = _main_pair(client, "跨组复用拓扑")
    third = _node(client, topology_id, "第三个数据库")

    first = _standby_group(
        client, topology_id, name="第一组", primary=ids["primary"], standbys=[ids["standby"]]
    )
    assert first.status_code == 201, first.text

    second = _standby_group(
        client, topology_id, name="第二组", primary=ids["primary"], standbys=[third]
    )
    assert second.status_code == 409
    assert "其他冗余组" in second.json()["detail"]


# --------------------------------------------------------------------------- #
# 5. 节点 / 拓扑删除
# --------------------------------------------------------------------------- #
def test_delete_standby_node_keeps_group_delete_primary_removes_group(
    client: TestClient,
) -> None:
    topology_id = _topology(client, "节点删除冗余拓扑")
    primary = _node(client, topology_id, "主库")
    standby_a = _node(client, topology_id, "备库A")
    standby_b = _node(client, topology_id, "备库B")

    created = _standby_group(
        client, topology_id, primary=primary, standbys=[standby_a, standby_b]
    ).json()

    # 删除一个备用节点：组仍然有效（还有 1 主 + 1 备）
    assert client.delete(f"{BASE}/{topology_id}/nodes/{standby_a}").status_code == 204
    remaining = client.get(f"/api/redundancy-groups/{created['id']}")
    assert remaining.status_code == 200
    assert [item["node_id"] for item in remaining.json()["members"]] == [
        primary,
        standby_b,
    ]

    # 删除主节点：组不再满足主备约束，整组被清理
    assert client.delete(f"{BASE}/{topology_id}/nodes/{primary}").status_code == 204
    assert client.get(f"/api/redundancy-groups/{created['id']}").status_code == 404
    assert client.get(f"{BASE}/{topology_id}/redundancy-groups").json() == []


def test_delete_topology_cascades_redundancy(
    client: TestClient, db_session: Session
) -> None:
    topology_id, ids = _main_pair(client, "级联删除冗余拓扑")
    _standby_group(
        client, topology_id, primary=ids["primary"], standbys=[ids["standby"]]
    )

    assert db_session.query(RedundancyGroup).count() == 1
    assert db_session.query(RedundancyMember).count() == 2

    assert client.delete(f"{BASE}/{topology_id}").status_code == 204

    db_session.expire_all()
    assert db_session.query(RedundancyGroup).count() == 0
    assert db_session.query(RedundancyMember).count() == 0
