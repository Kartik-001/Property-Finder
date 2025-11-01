"""Configuration constants for backend."""

import os

# Optional: set via environment or .env
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "models/gemini-2.5-flash")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
PORT = int(os.environ.get("PORT", 8000))
