# Backend-only deployment

This repository is prepared to deploy the FastAPI backend without the Streamlit
WebUI. The root `Dockerfile` runs `python main.py` and exposes port `8080`.
The previous WebUI image is preserved in `Dockerfile.webui`.

## Recommended free target

Use Hugging Face Spaces with the Docker SDK for the video worker. Docker Spaces
support custom FastAPI containers, runtime secrets, and an `app_port` setting.
Free Spaces use ephemeral disk, so generated files must be persisted externally
if they need to survive restarts.

Do not use Vercel Functions as the primary video worker. This backend writes
media files, runs FFmpeg, and can process for longer than small serverless
scratch/duration limits allow. Vercel is a better fit for the frontend or for a
small proxy that calls this backend.

## Required services

- A fork of this repository.
- A Hugging Face account and a Docker Space.
- Redis for task queue/state. Upstash Redis works for prototypes.
- Supabase Storage for generated video persistence.
- At least one LLM provider API key.
- A stock material provider key, unless requests use `video_source = "local"`.

## Hugging Face Space setup

Create a new Space:

- SDK: Docker
- Visibility: private while testing
- Port: `8080`
- Hardware: `cpu-basic` to start

The Space `README.md` front matter should include:

```yaml
---
title: video-processor-api
sdk: docker
app_port: 8080
suggested_hardware: cpu-basic
---
```

Push this repository to the Space git remote, or mirror the same source there.
Hugging Face Docker Spaces use the root `Dockerfile`, so no extra Dockerfile
rename is required.

## GitHub Actions sync

The `production` branch includes `.github/workflows/sync-huggingface-space.yml`.
It syncs every push from GitHub to a private Hugging Face Docker Space.

Create these in the GitHub repository settings:

- Repository secret: `HF_TOKEN`
- Repository variable: `HF_SPACE_ID`

`HF_TOKEN` must be a Hugging Face access token with permission to write to the
target Space. `HF_SPACE_ID` must use the `username/space-name` format, for
example:

```text
theshortylz/video-processor-api
```

After those values exist, rerun the workflow from GitHub Actions or push a new
commit to `production`.

## Runtime secrets and variables

Set these as Space secrets or environment variables. Never commit real values to
`.env`, `.env.example`, `config.toml`, or Dockerfiles.

Required:

```text
MPT_REQUIRE_API_KEY=true
MPT_API_KEY=<long-random-server-secret>
CORS_ALLOWED_ORIGINS=https://your-frontend-domain.example
MPT_ENDPOINT=https://your-space-subdomain.hf.space
MPT_LLM_PROVIDER=openai
OPENAI_API_KEY=<provider-key>
REDIS_URL=<redis://... or rediss://...>
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<server-side-service-role-key>
SUPABASE_STORAGE_BUCKET=generated-videos
```

The backend Docker image already sets `MPT_REQUIRE_API_KEY=true`. If
`MPT_API_KEY` is missing, protected API routes fail closed instead of becoming
public.

Optional stock material keys:

```text
PEXELS_API_KEYS=<key-1,key-2>
PIXABAY_API_KEYS=<key-1,key-2>
COVERR_API_KEYS=<key-1,key-2>
```

Optional direct public video links:

```text
SUPABASE_STORAGE_PUBLIC=true
SUPABASE_PUBLIC_URL_BASE=
```

Set `SUPABASE_STORAGE_PUBLIC=true` only when the bucket is intentionally public.
If it remains false, videos are still uploaded to Supabase, but task responses
keep local API paths instead of direct public Supabase URLs.

## Supabase Storage

Create a bucket named `generated-videos`, or change
`SUPABASE_STORAGE_BUCKET`. Use the service role key only on the backend. Do not
send it to the browser or to the frontend bundle.

For a simple prototype, a public bucket gives direct video URLs. For private
outputs, keep `SUPABASE_STORAGE_PUBLIC=false` and add a trusted server-side
download/signing endpoint before exposing files to end users.

## Frontend integration

The browser frontend must not contain `MPT_API_KEY`. Use one of these patterns:

- Preferred: call this backend through a server-side route in
  `blast-financial-insights` that injects `x-api-key`.
- Acceptable for internal tools: store `MPT_API_KEY` in a secure backend-only
  runtime variable and proxy all calls.
- Do not call the backend directly from browser code with `x-api-key` embedded.

Every protected API request must include:

```http
x-api-key: <MPT_API_KEY>
```

## Local verification

Install dependencies:

```shell
uv sync --frozen
```

Start the backend with auth enabled:

```shell
MPT_REQUIRE_API_KEY=true MPT_API_KEY=test-key MPT_LISTEN_PORT=18080 uv run python main.py
```

Unauthenticated requests must fail:

```shell
curl -i http://127.0.0.1:18080/api/v1/tasks
```

Authenticated requests must work:

```shell
curl -i -H 'x-api-key: test-key' http://127.0.0.1:18080/api/v1/tasks
```

OpenAPI should load at:

```text
http://127.0.0.1:18080/docs
```

Build the backend image:

```shell
docker build -t video-processor-api .
```

Run it locally:

```shell
docker run --rm -p 18080:8080 \
  -e MPT_API_KEY=test-key \
  -e MPT_REQUIRE_API_KEY=true \
  -e CORS_ALLOWED_ORIGINS=http://localhost:3000 \
  video-processor-api
```

## Security checklist

- Keep the Hugging Face Space private until auth, CORS, Redis, and Supabase are
  verified.
- Keep `MPT_REQUIRE_API_KEY=true` for public deployments.
- Use a long random `MPT_API_KEY` and rotate it if it is ever exposed.
- Do not expose Redis publicly.
- Do not expose Supabase service role keys to browser code.
- Set `CORS_ALLOWED_ORIGINS` to the production frontend domain, not `*`.
- Keep `upload_post_enabled=false` unless social publishing is intentionally
  configured.
- Prefer uploaded/licensed background music. The upstream README notes that
  bundled default music may have copyright risk.

## Copyright and platform notes

The source code is MIT licensed. Keep the original `LICENSE` file when
deploying or distributing modified versions.

Generated videos can include third-party stock video, TTS, music, user uploads,
and LLM-generated script text. Each provider has its own terms. Verify the
license for Pexels, Pixabay, Coverr, any uploaded assets, and any background
music before publishing videos commercially or automatically cross-posting them.
