import random

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import pool  # noqa: E402

app = FastAPI(title="UnicornPool")
app.mount("/static", StaticFiles(directory="static"), name="static")


class BuildReq(BaseModel):
    sector: str
    region: str


class ContribReq(BaseModel):
    name: str
    amount: float


@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.get("/api/bundles")
def bundles():
    st = pool.load()
    return {"bundles": [pool.view(b) for b in st["bundles"]], "log": st.get("last_log", [])}


@app.post("/api/build")
def build(req: BuildReq):
    bundles, log = pool.build_bundles(req.sector.strip(), req.region.strip())
    if not bundles:
        raise HTTPException(404, detail={"msg": "Cala returned no startups for that field - try a broader sector or region.", "log": log})
    return {"bundles": [pool.view(b) for b in bundles], "log": log}


@app.post("/api/bundles/{bid}/contribute")
def contribute(bid: str, req: ContribReq):
    try:
        b, accepted = pool.contribute(bid, req.name, req.amount)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    return {"bundle": b, "accepted": accepted}


NAMES = ["Aino", "Mikko", "Lena", "Jonas", "Sofia", "Elias", "Maja", "Noah", "Ida", "Leo",
         "Emilia", "Oskar", "Clara", "Matteo", "Saara", "Lukas", "Nora", "Ville", "Anna", "Tomás"]


@app.post("/api/bundles/{bid}/simulate")
def simulate(bid: str, n: int = 12):
    """Demo helper: a crowd of small investors chips in (stops 1 ticket short of the goal)."""
    st = pool.load()
    b = next((x for x in st["bundles"] if x["id"] == bid), None)
    if not b:
        raise HTTPException(404, "Bundle not found")
    if b["status"] == "locked":
        raise HTTPException(400, "Pool already locked")
    # a crowd of small tickets takes it to ~90%; you close it live on stage
    pool.simulate_crowd(bid, target_pct=0.9, tickets=[50, 100, 100, 250, 250, 500, 500, 1000, 2500, 5000],
                        names=NAMES)
    return {"bundle": pool.view(next(x for x in pool.load()["bundles"] if x["id"] == bid))}


@app.post("/api/reset")
def reset():
    pool.reset()
    return {"ok": True}
