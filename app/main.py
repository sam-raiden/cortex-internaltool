from fastapi import FastAPI
from app.api.endpoints import collection_runs
from app.api import trends

app = FastAPI(title="TamilSh POC Observability API", version="0.1.0")

app.include_router(collection_runs.router)
app.include_router(trends.router)

@app.get("/")
def read_root():
    return {"status": "ok", "app": "TamilSh Observability"}
