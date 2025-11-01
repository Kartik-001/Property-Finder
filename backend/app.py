"""FastAPI application exposing the search pipeline."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from typing import Any, Dict
from .search import run_query_pipeline

app = FastAPI(title="Property Search API")


@app.post("/api/search")
async def search_endpoint(request: Request) -> Dict[str, Any]:
    body = await request.json()
    query = body.get("query", "")
    use_gemini = bool(body.get("use_gemini", False))
    top_k = int(body.get("top_k", 10))

    try:
        out = run_query_pipeline(query, use_gemini=use_gemini, top_k=top_k)
        # out already contains serializable filters/summary/cards/results
        return out
    except Exception as e:
        # Return a JSON error payload instead of HTML to help clients debug
        return JSONResponse(status_code=500, content={"error": str(e)})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app:app", host="0.0.0.0", port=8000, reload=True)
