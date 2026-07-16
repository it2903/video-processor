from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.config import config
from app.models.llm_provider import DEFAULT_LLM_PROVIDER_ID, get_llm_provider
from app.models import const
from app.models.schema import TaskVideoRequest
from app.services import capabilities, supabase_domain


RUNS_TABLE = "mpt_video_runs"
EVENTS_TABLE = "mpt_generation_events"
ARTIFACTS_TABLE = "mpt_video_artifacts"
USAGE_TABLE = "mpt_usage_records"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dump_params(params: TaskVideoRequest) -> dict[str, Any]:
    return params.model_dump(mode="json", exclude_none=True)


def _safe_config_snapshot() -> dict[str, Any]:
    return {
        "llm_provider": config.app.get("llm_provider", ""),
        "video_source": config.app.get("video_source", ""),
        "subtitle_provider": config.app.get("subtitle_provider", "edge"),
        "storage_configured": supabase_domain.is_configured(),
        "providers": {
            "pexels": bool(config.app.get("pexels_api_keys")),
            "pixabay": bool(config.app.get("pixabay_api_keys")),
            "coverr": bool(config.app.get("coverr_api_keys")),
            "azure_speech": bool(
                config.azure.get("speech_key") and config.azure.get("speech_region")
            ),
            "elevenlabs": bool(config.elevenlabs.get("api_key")),
            "gemini": bool(config.app.get("gemini_api_key")),
            "mimo": bool(config.app.get("mimo_api_key")),
            "siliconflow": bool(config.siliconflow.get("api_key")),
        },
    }


def build_run_insert_payload(
    *,
    workspace_id: str,
    user_id: str,
    created_by: str,
    title: str,
    request_id: str,
    task_id: str,
    params: TaskVideoRequest,
    parent_run_id: str | None,
    run_id: str | None = None,
) -> dict[str, Any]:
    params_payload = _dump_params(params)
    payload = {
        "workspace_id": workspace_id,
        "user_id": user_id,
        "created_by": created_by,
        "parent_run_id": parent_run_id,
        "request_id": request_id,
        "mpt_task_id": task_id,
        "status": "queued",
        "title": title or params.video_subject or "Video MPT",
        "video_subject": params.video_subject,
        "video_language": params.video_language,
        "video_aspect": params_payload.get("video_aspect"),
        "video_source": params.video_source,
        "voice_name": params.voice_name,
        "bgm_type": params.bgm_type,
        "subtitle_enabled": params.subtitle_enabled,
        "request_payload": params_payload,
        "effective_params": params_payload,
        "config_snapshot": _safe_config_snapshot(),
        "capabilities_snapshot": {"version": capabilities.build_capabilities()["version"]},
        "progress": 0,
    }
    if run_id:
        payload["id"] = run_id
    return payload


def create_run_record(payload: dict[str, Any]) -> dict[str, Any]:
    row = supabase_domain.insert_row(RUNS_TABLE, payload)
    return row or payload


