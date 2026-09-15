# Set up Lenz fact-checking

Lenz checks factual claims against independent sources and returns a verdict, a score from 1 to 10, and the citations behind it. Follow the steps below to wire it into this project, then run the verification step so we both know it works.

## What I want to check with Lenz

Medical information about capabilities of imaging soft- and hardware

Keep this in mind when you wire it up — where the checks belong in the flow, and what should happen when a claim comes back false.

## API key

```
lenz_57e565c9bfe462828d579575253f6f13
```

This is a test key, issued automatically so you can start now. Rotate it before production: https://lenz.io/api-credentials

## Setup

No SDK — plain HTTP against `https://lenz.io/api/v1`, Bearer auth. Read the
key from the environment rather than hardcoding it:

```python
import os
import httpx

BASE = "https://lenz.io/api/v1"
headers = {"Authorization": f"Bearer {os.environ['LENZ_API_KEY']}"}

r = httpx.post(
    f"{BASE}/assess",
    headers=headers,
    json={"claim": "The Great Wall of China is visible from space"},
    timeout=30,
)
r.raise_for_status()
for claim in r.json()["claims"]:
    print(claim["claim"], claim["verdict"], claim["confidence"])
```

`/assess` returns `{"claims": [...], "error", "error_code"}` — one entry
per atomic claim, each with a `verdict` and a `confidence`. That row is
the whole answer at this tier: no score, no citation list. Use `/verify`
when you need those. An empty `claims` with `error_code: "no_claim"`
means the input held no checkable statement; a vague one is assessed on
its most likely reading, which the row's `claim` shows.

Four endpoints, in the order you would normally reach for them. Every
request body takes `text`:

- `POST /extract` — pull the checkable claims out of a block of text.
- `POST /assess` — score claims. Synchronous, ~10s.
- `POST /verify` — the full multi-model pipeline. Asynchronous, ~90s: it
  returns a `task_id`, and you poll `GET /verify/status/{task_id}` or
  supply a `webhook_url` in the body to be called on completion.
- `POST /ask/{verification_id}` — a grounded follow-up, body
  `{"message": ...}`.

Request and response schemas: https://lenz.io/api/v1/docs/

## Verify it works

Run the snippet above as-is, and show me the verdict and confidence it
came back with.

## Then

Find the place in your codebase where we produce text a user will act
on, and tell me how you would put an `/assess` call in front of it —
including what should happen when a claim comes back false, and how you
would handle a non-200. Do not add it yet; describe it first.

## Reference

- API reference: https://lenz.io/api/v1/docs/
- Quickstart: https://lenz.io/docs/quickstart
