# Onedo bot

**Self-hosted Persian browser agent.** Chat in a RTL panel; an AI agent drives Chromium (Playwright), streams a live view, pauses to ask when unsure, and can run scheduled playbooks.

> پنل فارسی تک‌کاربره برای فرمان به ایجنت مرورگر، مشاهده زنده کروم، و کارهای دوره‌ای — استقرار با Docker Compose.

---

## Features

- **Chat-driven browser automation** — navigate, click, type, extract; cancel mid-run
- **Live Chromium view** — interactive screenshot (click / type / scroll) over WebSocket
- **Pause-and-ask** — stops on ambiguity (`waiting_user`) instead of guessing
- **Persistent browser session** — Chromium profile, cookies, and credentials on a Docker volume
- **Scheduled playbooks** — periodic tasks with detailed step files; list/delete in `/app/schedules`
- **Single-user panel** — one admin from env; no signup / multi-tenant UI
- **Admin REST API** — token-protected ops + OpenAPI document
- **OpenAI-compatible LLM** — configure only via environment variables

## Requirements

- Docker Engine + Docker Compose v2
- An OpenAI-compatible API (base URL + API key)
- ~2 GB RAM recommended (Chromium + Playwright)

## Quick start (published images)

Images are published to the Gitea container registry:

| Service  | Image |
| -------- | ----- |
| nginx    | `gitea.tmayt.ir/thaiostream/onedo-bot-nginx` |
| frontend | `gitea.tmayt.ir/thaiostream/onedo-bot-frontend` |
| backend  | `gitea.tmayt.ir/thaiostream/onedo-bot-backend` |
| browser  | `gitea.tmayt.ir/thaiostream/onedo-bot-browser` |

Tags: `latest` and a slug from the commit subject on `main`.

### Option A — no source clone

```bash
curl -fsSL -o docker-compose.yml \
  https://gitea.tmayt.ir/thaiostream/onedo-bot/raw/branch/main/docker-compose.registry.yml
curl -fsSL -o .env.example \
  https://gitea.tmayt.ir/thaiostream/onedo-bot/raw/branch/main/.env.example

cp .env.example .env
# Edit .env: SECRET_KEY, ADMIN_API_TOKEN, POSTGRES_PASSWORD,
# DEFAULT_ADMIN_*, OPENAI_COMPATIBLE_*

docker login gitea.tmayt.ir   # if the registry requires auth
docker compose up -d
```

### Option B — from a clone

```bash
cp .env.example .env
# Edit .env as above
docker compose -f docker-compose.registry.yml up -d
```

Open: **http://localhost:12277**

Pin a version tag:

```bash
ONEDO_IMAGE_TAG=your-version-slug \
  docker compose -f docker-compose.registry.yml up -d
```

Change host port:

```bash
ONEDO_PORT=8080 docker compose -f docker-compose.registry.yml up -d
```

Stop:

```bash
docker compose -f docker-compose.registry.yml down
```

Data volumes (`pgdata`, `browser_data`) are kept unless you add `-v`.

---

## Configuration

Copy `.env.example` → `.env` and set at least:

| Variable | Purpose |
| -------- | ------- |
| `SECRET_KEY` | JWT signing secret (long random string) |
| `ADMIN_API_TOKEN` | Token for Admin API |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Database credentials |
| `DEFAULT_ADMIN_EMAIL` / `DEFAULT_ADMIN_PASSWORD` | Sole panel login |
| `OPENAI_COMPATIBLE_BASE_URL` | LLM API base (e.g. `https://api.openai.com/v1`) |
| `OPENAI_COMPATIBLE_API_KEY` | LLM API key |
| `OPENAI_COMPATIBLE_MODEL` | Model id (default `auto`) |
| `CORS_ORIGINS` | Allowed origins (include your public URL) |
| `ONEDO_IMAGE_TAG` | Image tag (optional, default `latest`) |
| `ONEDO_PORT` | Host port for nginx (optional, default `12277`) |

AI settings are **env-only** — not editable in the UI or database.

---

## Architecture

```text
Browser (you)
    │  :12277 (or ONEDO_PORT)
    ▼
  nginx ──► frontend (React, RTL)
       └──► backend (FastAPI) ──► PostgreSQL
                      │
                      └──► browser (Playwright / Chromium)
                              └── volume: browser_data
```

| Service  | Role |
| -------- | ---- |
| **nginx** | Only host-exposed port; reverse proxy to frontend + backend |
| **frontend** | React (Vite) Persian RTL panel, PWA |
| **backend** | FastAPI, JWT auth, agent loop, scheduler, Admin API |
| **browser** | Headless Chromium via Playwright; live screenshots + input |
| **db** | PostgreSQL 16 (internal network only) |

Only **nginx** is published to the host. Backend, frontend, browser, and database stay on the Compose network.

### Persistent data (`browser_data`)

| Path | Purpose |
| ---- | ------- |
| `/data/browser/chromium-profile` | Cookies, localStorage, HTTP cache |
| `/data/browser/cookies.json` | Exported cookie jar (agent tools) |
| `/data/browser/credentials.json` | Site logins for the agent (not shown in UI) |
| `/data/browser/chat_memory/{id}.json` | Per-conversation agent memory |
| `/data/browser/scheduled_tasks/{id}.md` | Periodic playbook steps |