def record_event(
    *,
    run_id: str | None,
    workspace_id: str,
    user_id: str | None,
    event_type: str,
    event_status: str = "succeeded",
    step_name: str | None = None,
    input_summary: dict[str, Any] | None = None,
    output_summary: dict[str, Any] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return supabase_domain.insert_row(
        EVENTS_TABLE,
        {
            "run_id": run_id,
            "workspace_id": workspace_id,
            "user_id": user_id,
            "event_type": event_type,
            "event_status": event_status,
            "step_name": step_name,
            "input_summary": input_summary or {},
            "output_summary": output_summary or {},
            "error_code": error_code,
            "error_message": error_message,
            "metadata": metadata or {},
        },
    )


def _llm_provider_and_model() -> tuple[str, str]:
    provider_id = str(config.app.get("llm_provider", DEFAULT_LLM_PROVIDER_ID) or "").lower()
    provider = get_llm_provider(provider_id)
    if provider is None:
        return provider_id, ""
    configured_model = config.app.get(provider.config_key("model_name"), "")
    return provider_id, provider.resolve_model_name(configured_model)


def record_llm_generation(
    *,
    workspace_id: str | None,
    user_id: str | None,
    run_id: str | None,
    operation: str,
    event_type: str,
    input_summary: dict[str, Any],
    output_summary: dict[str, Any],
    input_characters: int,
    output_characters: int,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    workspace_id = (workspace_id or "").strip()
    user_id = (user_id or "").strip() or None
    run_id = (run_id or "").strip() or None
    if not workspace_id:
        return {}

    provider, model = _llm_provider_and_model()
    event = record_event(
        run_id=run_id,
        workspace_id=workspace_id,
        user_id=user_id,
        event_type=event_type,
        event_status="succeeded",
        input_summary=input_summary,
        output_summary=output_summary,
        metadata=metadata or {},
    )
    usage = supabase_domain.insert_row(
        USAGE_TABLE,
        {
            "run_id": run_id,
            "workspace_id": workspace_id,
            "user_id": user_id,
            "operation": operation,
            "provider": provider,
            "model": model,
            "usage_source": "estimated",
            "input_characters": max(0, input_characters),
            "output_characters": max(0, output_characters),
            "metadata": {
                **(metadata or {}),
                "note": "MPT provider response does not expose token usage yet.",
            },
        },
    )
    return {"event": event, "usage": usage}


def _status_from_task(task: dict[str, Any]) -> str:
    state = task.get("state")
    if state == const.TASK_STATE_COMPLETE:
        return "completed"
    if state == const.TASK_STATE_FAILED:
        return "failed"
    return "running"


def _terms_from_task(task: dict[str, Any]) -> list[str]:
    terms = task.get("terms") or []
    if isinstance(terms, str):
        return [item.strip() for item in terms.split(",") if item.strip()]
    if isinstance(terms, list):
        return [str(item).strip() for item in terms if str(item).strip()]
    return []


def _record_artifacts(run: dict[str, Any], task: dict[str, Any]) -> None:
    storage_results = task.get("storage_results") or []
    if not isinstance(storage_results, list):
        return

    for result in storage_results:
        if not isinstance(result, dict) or not result.get("object_path"):
            continue
        supabase_domain.upsert_row(
            ARTIFACTS_TABLE,
            {
                "run_id": run["id"],
                "workspace_id": run["workspace_id"],
                "user_id": run.get("user_id"),
                "artifact_type": "video",
                "storage_bucket": result.get("bucket") or "mpt-videos",
                "storage_path": result["object_path"],
                "original_url": result.get("url") or None,
                "file_name": result.get("object_path", "").split("/")[-1],
                "content_type": result.get("content_type"),
                "file_size_bytes": result.get("size"),
                "metadata": {
                    "source": "mpt_task_storage_results",
                    "local_path": result.get("local_path"),
                },
            },
            on_conflict="storage_bucket,storage_path",
        )


def _record_usage(run: dict[str, Any], task: dict[str, Any]) -> None:
    script = task.get("script") or ""
    terms = _terms_from_task(task)
    if not script and not terms:
        return
    supabase_domain.insert_row(
        USAGE_TABLE,
        {
            "run_id": run["id"],
            "workspace_id": run["workspace_id"],
            "user_id": run.get("user_id"),
            "operation": "video_generation",
            "provider": config.app.get("llm_provider", ""),
            "model": config.app.get(f"{config.app.get('llm_provider', '')}_model_name", ""),
            "usage_source": "estimated",
            "input_characters": len(str(run.get("video_subject") or "")),
            "output_characters": len(script),
            "metadata": {
                "terms_count": len(terms),
                "note": "MPT provider response does not expose token usage yet.",
            },
        },
    )


def sync_task_to_run(run: dict[str, Any], task: dict[str, Any] | None) -> dict[str, Any]:
    if not task:
        return run

    status = _status_from_task(task)
    terms = _terms_from_task(task)
    update_payload: dict[str, Any] = {
        "status": status,
        "progress": max(0, min(100, int(task.get("progress") or 0))),
        "generated_script": task.get("script"),
        "generated_terms": terms,
        "metadata": {
            **(run.get("metadata") if isinstance(run.get("metadata"), dict) else {}),
            "last_synced_at": _now(),
            "mpt_state": task.get("state"),
        },
    }
    if status == "completed":
        update_payload["completed_at"] = run.get("completed_at") or _now()
    if status == "failed":
        update_payload["error_message"] = task.get("error") or "MPT task failed"

    supabase_domain.update_row(RUNS_TABLE, run["id"], update_payload)

    should_record_terminal_events = run.get("status") not in {
        "completed",
        "completed_with_warnings",
        "failed",
        "cancelled",
        "deleted",
    } and status in {"completed", "failed"}
    if should_record_terminal_events:
        record_event(
            run_id=run["id"],
            workspace_id=run["workspace_id"],
            user_id=run.get("user_id"),
            event_type="video_run_completed" if status == "completed" else "video_run_failed",
            event_status="succeeded" if status == "completed" else "failed",
            output_summary={
                "progress": update_payload["progress"],
                "videos_count": len(task.get("videos") or []),
                "terms_count": len(terms),
            },
        )
        if status == "completed":
            _record_artifacts(run, task)
            _record_usage(run, task)

    return {**run, **update_payload}


def get_run(run_id: str) -> dict[str, Any] | None:
    return supabase_domain.select_row(RUNS_TABLE, run_id)


def list_runs(
    *,
    workspace_id: str,
    user_id: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    query = {
        "workspace_id": f"eq.{workspace_id}",
        "deleted_at": "is.null",
    }
    if user_id:
        query["user_id"] = f"eq.{user_id}"
    if status:
        query["status"] = f"eq.{status}"
    return supabase_domain.select_rows(
        RUNS_TABLE,
        query,
        limit=max(1, min(limit, 100)),
        order="updated_at.desc",
    )


def mark_run_deleted(run: dict[str, Any], deleted_by: str | None) -> dict[str, Any]:
    payload = {
        "status": "deleted",
        "deleted_at": _now(),
        "deleted_by": deleted_by,
    }
    updated = supabase_domain.update_row(RUNS_TABLE, run["id"], payload)
    record_event(
        run_id=run["id"],
        workspace_id=run["workspace_id"],
        user_id=run.get("user_id"),
        event_type="video_run_deleted",
        metadata={"deleted_by": deleted_by},
    )
    return updated or {**run, **payload}
