"""Puerta de entrada que crea la app FastAPI, prepara CORS para el frontend, conecta Mongodb y añade endpoints mínimos."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import connect_to_mongo

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    connect_to_mongo()
    yield


app = FastAPI(
    title="Fibrito API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "message": "Fibrito API funcionando correctamente"
    }


@app.get("/health")
def health():
    return {
        "status": "ok"
    }