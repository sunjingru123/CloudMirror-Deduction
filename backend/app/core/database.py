"""数据库连接与 SQLAlchemy 基础初始化。

当前仅提供引擎、会话工厂和声明式基类，尚未定义具体业务表。
"""

from collections.abc import Generator

from sqlalchemy import create_engine
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

    目前没有任何业务模型，因此仅创建空的基础结构；后续新增模型后
    会自动在此注册建表。
    """
    # 导入模型以便注册到 Base.metadata（当前为空）
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
