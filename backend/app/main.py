"""
initialize fastapi app and define health check endpoint

running: localhost:8000/api/health
"""
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from psycopg import Connection
from pydantic import BaseModel

from app.db import get_db, jsonable_row, pool
from app.greening_model.scenario_inputs import calculate_simulated_action


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
    pattern = q.strip() + "%"
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT address_id, full_address, locality_name, postcode,
                   parcel_area_m2, lot_size_category
            FROM latest_greater_melbourne_address_property
            WHERE full_address ILIKE %(pattern)s
            ORDER BY
                CASE WHEN full_address ILIKE %(exact)s THEN 0 ELSE 1 END,
                CASE WHEN is_primary = 'Y' THEN 0 ELSE 1 END,
                full_address
            LIMIT %(limit)s
            """,
            {"pattern": pattern, "exact": q.strip(), "limit": limit},
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
        return calculate_simulated_action(payload.action_type, payload.inputs)
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

    return {"model_parameters": parameters, "evidence": evidence}