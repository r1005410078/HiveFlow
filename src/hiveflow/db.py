from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

from hiveflow.config import Settings


def get_engine(settings: Settings | None = None):
    """创建并返回数据库引擎。

    如果是 SQLite，会自动创建数据库文件所在目录。
    """
    app_settings = settings or Settings()
    if app_settings.database_url.startswith("sqlite:///"):
        db_file = Path(app_settings.database_url.removeprefix("sqlite:///"))
        db_file.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(app_settings.database_url, echo=False)


def create_all_tables(settings: Settings | None = None) -> None:
    """按当前 SQLModel 元数据创建所有数据表。"""
    engine = get_engine(settings)
    SQLModel.metadata.create_all(engine)
    _run_lightweight_migrations(engine)


def _run_lightweight_migrations(engine) -> None:
    """执行轻量迁移，确保旧库可兼容新增字段。"""
    if not engine.url.drivername.startswith("sqlite"):
        return

    with engine.begin() as conn:
        tables = {row[0] for row in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "strategy" not in tables:
            return
        columns = conn.exec_driver_sql("PRAGMA table_info('strategy')").fetchall()
        column_names = {row[1] for row in columns}
        if "dimension" not in column_names:
            conn.exec_driver_sql("ALTER TABLE strategy ADD COLUMN dimension VARCHAR")


@contextmanager
def get_session(settings: Settings | None = None) -> Iterator[Session]:
    """提供数据库会话上下文，调用方在 with 语句中使用。"""
    engine = get_engine(settings)
    with Session(engine) as session:
        yield session