Conversations and task metadata live in PostgreSQL (`pgdata`).

### Browser agent queue

Only **one** agent controls Chromium at a time (FIFO lock). Chat runs and scheduled jobs share the same queue; status stays `pending` until the lock is acquired. `waiting_user`, completion, or cancel releases the lock for the next waiter.

---

## Using the panel

1. Sign in with `DEFAULT_ADMIN_EMAIL` / `DEFAULT_ADMIN_PASSWORD`.
2. Open a chat and give a browser instruction (Persian or English).
3. Watch the live Chromium panel; you can also click / type / scroll yourself.
4. If the agent is unsure, it asks in chat (`waiting_user`) — reply to continue.
5. Cancel a running job from the loading bubble.
6. Manage periodic tasks at `/app/schedules` (list / delete).

There is no multi-user signup, no admin web console, and no credentials UI — vault and cookies are agent/file-based only.

---

## Admin API

Token from `.env`: `ADMIN_API_TOKEN`.

| Auth | Value |
| ---- | ----- |
| Preferred header | `X-Admin-Token: <ADMIN_API_TOKEN>` |
| Alternative | `Authorization: Bearer <ADMIN_API_TOKEN>` |
| Base path | `/api/admin-api/...` |
| OpenAPI (no auth) | `/api/<ADMIN_API_TOKEN>/docs/openapi.yml` |

Examples:

```bash
export TOKEN="your-admin-api-token"
export BASE="http://localhost:12277"

curl -H "X-Admin-Token: $TOKEN" "$BASE/api/admin-api/stats"
curl -H "X-Admin-Token: $TOKEN" "$BASE/api/admin-api/browser-agent-queue"
curl -H "X-Admin-Token: $TOKEN" "$BASE/api/admin-api/tasks"
curl -X POST -H "X-Admin-Token: $TOKEN" "$BASE/api/admin-api/tasks/<task_id>/cancel"
curl -H "X-Admin-Token: $TOKEN" "$BASE/api/admin-api/agent-config"
curl -H "X-Admin-Token: $TOKEN" "$BASE/api/admin-api/scheduled-tasks"
curl -X DELETE -H "X-Admin-Token: $TOKEN" "$BASE/api/admin-api/scheduled-tasks/<id>"
```

`agent-config` is **read-only** (mirrors env). New admin operations must be exposed on this API and documented in the OpenAPI builder — see [`AGENTS.md`](AGENTS.md).

---

## Build from source (development)

```bash
cp .env.example .env
# Edit secrets and OPENAI_COMPATIBLE_*

export DOCKER_BUILDKIT=1 COMPOSE_DOCKER_CLI_BUILD=1
docker compose up -d --build
```

`docker-compose.yml` builds from local Dockerfiles. Local builds may use optional package mirrors via `build.args` (e.g. Liara). Published CI images use stock Debian/Alpine apt and official PyPI/npm.

BuildKit caches apt/pip/npm and Playwright Chromium — avoid `--no-cache` unless you need a clean rebuild.

---

## CI / image publishing

Workflow: [`.github/workflows/build-and-push.yml`](.github/workflows/build-and-push.yml)

| Item | Detail |
| ---- | ------ |
| Triggers | Push to `main`, or `workflow_dispatch` |
| Shape | One job; builds nginx → frontend → backend → browser sequentially |
| Registry | `gitea.tmayt.ir/thaiostream/onedo-bot-*` |
| Tags | `latest` + sanitized commit subject |
| Driver | Classic Docker (no Buildx attestations / OCI index) |

Optional repository secrets (job is **skipped**, not failed, when unset):

- `REGISTRY_USERNAME`
- `REGISTRY_PASSWORD` (token with package write)

---

## Security notes

- Change `SECRET_KEY`, `ADMIN_API_TOKEN`, `POSTGRES_PASSWORD`, and `DEFAULT_ADMIN_PASSWORD` before any public exposure.
- Do not publish backend / frontend / db / browser ports — only nginx.
- Treat `browser_data` as sensitive (session cookies + `credentials.json`).
- Keep `ADMIN_API_TOKEN` private; the OpenAPI URL embeds the token for discovery — restrict network access accordingly.
- Single-user by design: one env-defined account, no registration.

---

## Project layout

```text
.
├── backend/                 # FastAPI + agent + Admin API
├── browser/                 # Playwright / Chromium service
├── frontend/                # React (Vite) RTL panel
├── nginx/                   # Reverse proxy
├── docker-compose.yml       # Build from source
├── docker-compose.registry.yml  # Run published images
├── .env.example
├── AGENTS.md                # Contributor / agent rules
└── .github/workflows/       # Build and Push Image
```

---

## Contributing

For coding agents and humans working on this repo, follow [`AGENTS.md`](AGENTS.md):

- Keep the panel single-user; AI config stays env-only.
- Every new admin/ops action must land in `/api/admin-api/...` **and** the OpenAPI document.
- Do not expose internal service ports beyond nginx.

Issues and pull requests are welcome for bugs, docs, and self-host improvements.

---

## License

No license file is published in this repository yet. Clarify licensing with the maintainers before redistributing.
