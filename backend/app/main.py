# the main file of the backend application, 
# which initializes the FastAPI app and defines the health check endpoint.

"""
initialize fastapi app and define health check endpoint

running: localhost:8000/api/health
"""
from fastapi import FastAPI

app = FastAPI(
    title="GreenShift API",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

# Health check endpoint
@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}