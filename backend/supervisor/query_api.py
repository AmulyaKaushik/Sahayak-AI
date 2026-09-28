from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from supervisor.agent import PipelineError, QueryResponse, run_query_pipeline

router = APIRouter(prefix="/api/v1", tags=["query"])


class QueryRequest(BaseModel):
    customer_id: str
    session_id: str
    text: str
    extra_fields: dict = {}


@router.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    try:
        return await run_query_pipeline(
            request.customer_id, request.session_id, request.text, request.extra_fields
        )
    except PipelineError as exc:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": exc.code, "message": exc.message}},
        )
