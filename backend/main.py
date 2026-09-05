"""
Main Backend Application Entry Point
====================================
FastAPI Application for Context Lakehouse and Git Graphify.
"""

import uvicorn
from backend.api.app import app

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
