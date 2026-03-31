from interfaces.http.schemas import DailyRunRequest


def to_daily_input(req: DailyRunRequest) -> dict:
    return {"as_of": req.as_of}
