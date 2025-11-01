# Frontend (Vite + React)

Minimal React app that provides a chat-like UI and calls the backend `/api/search` endpoint.

Quick start (PowerShell):

```powershell
cd "g:\My Drive\assignment\AI Engineer Intern Task\project_root\frontend"
npm install
npm run dev
```

Open http://localhost:5173 in your browser.

Notes:
- The frontend calls http://127.0.0.1:8000/api/search. Run the FastAPI backend (uvicorn) on port 8000.
- If you run backend on a different origin, enable CORS in the FastAPI app or change the fetch URL accordingly.
