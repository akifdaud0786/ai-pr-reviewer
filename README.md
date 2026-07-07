# 🤖 Advanced AI GitHub PR Code Reviewer

An event-driven, multi-agent AI system that automatically reviews GitHub Pull Requests.
It listens for GitHub webhook events, fans a PR diff out to four parallel LangGraph
agents (Static Analysis, Security, Architecture, Style), merges + deduplicates their
findings, posts inline + summary review comments back to GitHub, and — once a PR is
merged — learns repo-specific style patterns for smarter future reviews.

```
GitHub PR Event → Gateway (HMAC verify) → Webhook (parse/dedupe) → Redis Queue
   → Celery Worker → Orchestrator (fetch diff + LangGraph multi-agent review)
   → Reviewer (post inline + summary comments to GitHub)
   → [on merge] → Learner (extract patterns → store for future reviews)
```

## Services

| Service | Responsibility | Port |
|---|---|---|
| `gateway_service` | Verifies GitHub HMAC signatures, rejects forged requests, forwards verified events | 8000 |
| `webhook_service` | Parses PR payload, deduplicates by commit SHA, stores PR metadata, enqueues job | 8001 |
| `orchestrator_service` | Celery worker: fetches diff, loads repo patterns, runs LangGraph multi-agent review | (worker) |
| `reviewer_service` | GitHub App JWT auth, posts inline review comments + summary to the PR | 8002 |
| `learner_service` | On PR merge, extracts frequent issues/style patterns and stores them per-repo | 8003 |
| `shared` | Common DB models, Pydantic schemas, config | — |

## Stack

- **FastAPI** microservices, **Celery + Redis** for async job processing
- **LangGraph** `StateGraph` for the multi-agent review workflow (parallel fan-out → merge → dedupe)
- **OpenAI GPT-4o-mini** powering all four review agents
- **PostgreSQL** (SQLAlchemy async + asyncpg) for PRs, findings, and learned repo patterns
- **GitHub App** JWT + installation-token auth for posting comments
- **Prometheus + Grafana** for metrics, **Langfuse** (optional) for LLM tracing

## Quick start (local, Docker Compose)

```bash
cp .env.example .env
# fill in GITHUB_APP_ID, GITHUB_PRIVATE_KEY_PATH, GITHUB_WEBHOOK_SECRET, OPENAI_API_KEY

docker compose up --build
```

This starts: `postgres`, `redis`, `gateway` (:8000), `webhook` (:8001), `reviewer` (:8002),
`learner` (:8003), a Celery `worker` (orchestrator), `prometheus` (:9090), `grafana` (:3000).

Point your GitHub App's webhook URL at `http://<your-host>:8000/webhook/github`
(use ngrok/cloudflared for local testing) and subscribe to **Pull Request** events.

## Local test without a real GitHub App

Every service has an HTTP-testable path that doesn't require live GitHub/OpenAI creds:

```bash
# Health checks
curl localhost:8000/health
curl localhost:8001/health
curl localhost:8002/health
curl localhost:8003/health

# Simulate a signed webhook (script computes the HMAC signature for you)
python scripts/send_test_webhook.py
```

## Repository layout

```
ai-pr-reviewer/
├── docker-compose.yml
├── .env.example
├── shared/                  # DB models, schemas, config shared by all services
├── gateway_service/         # HMAC verification + forwarding
├── webhook_service/         # Parse, dedupe, store, enqueue
├── orchestrator_service/    # Celery worker + LangGraph agents
│   └── agents/              # static_analysis, security, style, architecture, merge
├── reviewer_service/        # GitHub comment posting
├── learner_service/         # Pattern extraction from merged PRs
├── monitoring/              # Prometheus + Grafana config
└── scripts/                 # test/dev helper scripts
```

See each service's own README section below (in its folder docstring) for endpoint details.
