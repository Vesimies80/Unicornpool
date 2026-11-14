# UnicornPool

Angel investing from €50. Cala finds early-stage startups in a field and their sourced data. Startups of similar size are bundled into a pool, and each one's cap is scaled to its size. Small investors chip in, and when the pool hits its goal every commitment locks at once.

## Run it (Mac/Linux)

```bash
./run.sh            # creates a venv, installs deps, starts on http://localhost:8000
```

Or by hand:

```bash
pip install -r requirements.txt
uvicorn app:app --port 8000
```

Your Cala key is in `.env` (`CALA_API_KEY=...`). Don't commit `.env` (it's in `.gitignore`).

On Windows: `python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt && uvicorn app:app --port 8000`

## Demo script (≈2 min)

1. Type a field and region (e.g. *climate tech* / *the Nordics*), then click **Build pools with Cala**. It takes about 20–60 s the first time.
2. Walk through one startup card: the description, raised amount, team size and last round all come from Cala, and the **↗ source links** are where each fact comes from. Point out the **cap rule** line: smaller startups get a smaller cap.
3. Open **"What we asked Cala"** at the bottom to show the real queries.
4. Click **Simulate a crowd**. Hundreds of €50–€5,000 tickets take the pool to 90%.
5. Type your name and click **Commit the rest**. The pool **locks** and the allocation table appears.

The page refreshes every 5 s, so a judge can open it on their phone (same Wi-Fi: `http://<your-laptop-ip>:8000`) and contribute live.

## Before the demo: warm the cache

Every Cala response is cached in `data/cache/`. Run your demo field once at the venue, and if the Wi-Fi drops, the same field still loads instantly.
- `CALA_REFRESH=1 uvicorn app:app` forces fresh Cala calls.
- **Reset demo** clears the pools but keeps the cache.
- Offline UI testing with fake companies: `CALA_MOCK=1 uvicorn app:app`. Delete `data/cache/` afterwards so fake data doesn't get mixed in.

## How it works

| File | What |
|---|---|
| `cala.py` | Cala client: `POST /v1/knowledge/query` (structured rows) and `/search` (sourced answer). Flattens `context[].origins[]` into source links and caches responses. |
| `pool.py` | Discovery → enrichment → sizing → bundling, plus contributions and the lock. State lives in `data/state.json`. |
| `app.py` | FastAPI routes. |
| `static/index.html` | The whole UI. |

**Discovery:** one structured `query` ("early-stage {sector} startups in {region} … funding, round, employees") plus one natural-language `search` for extra candidates. Then one `search` per company (max 9, run in parallel) for a description, team size, funding and sources.

**Sizing rule** (`size_cap` in `pool.py`):
- Tier by total raised so far: Pre-seed (< €1M), Seed (< €5M), Growth.
- Cap = employees × €15k, or 25% of raised if no headcount, clamped to the tier's min/max.
- A lone startup in a tier is merged into the nearest tier.
- Pool goal = sum of caps. On lock, each ticket is split pro-rata by cap.

## Tuning if Cala's results look thin

- Broaden the inputs: "fintech" / "Europe" usually returns more than a niche field plus a small country.
- Edit the prompts at the top of `discover()` in `pool.py`. Cala also accepts dot-notation, e.g. `startups.location=Finland.funding<5M`.
- Raise `MAX_STARTUPS` for bigger pools (more credits, slower).

## Pitch line for regulation questions

Pooled retail investing in the EU falls under the crowdfunding regulation (ECSP). In production this runs on top of a licensed crowdfunding platform. UnicornPool is the discovery, sizing and matching layer.
