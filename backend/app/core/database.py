"""数据库连接与 SQLAlchemy 基础初始化。

当前仅提供引擎、会话工厂和声明式基类，尚未定义具体业务表。
"""

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# SQLite 需要关闭同线程检查，方可配合 FastAPI 的线程池使用
_connect_args = (
    {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args,
    echo=False,
    future=True,
)


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:  # noqa: ARG001
    """为 SQLite 连接开启外键约束，使 ON DELETE CASCADE 生效。

    其他数据库默认已开启外键约束，此处仅对 SQLite 生效。
    """
    if not settings.DATABASE_URL.startswith("sqlite"):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """所有 ORM 模型的声明式基类。"""


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：提供数据库会话并在请求结束后关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """创建数据库表结构。

    使用 `create_all`，该操作幂等：已存在的表不会被修改，也不会清空数据，
    因此可以重复执行。
    """
    # 导入模型以便注册到 Base.metadata
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
