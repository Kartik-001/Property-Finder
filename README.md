Property Search — backend + frontend

This project refactors analysis from a notebook into a tiny, testable Python package and a minimal React frontend. It provides a simple search API over a CSV dataset of projects.

Repository layout
- backend/ — Python package
   - app.py            FastAPI app exposing /api/search
   - data_loader.py    CSV loading, normalization and cached dataset
   - parsing.py        rule-based query parser (and optional Gemini wrapper)
   - search.py         filtering, ranking and pipeline wiring
   - summary.py        generate short grounded summaries from results
   - format.py         helpers that convert results to UI cards
- data/ — CSV files (project.csv, ProjectAddress.csv, ProjectConfiguration.csv, ProjectConfigurationVariant.csv, projects_df.csv)
- frontend/ — minimal Vite + React chat UI that calls the API
- tests/ — unit tests for parsing & formatting

Quick start — backend (PowerShell)

1) Create & activate virtualenv, install requirements

```powershell
cd "g:\My Drive\assignment\AI Engineer Intern Task\project_root"
python -m venv .venv
. .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2) Run the API with uvicorn

```powershell
uvicorn backend.app:app --reload --port 8000
```

The app exposes POST /api/search which accepts JSON:

```json
{ "query": "3BHK in Pune under 1.2 Cr", "use_gemini": false, "top_k": 5 }
```

Example curl (Linux/macOS) — equivalent PowerShell Invoke-RestMethod can be used on Windows:

```bash
curl -X POST http://127.0.0.1:8000/api/search \
   -H "Content-Type: application/json" \
   -d '{"query":"3BHK in Pune under 1.2 Cr","use_gemini":false,"top_k":5}'
```

Expected (truncated) JSON response structure:

```json
{
   "filters": { "city": "pune", "bhk": 3, "budget_lakhs_max": 120.0, ... },
   "summary": "3 matching projects found. Price range: ₹1.00 L — ₹1.20 Cr.",
   "cards": [
      {
         "title": "3BHK in Baner",
         "city_locality": "Pune, Baner",
         "bhk": 3,
         "price": "₹1.20 Cr",
         "project_name": "Sunshine Residency",
         "possession": "Ready",
         "amenities": [],
         "cta": "/project/sunshine-residency-baner--1-20-cr",
         "relevance_score": 42.0
      }
   ],
   "results": [ { /* raw result records for debugging */ } ]
}
```

Frontend (Vite + React)

1) Install and run the frontend

```powershell
cd frontend
npm install
npm run dev
```

Open the dev server (usually http://localhost:5173). The frontend calls `http://127.0.0.1:8000/api/search` by default; if your backend uses a different origin enable CORS in `backend/app.py` or edit the fetch URL in `frontend/src/components/Chat.jsx`.

CSV data location
- Place the source CSV files in the `data/` folder (already included in this repo). The loader reads the following files by name:
   - project.csv
   - ProjectAddress.csv
   - ProjectConfiguration.csv
   - ProjectConfigurationVariant.csv

Tests

Run unit tests with pytest from the repository root:

```powershell
cd "g:\My Drive\assignment\AI Engineer Intern Task\project_root"
. .venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest -q
```

Notes & troubleshooting
- If you see "ModuleNotFoundError: rapidfuzz" the code has a deterministic fallback; to enable fuzzy matching install `rapidfuzz` in your environment.
- If frontend cannot reach backend, either enable CORS in `backend/app.py` or run both servers on the same host+port via a proxy.
- The Gemini extractor in `backend/parsing.py` is optional and disabled by default; it requires additional credentials and the `google-generativeai` package.

Optional: screenshots / demo
- You can add a short GIF or screenshots in this README (e.g., `docs/demo.gif`) to show the chat UI and result cards.

If you'd like, I can add: CORS support to the backend, a Dockerfile, or a single-command `make`/PowerShell script to start both frontend and backend for local demos.
