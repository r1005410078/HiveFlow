from fastapi import APIRouter, Depends
from interfaces.http.dependencies import DailyRunService, get_daily_run_service
from interfaces.http.mapper import to_daily_input
from interfaces.http.schemas import DailyRunRequest, DailyRunResponse

router = APIRouter(prefix="/api/v1/pipeline", tags=["pipeline"])


@router.post("/daily")
def post_daily(
    req: DailyRunRequest,
    service: DailyRunService = Depends(get_daily_run_service),
) -> DailyRunResponse:
    data = to_daily_input(req)
    return DailyRunResponse.model_validate(service(data["as_of"]))
