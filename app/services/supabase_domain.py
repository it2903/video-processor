from __future__ import annotations

from typing import Any
from urllib.parse import quote

import requests
from loguru import logger

from app.config import config


class SupabaseDomainError(RuntimeError):
    pass


def _clean_url(value: str) -> str:
    return (value or "").strip().rstrip("/")


def is_configured() -> bool:
    return bool(
        _clean_url(config.app.get("supabase_url", ""))
        and config.app.get("supabase_service_role_key", "")
    )


def _rest_url(table: str) -> str:
    supabase_url = _clean_url(config.app.get("supabase_url", ""))
    return f"{supabase_url}/rest/v1/{quote(table, safe='')}"


def _headers(prefer: str = "return=representation") -> dict[str, str]:
    service_role_key = config.app.get("supabase_service_role_key", "")
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _decode_response(response: requests.Response) -> Any:
    if response.status_code >= 400:
        raise SupabaseDomainError(
            f"Supabase REST request failed with status {response.status_code}: "
            f"{response.text[:300]}"
        )
    if not response.text:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def _request(
    method: str,
    table: str,
    *,
    params: dict[str, str] | None = None,
    json: dict[str, Any] | None = None,
    prefer: str = "return=representation",
) -> Any:
    if not is_configured():
        return None

    response = requests.request(
        method,
        _rest_url(table),
        headers=_headers(prefer),
        params=params or {},
        json=json,
        timeout=(10, 30),
    )
    return _decode_response(response)


def _first_row(payload: Any) -> dict[str, Any]:
    if isinstance(payload, list):
        return payload[0] if payload and isinstance(payload[0], dict) else {}
    return payload if isinstance(payload, dict) else {}


def insert_row(table: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return _first_row(_request("POST", table, json=payload))
    except SupabaseDomainError as exc:
        logger.warning(f"failed to insert Supabase row: table={table}, error={exc}")
        return {}


def upsert_row(
    table: str,
    payload: dict[str, Any],
    *,
    on_conflict: str,
) -> dict[str, Any]:
    try:
        return _first_row(
            _request(
                "POST",
                table,
                params={"on_conflict": on_conflict},
                json=payload,
                prefer="resolution=merge-duplicates,return=representation",
            )
        )
    except SupabaseDomainError as exc:
        logger.warning(f"failed to upsert Supabase row: table={table}, error={exc}")
        return {}


def update_row(table: str, row_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return _first_row(
            _request("PATCH", table, params={"id": f"eq.{row_id}"}, json=payload)
        )
    except SupabaseDomainError as exc:
        logger.warning(
            f"failed to update Supabase row: table={table}, id={row_id}, error={exc}"
        )
        return {}


def select_rows(
    table: str,
    query: dict[str, str] | None = None,
    *,
    limit: int | None = None,
    order: str | None = None,
) -> list[dict[str, Any]]:
    params = {"select": "*"}
    if query:
        params.update(query)
    if limit is not None:
        params["limit"] = str(limit)
    if order:
        params["order"] = order

    try:
        payload = _request("GET", table, params=params, prefer="")
    except SupabaseDomainError as exc:
        logger.warning(f"failed to select Supabase rows: table={table}, error={exc}")
        return []
    return payload if isinstance(payload, list) else []


def select_row(table: str, row_id: str) -> dict[str, Any] | None:
    rows = select_rows(table, {"id": f"eq.{row_id}"}, limit=1)
    return rows[0] if rows else None
