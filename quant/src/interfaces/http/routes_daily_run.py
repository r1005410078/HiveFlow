from fastapi import APIRouter, Depends
from interfaces.http.dependencies import DailyRunService, get_daily_run_service
from interfaces.http.mapper import to_daily_input
from interfaces.http.schemas import DailyRunRequest

router = APIRouter(prefix="/api/v1/pipeline", tags=["pipeline"])


@router.post("/daily")
def post_daily(
    req: DailyRunRequest,
    service: DailyRunService = Depends(get_daily_run_service),
) -> dict:
    data = to_daily_input(req)
    return service(data["as_of"])
