# Railway backend deployment

This deployment target runs only the FastAPI backend from the root Dockerfile.
Railway injects `PORT` at runtime, and the app reads it before falling back to
`MPT_LISTEN_PORT`, so no custom start command is required.

The Dockerfile creates a runtime `config.toml` from `config.example.toml` during
the image build. Do not commit a real `config.toml`; production values should
come from Railway variables.

## Cost and limits

Railway is suitable for a prototype, but it is not unlimited free Docker
hosting. At the time this guide was written, the Free plan starts with a
30-day trial with credits and then small monthly free usage. Video generation
uses FFmpeg, disk, CPU, Redis, Supabase, and external model APIs, so expect to
upgrade if jobs become long or concurrent.

## Deploy from GitHub

Use this flow for the `production` branch:

1. Open Railway and create a new project.
2. Choose Deploy from GitHub repo.
3. Select `theshortylz/video-processor`.
4. Set the branch to `production`.
5. Keep the root directory as `/`.
6. Let Railway use the root `Dockerfile`. The committed `railway.toml` also
   pins the builder to Dockerfile and sets `/health` as the healthcheck path.
7. Generate a public Railway domain for the service.
8. Add the runtime variables below before exposing the API publicly.

## Required runtime variables

Set these in Railway service variables. Never commit real values to `.env`,
`.env.example`, `config.toml`, Dockerfiles, or documentation.

```text
MPT_REQUIRE_API_KEY=true
MPT_API_KEY=<long-random-server-secret>
CORS_ALLOWED_ORIGINS=https://your-frontend-domain.example
MPT_ENDPOINT=https://your-railway-domain.up.railway.app
MPT_LLM_PROVIDER=openai
OPENAI_API_KEY=<provider-key>
REDIS_URL=<redis://... or rediss://...>
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<server-side-service-role-key>
SUPABASE_STORAGE_BUCKET=generated-videos
```

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

Use `SUPABASE_STORAGE_PUBLIC=true` only when the bucket is intentionally public.
Keep the Supabase service role key only in Railway backend variables.

## Redis

Use a managed Redis URL such as Upstash or a Railway Redis-compatible service.
The variable must be `REDIS_URL`. Prefer TLS URLs (`rediss://`) when the provider
supports them.

## Frontend integration

Do not put `MPT_API_KEY` in browser code. The future
`blast-financial-insights` frontend should call this backend through a
server-side route that injects:

```http
x-api-key: <MPT_API_KEY>
```

Direct browser calls would expose the key.

## Verification

After Railway deploys, verify:

```shell
curl -i https://your-railway-domain.up.railway.app/health
curl -i https://your-railway-domain.up.railway.app/api/v1/tasks
curl -i -H 'x-api-key: <MPT_API_KEY>' https://your-railway-domain.up.railway.app/api/v1/tasks
```

Expected result:

- `/health` returns `200`.
- The unauthenticated `/api/v1/tasks` request returns `401`.
- The authenticated `/api/v1/tasks` request succeeds.

## Security checklist

- Keep `MPT_REQUIRE_API_KEY=true`.
- Use a long random `MPT_API_KEY` and rotate it if it is exposed.
- Set `CORS_ALLOWED_ORIGINS` to the frontend domain, not `*`.
- Do not expose Redis publicly.
- Do not expose Supabase service role keys to browser code.
- Keep `upload_post_enabled=false` unless social publishing is intentionally
  configured.
- Review the license/terms for any stock video, music, TTS, uploaded assets,
  and generated content before publishing videos commercially.
