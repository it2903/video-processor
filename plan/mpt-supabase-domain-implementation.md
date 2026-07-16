# MPT Supabase Domain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make MPT expose generic `/api/v1/*` video-generation domain endpoints that own Supabase persistence, capabilities, history, artifacts, and trace events.

**Architecture:** Keep the existing low-level MPT endpoints (`/videos`, `/tasks`, `/scripts`, `/terms`) intact. Add a thin domain layer that uses the existing task manager/rendering engine, then records canonical history in Supabase tables owned by MPT. Blast remains a caller through a proxy and does not own MPT history.

**Tech Stack:** FastAPI, Pydantic, requests-based Supabase REST/Storage calls, existing MPT task manager, pytest.

## Global Constraints

- New endpoints must stay under `/api/v1/*`; no customer-specific path segment.
- MPT owns writes to `mpt_*` tables and `mpt-videos` storage with server-side Supabase credentials.
- Browser/frontends must not receive or submit provider secrets.
- Existing `/api/v1/videos`, `/api/v1/tasks`, `/api/v1/scripts`, `/api/v1/terms` behavior must remain compatible.
- If Supabase is not configured, rendering endpoints should still work but domain endpoints must report persistence as unavailable or degraded clearly.

---

### Task 1: Supabase Domain Client

**Files:**
- Create: `app/services/supabase_domain.py`
- Test: `test/services/test_supabase_domain.py`

**Interfaces:**
- Produces: `is_configured() -> bool`, `insert_row(table, payload) -> dict`, `update_row(table, row_id, payload) -> dict`, `select_rows(table, query) -> list[dict]`, `select_row(table, row_id) -> dict | None`.

- [x] Write failing tests for URL/header construction and disabled behavior.
- [x] Implement requests-based PostgREST client using `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`.
- [x] Run the focused test file.

### Task 2: Capabilities Catalog

**Files:**
- Create: `app/services/capabilities.py`
- Modify: `app/controllers/v1/video.py`
- Test: `test/services/test_capabilities.py`

**Interfaces:**
- Produces: `build_capabilities() -> dict`.

- [x] Write failing tests for fonts, slider ranges, transitions, sources, music files, and voice providers.
- [x] Implement catalog from existing config, resource folders, voice helpers, and BGM helper.
- [x] Expose `GET /api/v1/capabilities`.

### Task 3: Video Run Domain

**Files:**
- Create: `app/services/video_runs.py`
- Modify: `app/controllers/v1/video.py`
- Test: `test/services/test_video_runs.py`

**Interfaces:**
- Produces: `create_video_run(request, params) -> dict`, `get_video_run(run_id) -> dict`, `list_video_runs(workspace_id, user_id, limit, status) -> dict`, `sync_task_to_run(run_id, task_payload) -> dict`.

- [x] Write failing tests for run creation payload, workspace/user scope, event insertion, and completed artifact sync.
- [x] Implement run creation by creating MPT task and inserting `mpt_video_runs` + `mpt_generation_events`.
- [x] Implement polling sync that reads task state, updates the run, inserts artifact rows and usage/event rows when available.
- [x] Expose `POST /api/v1/video-runs`, `GET /api/v1/video-runs`, `GET /api/v1/video-runs/{run_id}`, `POST /api/v1/video-runs/{run_id}/rerun`, `DELETE /api/v1/video-runs/{run_id}`.

### Task 4: Verification and Deploy Prep

**Files:**
- Modify docs/env if variable names change.

- [ ] Run focused pytest suite.
- [ ] Run import/type smoke for FastAPI app.
- [ ] Commit on `production`.
- [ ] Push `production`.
- [ ] Deploy through Railway or confirm push-triggered deployment.
