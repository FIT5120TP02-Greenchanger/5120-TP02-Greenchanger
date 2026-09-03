"""
initialize fastapi app and define health check endpoint

running: localhost:8000/api/health
"""
import itertools
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from psycopg import Connection
from pydantic import BaseModel

from app.db import get_db, jsonable_row, pool
from app.greening_model.scenario_inputs import calculate_simulated_action, load_input_contract

# Read once at import time -- avoid re-parsing the JSON contract off disk on
# every /simulate and /meta/assumptions request.
SCENARIO_INPUT_CONTRACT = load_input_contract()

# Browsers refuse to hand a cross-origin response to page JavaScript unless the
# server says the origin may read it. In production the frontend is served from
# the same host as this API, so nothing here applies -- these entries exist for
# local development, where Vite runs on its own port. Override with a
# comma-separated CORS_ORIGINS if your dev server uses a different one.
CORS_ORIGINS = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,"
    "https://greenchanger.me,https://www.greenchanger.me",
).split(",")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open the connection pool on startup, close it on shutdown."""
    pool.open()
    yield
    pool.close()


app = FastAPI(
    title="GreenShift API",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _like_prefix(text: str) -> str:
    """Escape LIKE metacharacters so a typed % cannot become a wildcard.

    Without this, searching for "%" produces a pattern with no fixed prefix --
    the planner cannot use the index and we are back to a full scan of the
    address table on every keystroke.
    """
    return text.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# Vicmap spells street types out ("SEASCAPE STREET", "CENTRE ROAD") while people type the
# usual abbreviations, so "1 centre rd" never matched. Each abbreviated token is tried both
# as typed and expanded: "ST" is also SAINT ("ST KILDA ROAD"), so the as-typed form must stay.
STREET_TYPE_ABBREVIATIONS = {
    "AV": "AVENUE",
    "AVE": "AVENUE",
    "BLVD": "BOULEVARD",
    "BVD": "BOULEVARD",
    "CL": "CLOSE",
    "CR": "CRESCENT",
    "CRES": "CRESCENT",
    "CT": "COURT",
    "DR": "DRIVE",
    "ESP": "ESPLANADE",
    "GR": "GROVE",
    "HWY": "HIGHWAY",
    "LN": "LANE",
    "PDE": "PARADE",
    "PL": "PLACE",
    "RD": "ROAD",
    "ST": "STREET",
    "TCE": "TERRACE",
    "WY": "WAY",
}
MAX_PREFIX_CANDIDATES = 8


def _prefix_candidates(text: str) -> list[str]:
    """Upper-cased prefixes to try: the text as typed first, then its street-type expansions.

    Every abbreviated token can stay or expand independently, so "1 st kilda rd" yields
    "1 ST KILDA ROAD" as well as "1 STREET KILDA ROAD". Capped so a pathological query
    cannot fan out into dozens of LIKE patterns; the as-typed form is always first.
    """
    tokens = text.strip().upper().split()
    options = [
        (token, STREET_TYPE_ABBREVIATIONS[token])
        if token in STREET_TYPE_ABBREVIATIONS
        else (token,)
        for token in tokens
    ]
    candidates: list[str] = []
    for combo in itertools.product(*options):
        candidate = " ".join(combo)
        if candidate not in candidates:
            candidates.append(candidate)
        if len(candidates) == MAX_PREFIX_CANDIDATES:
            break
    return candidates


# Health check endpoint
@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/addresses")
def search_addresses(
    q: str = Query(..., min_length=3, description="Address search prefix, e.g. '15 Seascape'"),
    limit: int = Query(10, ge=1, le=50),
    db: Connection = Depends(get_db),
) -> list[dict]:
    """Lightweight address autocomplete. No environmental joins -- keep this cheap."""
    candidates = _prefix_candidates(q)
    # One prefix LIKE per candidate, OR-ed: each is still a fixed-prefix pattern the
    # text_pattern_ops index serves (BitmapOr), so this stays as cheap as the single-pattern query.
    params: dict[str, Any] = {"limit": limit}
    like_clauses = []
    exact_clauses = []
    for index, candidate in enumerate(candidates):
        params[f"like{index}"] = _like_prefix(candidate)
        params[f"exact{index}"] = candidate
        like_clauses.append(f"UPPER(full_address) LIKE %(like{index})s || '%%'")
        exact_clauses.append(f"UPPER(full_address) = %(exact{index})s")
    with db.cursor() as cur:
        cur.execute(
            f"""
            SELECT address_id, full_address, locality_name, postcode,
                   parcel_area_m2, lot_size_category
            FROM latest_greater_melbourne_address_property
            WHERE {" OR ".join(like_clauses)}
            ORDER BY
                CASE WHEN {" OR ".join(exact_clauses)} THEN 0 ELSE 1 END,
                CASE WHEN is_primary = 'Y' THEN 0 ELSE 1 END,
                full_address
            LIMIT %(limit)s
            """,
            params,
        )
        return [jsonable_row(row) for row in cur.fetchall()]


@app.get("/api/properties/baseline")
def get_property_baseline_view(
    address: str = Query(
        ..., min_length=3, description="Exact address, typically chosen from /api/addresses"
    ),
    db: Connection = Depends(get_db),
) -> dict:
    """One property's full baseline: heat, canopy, weather and mapped-tree context."""
    with db.cursor() as cur:
        cur.execute(
            "SELECT * FROM get_property_baseline(%(address)s, %(limit)s)",
            {"address": address.strip(), "limit": 1},
        )
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="No matching property found")
    return jsonable_row(row)


class ScenarioSimulateRequest(BaseModel):
    action_type: str
    inputs: dict[str, Any]


@app.post("/api/scenario/simulate")
def simulate_scenario(payload: ScenarioSimulateRequest) -> dict:
    """Indicative-range greening scenario calculation. Pure math, no DB access."""
    try:
        return calculate_simulated_action(
            payload.action_type, payload.inputs, contract=SCENARIO_INPUT_CONTRACT
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/meta/assumptions")
def get_model_assumptions(db: Connection = Depends(get_db)) -> dict:
    """Model parameters, validation status and the cited evidence behind them."""
    with db.cursor() as cur:
        cur.execute(
            "SELECT * FROM current_intervention_model_parameter "
            "ORDER BY action_type, parameter_code"
        )
        parameters = [jsonable_row(row) for row in cur.fetchall()]

        cur.execute("SELECT * FROM selected_intervention_evidence ORDER BY citation_key")
        evidence = [jsonable_row(row) for row in cur.fetchall()]

    return {
        "model_parameters": parameters,
        "evidence": evidence,
        "scenario_inputs": SCENARIO_INPUT_CONTRACT,
    }