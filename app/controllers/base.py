from uuid import uuid4
import secrets

from fastapi import Request

from app.config import config
from app.models.exception import HttpException


def get_task_id(request: Request):
    task_id = request.headers.get("x-task-id")
    if not task_id:
        task_id = uuid4()
    return str(task_id)


def get_api_key(request: Request):
    api_key = request.headers.get("x-api-key")
    return api_key


def verify_token(request: Request):
    expected_token = str(config.app.get("api_key", "") or "").strip()
    if not expected_token:
        if config.app.get("require_api_key", False):
            request_id = get_task_id(request)
            raise HttpException(
                task_id=request_id,
                status_code=503,
                message="api key is required but MPT_API_KEY is not configured",
            )
        return

    token = get_api_key(request)
    if not token or not secrets.compare_digest(str(token), expected_token):
        request_id = get_task_id(request)
        request_url = request.url
        user_agent = request.headers.get("user-agent")
        raise HttpException(
            task_id=request_id,
            status_code=401,
            message=f"invalid api key: {request_url}, {user_agent}",
        )
