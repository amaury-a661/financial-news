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

## Run it

Start the workflow `ft-financial-digest` from the Mistral Console
(**Workflows → ft-financial-digest → Start workflow**) or via the API:

```bash
curl -X POST https://api.mistral.ai/v1/workflows/ft-financial-digest/execute \
  -H "Authorization: Bearer $MISTRAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Optional input (defaults shown):

```json
{
  "recipient_email": "amaury.kezachian@outlook.com",
  "max_headlines": 8
}
```

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
