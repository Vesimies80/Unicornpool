"""Thin Cala client with on-disk caching (so the demo also works offline)."""
import hashlib
import json
import os
from pathlib import Path

import requests

BASE = "https://api.cala.ai/v1"
CACHE_DIR = Path(__file__).parent / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


class CalaError(Exception):
    pass


def _key():
    k = os.getenv("CALA_API_KEY")
    if not k:
        raise CalaError("CALA_API_KEY missing - put it in .env")
    return k


def _cached(kind, text, fn):
    h = hashlib.sha1(f"{kind}:{text}".encode()).hexdigest()[:16]
    path = CACHE_DIR / f"{kind}_{h}.json"
    if path.exists() and os.getenv("CALA_REFRESH") != "1":
        return json.loads(path.read_text())
    data = fn()
    path.write_text(json.dumps({"input": text, "response": data}, indent=2))
    return {"input": text, "response": data}


def _post(endpoint, payload):
    if os.getenv("CALA_MOCK") == "1":
        import mock_cala
        return mock_cala.respond(endpoint, payload)
    r = requests.post(
        f"{BASE}/knowledge/{endpoint}",
        json=payload,
        headers={"X-API-KEY": _key(), "Content-Type": "application/json"},
        timeout=90,
    )
    if r.status_code != 200:
        raise CalaError(f"Cala {endpoint} {r.status_code}: {r.text[:300]}")
    return r.json()


def query(text):
    """Structured answer: {'results': [rows], 'entities': [...]}"""
    return _cached("query", text, lambda: _post("query", {"input": text}))["response"]


def search(text):
    """Natural-language answer: {'content', 'explainability', 'context', 'entities'}"""
    return _cached("search", text, lambda: _post("search", {"input": text}))["response"]


def sources_from(search_resp, limit=6):
    """Flatten context[].origins[] into unique (name, url, fact) items."""
    out, seen = [], set()
    for kb in (search_resp or {}).get("context") or []:
        for o in kb.get("origins") or []:
            doc = o.get("document") or {}
            src = o.get("source") or {}
            url = doc.get("url") or src.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            out.append({
                "name": doc.get("name") or src.get("name") or url,
                "publisher": src.get("name") or "",
                "url": url,
                "fact": (kb.get("content") or "")[:220],
            })
            if len(out) >= limit:
                return out
    return out
