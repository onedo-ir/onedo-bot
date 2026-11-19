from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.routers import admin, auth, browser, chat, tasks
from app.schemas import HealthOut
from app.seed import migrate_schema_to_single_user, seed_database

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    migrate_schema_to_single_user(engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(tasks.router)
app.include_router(admin.api_router)
app.include_router(admin.docs_router)
app.include_router(browser.router)


@app.get("/api/health", response_model=HealthOut)
def health():
    return HealthOut(status="ok", app=settings.app_name)
