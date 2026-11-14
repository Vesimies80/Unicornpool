"""Discovery (Cala) -> sizing -> bundling -> contributions -> lock."""
import json
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cala

STATE_FILE = Path(__file__).parent / "data" / "state.json"
_lock = threading.Lock()

MIN_TICKET = 50          # EUR minimum contribution
MAX_STARTUPS = 9         # keep demo fast + cheap
TIERS = [  # (name, max total raised so far in EUR, cap per startup bounds)
    ("Pre-seed pool", 1_000_000, (40_000, 150_000)),
    ("Seed pool", 5_000_000, (100_000, 400_000)),
    ("Growth pool", float("inf"), (250_000, 750_000)),
]

# ---------------------------------------------------------------- parsing
_MULT = {"k": 1e3, "thousand": 1e3, "m": 1e6, "mn": 1e6, "million": 1e6,
         "b": 1e9, "bn": 1e9, "billion": 1e9}


def parse_money(v):
    """'€2.5M', '$3 million', 'USD 1,200,000', 4000000 -> float EUR (approx)."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).lower().replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(k|thousand|mn|m|million|bn|b|billion)?\b", s)
    if not m:
        return None
    amt = float(m.group(1)) * _MULT.get(m.group(2) or "", 1)
    if "$" in s or "usd" in s:
        amt *= 0.92
    elif "£" in s or "gbp" in s:
        amt *= 1.17
    return amt if amt >= 1000 else None


def parse_int(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    m = re.search(r"\d[\d,]*", str(v))
    return int(m.group().replace(",", "")) if m else None


def pick(row, *keys):
    low = {k.lower(): v for k, v in row.items()}
    for k in keys:
        if low.get(k) not in (None, "", "N/A", "null"):
            return low[k]
    return None


def strip_md(s):
    s = re.sub(r"[*_#`>\[\]]", "", s or "")
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------- discovery
def discover(sector, region):
    """Use Cala to find early-stage startups in a field, then enrich each one."""
    log = []
    q_struct = (f"early-stage {sector} startups in {region} founded after 2019 "
                f"with total funding under 10M, with funding amount, round type, "
                f"employee count and year")
    q_nl = f"Which early-stage {sector} startups in {region} raised pre-seed or seed funding recently?"

    companies = {}
    try:
        res = cala.query(q_struct)
        rows = res.get("results") or []
        log.append({"endpoint": "query", "input": q_struct, "rows": len(rows)})
        for r in rows:
            name = pick(r, "company", "name", "startup", "company_name", "organization")
            if not name or not isinstance(name, str):
                continue
            c = companies.setdefault(name, {"name": name, "rounds": []})
            amt = parse_money(pick(r, "funding_amount", "funding", "total_funding", "amount", "raised"))
            c["rounds"].append({
                "amount": amt,
                "round": pick(r, "round_type", "round", "stage"),
                "year": pick(r, "year", "date", "announced"),
            })
            c.setdefault("sector", pick(r, "sector", "industry"))
            c.setdefault("location", pick(r, "location", "country", "city"))
            emp = parse_int(pick(r, "employee_count", "employees", "headcount"))
            if emp:
                c["employees"] = emp
    except cala.CalaError as e:
        log.append({"endpoint": "query", "input": q_struct, "error": str(e)})

    # Natural-language search: extra candidates + sources
    try:
        s = cala.search(q_nl)
        ents = [e["name"] for e in (s.get("entities") or []) if e.get("entity_type") == "Company"]
        log.append({"endpoint": "search", "input": q_nl, "companies": len(ents)})
        for n in ents:
            companies.setdefault(n, {"name": n, "rounds": []})
    except cala.CalaError as e:
        log.append({"endpoint": "search", "input": q_nl, "error": str(e)})

    names = list(companies)[:MAX_STARTUPS]
    with ThreadPoolExecutor(max_workers=5) as ex:
        enriched = list(ex.map(lambda n: enrich(companies[n], sector), names))
    for e in enriched:
        log.append({"endpoint": "search", "input": e.pop("_q"), "sources": len(e["sources"])})
    return [e for e in enriched if e], log


def enrich(c, sector):
    q = (f"{c['name']}: what does the company do, where is it based, how many employees, "
         f"total funding raised and latest funding round")
    c = dict(c)
    c["_q"] = q
    try:
        s = cala.search(q)
    except cala.CalaError:
        s = {}
    text = s.get("content") or ""
    clean = strip_md(text)
    c["description"] = (re.split(r"(?<=[.!?])\s", clean)[0] if clean else "")[:260]
    c["sources"] = cala.sources_from(s)
    c["facts"] = len(s.get("context") or [])

    if not c.get("employees"):
        m = re.search(r"(\d[\d,]*)\s*(?:\+\s*)?(?:employees|staff|people|team members)", clean, re.I)
        if m:
            c["employees"] = parse_int(m.group(1))
    amounts = [r["amount"] for r in c["rounds"] if r.get("amount")]
    raised = sum(amounts) if amounts else None
    if not raised:
        m = re.search(r"(?:raised|funding of|secured|total funding[^\d€$]*)\s*([€$£]?\s?\d[\d.,]*\s*(?:k|m|mn|million|bn|b)?)", clean, re.I)
        raised = parse_money(m.group(1)) if m else None
    c["raised"] = raised
    last = next((r for r in reversed(c["rounds"]) if r.get("round")), None)
    c["last_round"] = (last or {}).get("round")
    c["last_year"] = (last or {}).get("year")
    c["sector"] = c.get("sector") or sector
    return c


# ---------------------------------------------------------------- sizing
def size_cap(c):
    """How much this startup may raise from the pool, scaled by its size."""
    raised = c.get("raised") or 0
    emp = c.get("employees")
    tier = next(t for t in TIERS if raised < t[1])
    lo, hi = tier[2]
    if emp:
        basis, how = emp * 15_000, f"{emp} employees × €15k"
    elif raised:
        basis, how = raised * 0.25, f"25% of €{raised/1e6:.1f}M raised so far"
    else:
        basis, how = lo, "no size data → tier minimum"
    cap = int(round(min(max(basis, lo), hi), -3))
    return tier[0], cap, how


def build_bundles(sector, region):
    startups, log = discover(sector, region)
    groups = {}
    for c in startups:
        tier, cap, how = size_cap(c)
        c.update(cap=cap, cap_rule=how, tier=tier)
        groups.setdefault(tier, []).append(c)
    # a "bundle" of one isn't a bundle: fold lone startups into the nearest tier
    order = [t[0] for t in TIERS]
    for tier in list(order):
        if len(groups.get(tier, [])) == 1 and len(groups) > 1:
            i = order.index(tier)
            near = sorted((t for t in groups if t != tier), key=lambda t: abs(order.index(t) - i))[0]
            groups[near] += groups.pop(tier)
    bundles = []
    for tier, members in groups.items():
        bundles.append({
            "id": uuid.uuid4().hex[:8],
            "name": f"{sector.title()} · {region} · {tier}",
            "sector": sector, "region": region, "tier": tier,
            "startups": members,
            "goal": sum(m["cap"] for m in members),
            "contributions": [],
            "status": "open",
            "created": time.time(),
        })
    bundles.sort(key=lambda b: -len(b["startups"]))
    with _lock:
        st = load()
        st["bundles"] = bundles + st["bundles"]
        st["last_log"] = log
        save(st)
    return bundles, log


# ---------------------------------------------------------------- state
def load():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"bundles": [], "last_log": []}


def save(st):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(st, indent=2))


def view(b):
    raised = sum(x["amount"] for x in b["contributions"])
    out = dict(b, raised=raised, pct=min(100, round(100 * raised / b["goal"], 1)) if b["goal"] else 0,
               investors=len({x["name"].lower() for x in b["contributions"]}))
    if b["status"] == "locked":
        out["allocation"] = [{"name": s["name"], "amount": s["cap"],
                              "share": round(100 * s["cap"] / b["goal"], 1)} for s in b["startups"]]
    return out


def contribute(bundle_id, name, amount):
    with _lock:
        st = load()
        b = next((x for x in st["bundles"] if x["id"] == bundle_id), None)
        if not b:
            raise ValueError("Bundle not found")
        if b["status"] == "locked":
            raise ValueError("This pool is already locked")
        if amount < MIN_TICKET:
            raise ValueError(f"Minimum ticket is €{MIN_TICKET}")
        remaining = b["goal"] - sum(x["amount"] for x in b["contributions"])
        accepted = min(amount, remaining)
        b["contributions"].append({"name": name.strip() or "Anonymous", "amount": accepted, "t": time.time()})
        if accepted >= remaining:
            b["status"] = "locked"
            b["locked_at"] = time.time()
        save(st)
        return view(b), accepted


def simulate_crowd(bundle_id, target_pct, tickets, names):
    import random
    with _lock:
        st = load()
        b = next(x for x in st["bundles"] if x["id"] == bundle_id)
        raised = sum(x["amount"] for x in b["contributions"])
        target = target_pct * b["goal"]
        i = 0
        while raised < target:
            amt = min(random.choice(tickets), target - raised)
            if amt < MIN_TICKET:
                break
            i += 1
            b["contributions"].append({"name": f"{random.choice(names)} #{random.randint(100, 999)}",
                                       "amount": amt, "t": time.time()})
            raised += amt
        save(st)


def reset():
    with _lock:
        save({"bundles": [], "last_log": []})
