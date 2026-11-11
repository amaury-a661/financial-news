# FT Financial Digest

A Mistral Workflow (one-shot, triggered on demand — no schedule) that:

1. Fetches the Financial Times front page and extracts headlines.
2. Uses an LLM to keep only **financial-industry news** (markets, banks, central
   banks, listed companies, deals, regulation, macro) and drop everything else
   (lifestyle, arts, sports, personal blogs, opinion without financial substance).
3. Emails an HTML digest to the recipient with a **podcast-style MP3**
   (1–2 minutes, Mistral Voxtral TTS, US English male voice `voice_485`) attached.

The email is sent through the workspace **Gmail connector** with
`on_behalf_of=True`, so it uses the Gmail account of the user who triggers the
workflow.

## Run it (self-hosted worker)

There is no schedule: the workflow only runs when you trigger it, and every
trigger sends one fresh digest. The worker runs on your own machine and
registers the workflow `ft-financial-digest` with Mistral's platform — no
managed deployment or pay-as-you-go plan required.

1. Install Python 3.12+ and [uv](https://docs.astral.sh/uv/), then:

   ```bash
   git clone https://github.com/amaury-a661/financial-news
   cd financial-news
   uv sync
   cp .env.example .env   # then set MISTRAL_API_KEY in .env
   uv run python -m worker.entrypoints.worker
   ```

2. Keep the worker running. The first start registers the workflow and the
   deployment `ft-financial-digest` under your account (on-behalf-of workflows
   require this hardened registration; it happens automatically on first
   registration).

3. Trigger a run:

   - **Mistral Console**: Workflows → `ft-financial-digest` → **Start
     workflow**, input `{}` (defaults: digest to `amaury.kezachian@outlook.com`,
     8 headlines).
   - **API**:

     ```bash
     curl -X POST https://api.mistral.ai/v1/workflows/ft-financial-digest/execute \
       -H "Authorization: Bearer $MISTRAL_API_KEY" \
       -H "Content-Type: application/json" \
       -d '{}'
     ```

The email is sent through the workspace **Gmail connector** with
`on_behalf_of=True`, so it uses the Gmail account of the user who triggers the
workflow. The worker must stay running while an execution is in progress.

## Managed deployment (optional)

To run the worker on Mistral Cloud instead of locally, enable pay-as-you-go on
your organization and create a managed deployment from this repository with
Dockerfile `deploy/docker/Dockerfile.worker`.

## Project layout

- `src/worker/workflows/ft_digest.py` — the workflow and its activities
- `src/worker/entrypoints/worker.py` — worker entrypoint (discovers workflows)
- `deploy/docker/Dockerfile.worker` — image used by the managed deployment
- `tests/` — unit tests for parsing and rendering helpers

## Local development

```bash
uv sync
uv run pytest
```

## Deployment

Deployed as a managed deployment on Mistral Cloud from this repository
(Dockerfile: `deploy/docker/Dockerfile.worker`). The worker authenticates with
the platform-injected service-account token; no secrets in the repo.
