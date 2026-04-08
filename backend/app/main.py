"""Puerta de entrada de la API y composición de routers."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import connect_to_mongo
from app.routes.auth import router as auth_router
from app.routes.progress import router as progress_router
from app.routes.users import router as users_router
from app.routes.weight import router as weight_router

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

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(weight_router)
app.include_router(progress_router)


@app.get("/")
def root():
    return {"message": "Fibrito API funcionando correctamente"}


@app.get("/health")
def health():
    return {"status": "ok"}
