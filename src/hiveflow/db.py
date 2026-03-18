from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

from hiveflow.config import Settings
from hiveflow.domain.grid_positions import GridPosition  # noqa: F401
from hiveflow.domain.strategy_runs import StrategyRun  # noqa: F401
# StrategyRun: SQLModel.metadata.create_all 在首次运行时自动建表，无需迁移分支


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
        tables = {row[0] for row in conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}

        # strategy 表：dimension 列
        if "strategy" in tables:
            columns = conn.exec_driver_sql("PRAGMA table_info('strategy')").fetchall()
            column_names = {row[1] for row in columns}
            if "dimension" not in column_names:
                conn.exec_driver_sql("ALTER TABLE strategy ADD COLUMN dimension VARCHAR")

        # backtestresult 表：weights_snapshot 列（独立于 strategy 表检查）
        if "backtestresult" in tables:
            bt_cols = conn.exec_driver_sql("PRAGMA table_info('backtestresult')").fetchall()
            # bt_col_names 是一次性快照；各 ALTER 检查相互独立，
            # 每条检查不依赖同次迁移中前一条 ALTER 新增的列。
            bt_col_names = {row[1] for row in bt_cols}
            if "weights_snapshot" not in bt_col_names:
                conn.exec_driver_sql(
                    "ALTER TABLE backtestresult ADD COLUMN weights_snapshot TEXT"
                )
            if "backtest_type" not in bt_col_names:
                conn.exec_driver_sql(
                    "ALTER TABLE backtestresult ADD COLUMN backtest_type VARCHAR DEFAULT 'static'"
                )
            if "equity_curve" not in bt_col_names:
                conn.exec_driver_sql(
                    "ALTER TABLE backtestresult ADD COLUMN equity_curve TEXT"
                )

        # gridposition 表：inst_type 列
        if "gridposition" in tables:
            gp_cols = conn.exec_driver_sql("PRAGMA table_info('gridposition')").fetchall()
            gp_col_names = {row[1] for row in gp_cols}
            if "inst_type" not in gp_col_names:
                conn.exec_driver_sql(
                    "ALTER TABLE gridposition ADD COLUMN inst_type VARCHAR DEFAULT 'SPOT'"
                )


@contextmanager
def get_session(settings: Settings | None = None) -> Iterator[Session]:
    """提供数据库会话上下文，调用方在 with 语句中使用。"""
    engine = get_engine(settings)
    with Session(engine) as session:
        yield session
