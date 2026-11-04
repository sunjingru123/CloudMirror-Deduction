"""pytest 全局配置。

注意：必须在导入应用模块之前设置 `DATABASE_URL`，使测试使用独立的数据库文件，
避免污染开发数据库。
"""

import os
from pathlib import Path

_TEST_DB_NAME = "_test_cloudmirror.db"
os.environ["DATABASE_URL"] = f"sqlite:///./{_TEST_DB_NAME}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_database():
    """每个测试前重建表结构，保证测试相互独立。"""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture()
def client(_reset_database):
    """在应用生命周期内提供测试客户端。"""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_session():
    """提供直接访问数据库的会话，用于验证数据是否真正持久化。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_database():
    """全部测试结束后释放连接并删除测试数据库文件。"""
    yield
    engine.dispose()
    for suffix in ("", "-journal", "-wal", "-shm"):
        Path(f"{_TEST_DB_NAME}{suffix}").unlink(missing_ok=True)
