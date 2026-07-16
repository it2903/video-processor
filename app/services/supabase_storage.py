import mimetypes
import os
from pathlib import Path
from urllib.parse import quote

import requests
from loguru import logger

from app.config import config


class SupabaseStorageError(RuntimeError):
    pass


CANONICAL_VIDEO_BUCKET = "mpt-videos"


def _clean_url(value: str) -> str:
    return (value or "").strip().rstrip("/")


def storage_bucket() -> str:
    configured_bucket = str(config.app.get("supabase_storage_bucket") or "").strip()
    if configured_bucket and configured_bucket != CANONICAL_VIDEO_BUCKET:
        logger.warning(
            "ignoring non-canonical MPT video storage bucket: "
            f"{configured_bucket}; using {CANONICAL_VIDEO_BUCKET}"
        )
    return CANONICAL_VIDEO_BUCKET


def _is_public_bucket() -> bool:
    return bool(config.app.get("supabase_storage_public", False))


def is_configured() -> bool:
    return bool(
        _clean_url(config.app.get("supabase_url", ""))
        and config.app.get("supabase_service_role_key", "")
        and storage_bucket()
    )


def _object_url(object_path: str) -> str:
    if not _is_public_bucket():
        return ""

    bucket = storage_bucket()
    custom_base_url = _clean_url(config.app.get("supabase_public_url_base", ""))
    encoded_path = quote(object_path, safe="/")

    if custom_base_url:
        return f"{custom_base_url}/{encoded_path}"

    supabase_url = _clean_url(config.app.get("supabase_url", ""))
    return f"{supabase_url}/storage/v1/object/public/{bucket}/{encoded_path}"


def create_signed_url(object_path: str, expires_in: int = 3600) -> str:
    if not is_configured() or not object_path:
        return ""

    supabase_url = _clean_url(config.app.get("supabase_url", ""))
    service_role_key = config.app.get("supabase_service_role_key", "")
    bucket = storage_bucket()
    encoded_path = quote(object_path, safe="/")
    sign_url = f"{supabase_url}/storage/v1/object/sign/{bucket}/{encoded_path}"
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(
            sign_url,
            headers=headers,
            json={"expiresIn": max(60, min(24 * 60 * 60, int(expires_in or 3600)))},
            timeout=(10, 30),
        )
    except requests.RequestException as exc:
        logger.warning(f"failed to create Supabase signed URL: {exc}")
        return ""

    if response.status_code not in {200, 201}:
        logger.warning(
            "failed to create Supabase signed URL: "
            f"status={response.status_code}, body={response.text[:300]}"
        )
        return ""

    try:
        payload = response.json()
    except ValueError:
        return ""

    signed_url = str(payload.get("signedURL") or payload.get("signed_url") or "")
    if not signed_url:
        return ""
    if signed_url.startswith("http://") or signed_url.startswith("https://"):
        return signed_url
    if not signed_url.startswith("/"):
        signed_url = f"/{signed_url}"
    return f"{supabase_url}{signed_url}"


def upload_file(local_path: str, object_path: str) -> dict:
    if not is_configured():
        return {}

    if not os.path.isfile(local_path):
        raise SupabaseStorageError(f"file does not exist: {local_path}")

    supabase_url = _clean_url(config.app.get("supabase_url", ""))
    service_role_key = config.app.get("supabase_service_role_key", "")
    bucket = storage_bucket()
    encoded_path = quote(object_path, safe="/")
    upload_url = f"{supabase_url}/storage/v1/object/{bucket}/{encoded_path}"
    content_type = mimetypes.guess_type(local_path)[0] or "application/octet-stream"
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": content_type,
        "x-upsert": "true",
    }

    with open(local_path, "rb") as file_obj:
        response = requests.post(
            upload_url,
            headers=headers,
            data=file_obj,
            timeout=(15, 300),
        )

    if response.status_code not in {200, 201}:
        raise SupabaseStorageError(
            f"upload failed with status {response.status_code}: {response.text[:300]}"
        )

    return {
        "bucket": bucket,
        "object_path": object_path,
        "url": _object_url(object_path),
        "size": os.path.getsize(local_path),
        "content_type": content_type,
    }


def _task_video_object_path(
    task_id: str,
    filename: str,
    workspace_id: str | None = None,
    user_id: str | None = None,
    run_id: str | None = None,
) -> str:
    if workspace_id and run_id:
        owner_segment = user_id or "system"
        return f"{workspace_id}/{owner_segment}/{run_id}/videos/{filename}"
    return f"tasks/{task_id}/{filename}"


def upload_task_videos(
    task_id: str,
    video_paths: list[str],
    workspace_id: str | None = None,
    user_id: str | None = None,
    run_id: str | None = None,
) -> list[dict]:
    if not is_configured():
        return []

    uploads = []
    for video_path in video_paths:
        filename = Path(video_path).name
        object_path = _task_video_object_path(
            task_id,
            filename,
            workspace_id=workspace_id,
            user_id=user_id,
            run_id=run_id,
        )
        try:
            result = upload_file(video_path, object_path)
            if result:
                uploads.append({**result, "local_path": video_path})
                logger.info(
                    "uploaded generated video to Supabase Storage: "
                    f"task_id={task_id}, object_path={object_path}"
                )
        except SupabaseStorageError as exc:
            logger.warning(
                "failed to upload generated video to Supabase Storage: "
                f"task_id={task_id}, local_path={video_path}, error={str(exc)}"
            )
    return uploads
