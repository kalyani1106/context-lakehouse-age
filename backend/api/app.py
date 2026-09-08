"""
FastAPI Application Entry Point
===============================
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.config import settings
from backend.api.routes import router
from backend.api.git_routes import git_router
from backend.api.context_routes import context_router

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Context Lakehouse, PDF Extraction, and Git Repository Knowledge Graph Pipeline with Apache AGE"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(router)
app.include_router(git_router)
app.include_router(context_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
