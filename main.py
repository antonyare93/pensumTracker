from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.academic_router import router

app = FastAPI(title="Pensum Tracker API")

import os

_extra = os.getenv("ALLOWED_ORIGINS", "")
_origins = [o.strip() for o in _extra.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        *_origins,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
