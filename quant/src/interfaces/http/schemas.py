from pydantic import BaseModel


class DailyRunRequest(BaseModel):
    as_of: str
