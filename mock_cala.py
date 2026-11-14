"""FAKE Cala responses for offline UI testing only (CALA_MOCK=1). Not real companies."""
import random

FAKE = [
    ("MockGrid Oy", "€800K", "Pre-seed", 6), ("TestHeat Labs", "€2.1M", "Seed", 14),
    ("Demo Carbon", "€450K", "Pre-seed", None), ("Sample Hydrogen", "€3.4M", "Seed", 22),
    ("Placeholder Solar", "€1.5M", "Seed", 9), ("Fixture Batteries", "€6M", "Series A", 40),
    ("Stub Recycling", "€300K", "Pre-seed", 4),
]


def respond(endpoint, payload):
    text = payload["input"]
    if endpoint == "query":
        return {"results": [{"company": n, "funding_amount": a, "round_type": r, "year": "2025",
                             "sector": "climate tech", **({"employee_count": e} if e else {})}
                            for n, a, r, e in FAKE], "entities": []}
    name = next((n for n, *_ in FAKE if text.startswith(n)), None)
    if name:
        content = f"**{name}** is a fictional test company that builds things for the demo. It has {random.randint(3, 30)} employees."
    else:
        content = "Several fictional startups raised seed rounds."
    return {
        "content": content,
        "explainability": [],
        "context": [{"id": "x", "content": content,
                     "origins": [{"source": {"name": "Example News", "url": "https://example.com"},
                                  "document": {"name": f"Test article about {name or 'startups'}",
                                               "url": f"https://example.com/{(name or 'x').replace(' ', '-')}"}}]}],
        "entities": [{"id": "1", "name": "Mock Extra AB", "entity_type": "Company", "mentions": []}],
    }
