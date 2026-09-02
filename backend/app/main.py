"""
initialize fastapi app and define health check endpoint

running: localhost:8000/api/health
"""
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
    prefix = _like_prefix(q)
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT address_id, full_address, locality_name, postcode,
                   parcel_area_m2, lot_size_category
            FROM latest_greater_melbourne_address_property
            WHERE UPPER(full_address) LIKE UPPER(%(prefix)s) || '%%'
            ORDER BY
                CASE WHEN UPPER(full_address) = UPPER(%(prefix)s) THEN 0 ELSE 1 END,
                CASE WHEN is_primary = 'Y' THEN 0 ELSE 1 END,
                full_address
            LIMIT %(limit)s
            """,
            {"prefix": prefix, "limit": limit},
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