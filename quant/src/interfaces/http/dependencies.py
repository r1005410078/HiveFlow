from collections.abc import Callable

from application.daily_run_service import run_daily


DailyRunService = Callable[[str], dict]


def get_daily_run_service() -> DailyRunService:
    # Provider only: wire application service into FastAPI dependency graph.
    return lambda as_of: run_daily(as_of=as_of, root=None)
