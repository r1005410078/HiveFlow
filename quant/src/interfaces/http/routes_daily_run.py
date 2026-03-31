from fastapi import APIRouter

from application.daily_run_service import run_daily
from interfaces.http.mapper import to_daily_input
from interfaces.http.schemas import DailyRunRequest

router = APIRouter(prefix="/api/v1/pipeline", tags=["pipeline"])


@router.post("/daily")
def post_daily(req: DailyRunRequest) -> dict:
    data = to_daily_input(req)
    return run_daily(as_of=data["as_of"], root=None)
