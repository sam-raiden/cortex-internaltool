import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import collection_runs
from app.api import trends, v1

app = FastAPI(title="Cortex Trends API", version="0.1.0")

# The frontend runs on a different origin (e.g. a Google AI Studio-hosted
# app), so without CORS the browser blocks every request outright.
# CORS_ALLOWED_ORIGINS is a comma-separated list; defaults to "*" for dev
# convenience -- tighten this to the frontend's real origin(s) before any
# production deployment.
_cors_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _cors_origins == "*" else [o.strip() for o in _cors_origins.split(",")],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(collection_runs.router)
app.include_router(trends.router)
app.include_router(v1.router)

@app.get("/")
def read_root():
    return {"status": "ok", "app": "TamilSh Observability"}
