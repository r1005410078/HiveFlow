"""
HTTP route template (DDD-safe)

Rules:
1) Do not implement business logic here.
2) Parse request DTO -> call application service -> return response DTO.
3) Dependency injection only via Depends + provider.
"""

from fastapi import APIRouter, Depends

# from interfaces.http.dependencies import SomeService, get_some_service
# from interfaces.http.schemas import SomeRequest
# from interfaces.http.mapper import to_input

router = APIRouter(prefix="/api/v1/example", tags=["example"])


# @router.post("/action")
# def do_action(
#     req: SomeRequest,
#     service: SomeService = Depends(get_some_service),
# ) -> dict:
#     data = to_input(req)
#     return service(data)
