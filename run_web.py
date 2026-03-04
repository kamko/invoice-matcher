#!/usr/bin/env python3
"""
Run the Invoice Matcher web application.

Usage:
    uv run python run_web.py

This starts the FastAPI backend on port 8000.
For development, also run the frontend: cd frontend && npm run dev
"""

import sys
import uvicorn


def main():
    """Run the web application."""
    print("Starting Invoice Matcher Web Application...")
    print("API: http://localhost:8000")
    print("API Docs: http://localhost:8000/docs")
    print()
    print("For frontend development, in another terminal run:")
    print("  cd frontend && npm run dev")
    print()

    uvicorn.run(
        "web.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["web"],
    )


if __name__ == "__main__":
    main()
