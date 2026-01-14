# main.py
import logging
from fastapi import FastAPI
from services.config import PROJECT_NAME, VERSION
from routers import bridge

app = FastAPI(
    title=PROJECT_NAME,
    description="Webhook Bridge",
    version=VERSION
)

app.include_router(bridge.router)

@app.get("/")
def read_root():
    return {
        "message": f"{PROJECT_NAME} Aktif",
        "version": VERSION
    }