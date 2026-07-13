---
goal: Harden and deploy the MoneyPrinterTurbo backend-only API
version: 1.0
date_created: 2026-07-13
last_updated: 2026-07-13
owner: theshortylz
status: 'In progress'
tags: [infrastructure, security, deployment, docker, supabase, redis]
---

# Introduction

![Status: In progress](https://img.shields.io/badge/status-In%20progress-yellow)

This plan makes the forked `theshortylz/video-processor` repository safe and practical to deploy as a backend-only video generation API. The target runtime is a Docker-capable free host such as Hugging Face Spaces, with Redis for task state and Supabase Storage for durable generated outputs. Vercel is not used for the FFmpeg worker because this application writes media files, performs CPU-heavy video processing, and can exceed serverless scratch/duration limits.

## 1. Requirements & Constraints

- **REQ-001**: The deployed service must expose only the FastAPI backend, not the Streamlit WebUI.
- **REQ-002**: Runtime secrets must be loaded from environment variables and never committed in `config.toml`.
- **REQ-003**: All `/api/v1` endpoints must require an `x-api-key` header when `MPT_API_KEY` or `app.api_key` is configured.
- **REQ-003A**: Docker/public deployments must reject protected API requests when API auth is required but no API key is configured.
- **REQ-004**: The backend must support Redis via a single `REDIS_URL` environment variable and existing host/port/password config.
- **REQ-004A**: Invalid `REDIS_URL` values must not crash application import; accepted schemes are `redis://`, `rediss://`, and `unix://`.
- **REQ-005**: The backend must support Supabase Storage configuration through environment variables for future persistent media upload.
- **REQ-006**: Docker deployment must bind to `0.0.0.0` and use the platform-provided `PORT` when present.
- **REQ-007**: The repository must include deployment documentation for Hugging Face Spaces Docker.
- **SEC-001**: Public API deployments must fail closed when authentication is enabled and requests omit or provide an incorrect `x-api-key`.
- **SEC-002**: Secrets must not be logged, committed, embedded in images, or written to example files with real values.
- **SEC-003**: CORS must be explicitly configurable with `CORS_ALLOWED_ORIGINS`; wildcard is acceptable only for local development.
- **CON-001**: Free hosting storage is ephemeral unless an external storage service is used.
- **CON-002**: Supabase free storage is limited and must be treated as a small-output prototype tier.
- **CON-003**: Redis must not be exposed to untrusted writers.
- **GUD-001**: Preserve upstream project structure and minimize invasive changes.
- **PAT-001**: Follow the existing `app.config.config` centralized runtime configuration pattern.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Add a backend-only deployment surface without changing existing local WebUI behavior.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Replace the root `Dockerfile` with a backend-only FastAPI image that installs `ffmpeg`, installs `requirements.txt`, copies the repo, exposes `8080`, and runs `python main.py` with `PORT` support. Preserve the prior WebUI image as `Dockerfile.webui`. | ✅ | 2026-07-13 |
| TASK-002 | Add `.dockerignore` excluding `.git`, `.venv`, `storage`, `models`, logs, caches, and local config files. | ✅ | 2026-07-13 |
| TASK-003 | Add `.env.example` with placeholder variables for `MPT_API_KEY`, LLM provider keys, material provider keys, Redis, Supabase, CORS, and API port. | ✅ | 2026-07-13 |

### Implementation Phase 2

- GOAL-002: Harden runtime configuration for public deployment.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-004 | Update `app/config/config.py` to read `PORT`, `MPT_API_KEY`, `MPT_APP_*`, `REDIS_URL`, `SUPABASE_*`, provider API key environment variables, and list-style material keys. | ✅ | 2026-07-13 |
| TASK-005 | Add `api_key = ""` under `[app]` in `config.example.toml` and document the matching `MPT_API_KEY` environment variable. | ✅ | 2026-07-13 |
| TASK-006 | Enable `Depends(base.verify_token)` on `app/controllers/v1/video.py` and `app/controllers/v1/llm.py`. | ✅ | 2026-07-13 |
| TASK-007 | Update `app/controllers/base.py` so authentication is disabled only when no API key is configured, and returns 401 for missing or invalid `x-api-key`. | ✅ | 2026-07-13 |
| TASK-007A | Add `MPT_REQUIRE_API_KEY` and set it by default in the backend Docker image so public deployments fail closed when `MPT_API_KEY` is missing. | ✅ | 2026-07-13 |

### Implementation Phase 3

- GOAL-003: Prepare external state and durable media integration boundaries.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-008 | Update Redis configuration in `app/controllers/v1/video.py` to prefer `config.app["redis_url"]` when present and fall back to existing host/port/password fields. | ✅ | 2026-07-13 |
| TASK-009 | Update Redis state configuration in `app/services/state.py` to prefer `config.app["redis_url"]` when present and fall back to existing host/port/password fields. | ✅ | 2026-07-13 |
| TASK-009A | Validate `REDIS_URL` scheme before auto-enabling Redis so malformed env values do not crash application import. | ✅ | 2026-07-13 |
| TASK-010 | Add `app/services/supabase_storage.py` with optional helper functions controlled by `supabase_url`, `supabase_service_role_key`, and `supabase_storage_bucket`. | ✅ | 2026-07-13 |
| TASK-011 | Integrate successful final video uploads in `app/services/task.py` only when Supabase Storage is fully configured; preserve existing local file URLs when it is not configured. | ✅ | 2026-07-13 |

### Implementation Phase 4

- GOAL-004: Document and verify the deployment workflow.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-012 | Add `docs/deployment/backend-only.md` with setup steps for GitHub fork, Hugging Face Space Docker, required secrets, CORS, Redis, Supabase, API testing, and security notes. | ✅ | 2026-07-13 |
| TASK-013 | Verify OpenAPI generation succeeds with `uv run python -c "from app.asgi import app; app.openapi()"`. | ✅ | 2026-07-13 |
| TASK-014 | Verify authentication rejects unauthenticated `/api/v1/tasks` requests and accepts requests with the configured `x-api-key`. | ✅ | 2026-07-13 |
| TASK-015 | Verify Dockerfile syntax and, if local Docker is available, build the backend image with `docker build -t video-processor-api .`. | Blocked: Docker daemon unavailable locally | 2026-07-13 |

## 3. Alternatives

- **ALT-001**: Deploy on Vercel Functions. Rejected for the primary worker because FFmpeg media generation relies on writable disk and long-running CPU work; Vercel is better suited as a frontend or lightweight proxy for this system.
- **ALT-002**: Deploy on Render free web service. Rejected as the first recommendation because free instances typically sleep and have lower RAM than Hugging Face Spaces CPU Basic for media workloads.
- **ALT-003**: Keep only local filesystem output. Rejected for deployed use because free Docker hosts use ephemeral storage and generated videos would disappear after restarts.

## 4. Dependencies

- **DEP-001**: Python 3.11 runtime and existing `requirements.txt`.
- **DEP-002**: FFmpeg installed in the deployment image.
- **DEP-003**: Redis-compatible TCP URL such as Upstash Redis or another managed Redis service.
- **DEP-004**: Supabase project with a Storage bucket and service role key for server-side uploads.
- **DEP-005**: Hugging Face Spaces Docker runtime or another Docker-capable host.

## 5. Files

- **FILE-001**: `Dockerfile` backend-only container definition and `Dockerfile.webui` preserved WebUI container definition.
- **FILE-002**: `.dockerignore` deployment build context exclusions.
- **FILE-003**: `.env.example` placeholder environment variables.
- **FILE-004**: `config.example.toml` safe config documentation.
- **FILE-005**: `app/config/config.py` runtime env var mapping.
- **FILE-006**: `app/controllers/base.py` API key auth behavior.
- **FILE-007**: `app/controllers/v1/video.py` protected video endpoints and Redis URL support.
- **FILE-008**: `app/controllers/v1/llm.py` protected LLM endpoints.
- **FILE-009**: `app/services/state.py` Redis URL support for task state.
- **FILE-010**: `app/services/supabase_storage.py` optional Supabase Storage helper.
- **FILE-011**: `app/services/task.py` optional final-video upload integration.
- **FILE-012**: `docs/deployment/backend-only.md` deployment instructions.

## 6. Testing

- **TEST-001**: Run `uv run python -c "from app.asgi import app; print(len(app.openapi()['paths']))"` and confirm it exits with status 0.
- **TEST-002**: Start the API locally with `MPT_API_KEY=test-key uv run python main.py` and confirm `GET /api/v1/tasks` returns 401 without `x-api-key`.
- **TEST-003**: Confirm `GET /api/v1/tasks` returns 200 with `x-api-key: test-key`.
- **TEST-004**: Run `uv run python -m compileall app` and confirm it exits with status 0.
- **TEST-005**: Run `docker build -t video-processor-api .` when Docker is available and confirm it exits with status 0.

## 7. Risks & Assumptions

- **RISK-001**: Free hosting may sleep, restart, or evict workloads; Redis and Supabase reduce data loss but do not guarantee uninterrupted long-running tasks.
- **RISK-002**: Generated videos may exceed Supabase free tier storage, upload, or egress limits.
- **RISK-003**: API misuse can create LLM, TTS, or stock-footage API costs if `MPT_API_KEY` is weak or leaked.
- **RISK-004**: Default bundled music may have copyright risk; deployed workflows should use uploaded/licensed music or disable random background music.
- **ASSUMPTION-001**: The first production target is Hugging Face Spaces Docker.
- **ASSUMPTION-002**: The frontend in `blast-financial-insights` will call this backend with a server-side API key or protected proxy, not expose the backend API key directly in browser code.

## 8. Related Specifications / Further Reading

- Hugging Face Spaces overview: https://huggingface.co/docs/hub/en/spaces-overview
- Hugging Face Docker Spaces: https://huggingface.co/docs/hub/en/spaces-sdks-docker
- Hugging Face Space secrets: https://huggingface.co/docs/huggingface_hub/en/guides/manage-spaces
- Vercel Functions runtimes and filesystem: https://vercel.com/docs/functions/runtimes
- Upstash Redis pricing: https://upstash.com/pricing/redis
- Supabase pricing: https://supabase.com/pricing
