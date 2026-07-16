from fastapi import Depends, Request
from loguru import logger

from app.controllers import base
from app.controllers.v1.base import new_router
from app.models.schema import (
    VideoScriptRequest,
    VideoScriptResponse,
    VideoSocialMetadataRequest,
    VideoSocialMetadataResponse,
    VideoTermsRequest,
    VideoTermsResponse,
)
from app.services import llm
from app.services import video_runs as video_run_service
from app.utils import utils

# authentication dependency
router = new_router(dependencies=[Depends(base.verify_token)])


def _text_length(value) -> int:
    if value is None:
        return 0
    if isinstance(value, list):
        return sum(len(str(item)) for item in value)
    if isinstance(value, dict):
        return sum(len(str(item)) for item in value.values())
    return len(str(value))


def _trace_llm_generation(
    *,
    body,
    operation: str,
    event_type: str,
    input_summary: dict,
    output_summary: dict,
    input_characters: int,
    output_characters: int,
) -> None:
    workspace_id = getattr(body, "workspace_id", None)
    if not workspace_id:
        return
    try:
        video_run_service.record_llm_generation(
            workspace_id=workspace_id,
            user_id=getattr(body, "user_id", None),
            run_id=getattr(body, "run_id", None),
            operation=operation,
            event_type=event_type,
            input_summary=input_summary,
            output_summary=output_summary,
            input_characters=input_characters,
            output_characters=output_characters,
        )
    except Exception as exc:
        logger.warning(f"failed to trace LLM generation event: {exc}")


@router.post(
    "/scripts",
    response_model=VideoScriptResponse,
    summary="Create a script for the video",
)
def generate_video_script(request: Request, body: VideoScriptRequest):
    video_script = llm.generate_script(
        video_subject=body.video_subject,
        language=body.video_language,
        paragraph_number=body.paragraph_number,
        video_script_prompt=body.video_script_prompt,
        custom_system_prompt=body.custom_system_prompt,
    )
    _trace_llm_generation(
        body=body,
        operation="script_generation",
        event_type="script_generated",
        input_summary={
            "video_subject": body.video_subject,
            "video_language": body.video_language,
            "paragraph_number": body.paragraph_number,
            "has_video_script_prompt": bool(body.video_script_prompt),
            "has_custom_system_prompt": bool(body.custom_system_prompt),
        },
        output_summary={"script_length": len(video_script)},
        input_characters=_text_length(body.video_subject)
        + _text_length(body.video_script_prompt)
        + _text_length(body.custom_system_prompt),
        output_characters=len(video_script),
    )
    response = {"video_script": video_script}
    return utils.get_response(200, response)


@router.post(
    "/terms",
    response_model=VideoTermsResponse,
    summary="Generate video terms based on the video script",
)
def generate_video_terms(request: Request, body: VideoTermsRequest):
    video_terms = llm.generate_terms(
        video_subject=body.video_subject,
        video_script=body.video_script,
        amount=body.amount,
        match_script_order=body.match_materials_to_script,
    )
    _trace_llm_generation(
        body=body,
        operation="terms_generation",
        event_type="terms_generated",
        input_summary={
            "video_subject": body.video_subject,
            "amount": body.amount,
            "match_materials_to_script": body.match_materials_to_script,
        },
        output_summary={"terms_count": len(video_terms)},
        input_characters=_text_length(body.video_subject) + _text_length(body.video_script),
        output_characters=_text_length(video_terms),
    )
    response = {"video_terms": video_terms}
    return utils.get_response(200, response)


@router.post(
    "/social-metadata",
    response_model=VideoSocialMetadataResponse,
    summary="Generate social publishing metadata",
)
def generate_video_social_metadata(
    request: Request, body: VideoSocialMetadataRequest
):
    metadata = llm.generate_social_metadata(
        video_subject=body.video_subject,
        video_script=body.video_script,
        language=body.language,
        platform=body.platform,
    )
    _trace_llm_generation(
        body=body,
        operation="social_metadata_generation",
        event_type="social_metadata_generated",
        input_summary={
            "video_subject": body.video_subject,
            "language": body.language,
            "platform": body.platform,
        },
        output_summary={
            "title_length": _text_length(metadata.get("title")),
            "caption_length": _text_length(metadata.get("caption")),
            "hashtags_count": len(metadata.get("hashtags") or []),
        },
        input_characters=_text_length(body.video_subject) + _text_length(body.video_script),
        output_characters=_text_length(metadata),
    )
    return utils.get_response(200, metadata)
