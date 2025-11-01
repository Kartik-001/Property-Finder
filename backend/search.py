"""Search and ranking logic for projects."""

from typing import Dict, Any, List
import pandas as pd
from difflib import SequenceMatcher

# higher-level pipeline imports (kept local to this module so callers can use a
# single function that wires parsing, search, summary and formatting together)
from .parsing import rule_based_parse, gemini_extract_filters
from .data_loader import load_projects_df
from .summary import generate_summary_from_df
from .format import results_to_cards


def _partial_ratio(a: str, b: str) -> float:
    """Return a 0-100 partial-ratio score between two strings.

    Prefer rapidfuzz if installed; otherwise use a deterministic difflib-based
    best-window ratio scaled to 0-100.
    """
    try:
        from rapidfuzz import fuzz as _rf_fuzz  # type: ignore

        return float(_rf_fuzz.partial_ratio(a, b))
    except Exception:
        if not a or not b:
            return 0.0
        a = str(a).lower()
        b = str(b).lower()
        if len(a) > len(b):
            a, b = b, a
        best = 0.0
        la = len(a)
        for i in range(0, len(b) - la + 1):
            window = b[i : i + la]
            r = SequenceMatcher(None, a, window).ratio()
            if r > best:
                best = r
        return best * 100.0


def search_projects(
    filters: Dict, projects_df: pd.DataFrame, top_k: int = 10
) -> List[Dict[str, Any]]:
    """Filter and rank projects, returning a list of serializable dict records.

    - Applies exact filters for city, bhk and possession (case-insensitive)
    - Filters by budget (price_lakhs <= budget_lakhs_max)
    - Computes a numeric `relevance_score` used to sort results
    - Returns top_k records as list[dict]
    """
    df = projects_df.copy()
    # strict filters
    if filters.get("city"):
        df = df[df["city_norm"].str.lower() == str(filters["city"]).strip().lower()]
    if filters.get("bhk") is not None:
        df = df[df["bhk"] == filters["bhk"]]
    if filters.get("budget_lakhs_max") is not None:
        df = df[df["price_lakhs"].notna()]
        df = df[df["price_lakhs"] <= filters["budget_lakhs_max"]]
    if filters.get("possession"):
        # normalize possession comparison (allow variants like 'Ready' or 'ready' or 'Under_Construction')
        poss = str(filters["possession"]).lower().replace("_", " ")
        df = df[
            df["possession_norm"].astype(str).str.lower().str.contains(poss, na=False)
        ]

    df = df.reset_index(drop=True)
    if df.empty:
        return []

    scores = []
    for _, row in df.iterrows():
        score = 0.0
        qname = filters.get("project_name") or ""
        if qname and isinstance(qname, str):
            # fuzzy matching: try to use rapidfuzz if available, otherwise use
            # a deterministic difflib-based partial ratio fallback.
            try:
                # local import avoids hard dependency at module import time
                from rapidfuzz import fuzz as _rf_fuzz  # type: ignore

                part_score = _rf_fuzz.partial_ratio(
                    qname, str(row.get("project_name", ""))
                )
            except Exception:
                # Use module-level deterministic fallback when rapidfuzz isn't available
                part_score = _partial_ratio(qname, str(row.get("project_name", "")))

            score += (part_score / 100.0) * 50
        loc = filters.get("locality") or ""
        if loc and row.get("locality_norm"):
            score += _partial_ratio(loc, str(row.get("locality_norm", ""))) / 100.0 * 30
        for s in filters.get("soft", []):
            if (
                s in str(row.get("project_name", "")).lower()
                or s in str(row.get("locality_norm", "")).lower()
            ):
                score += 10
        if (
            filters.get("budget_lakhs_max")
            and row.get("price_lakhs") not in (None, "")
            and pd.notna(row.get("price_lakhs"))
        ):
            diff = max(0, filters["budget_lakhs_max"] - float(row["price_lakhs"]))
            score += min(10, (diff / max(1.0, float(filters["budget_lakhs_max"]))) * 10)
        scores.append(score)

    df["relevance_score"] = scores
    df = df.sort_values(by="relevance_score", ascending=False).head(top_k)

    # convert to serializable list of dicts
    records = []
    raw = df.to_dict(orient="records")
    for r in raw:
        nr = {k: _normalize_record_value(v) for k, v in r.items()}
        records.append(nr)
    return records


def _normalize_record_value(v: Any):
    """Convert pandas/numpy scalar values to native Python types and map NA -> None."""
    try:
        # pandas NA / numpy scalar
        if pd.isna(v):
            return None
    except Exception:
        pass
    # numpy scalar to python scalar
    if hasattr(v, "item"):
        try:
            return v.item()
        except Exception:
            return v
    return v


def run_query_pipeline(
    query: str, use_gemini: bool = False, top_k: int = 5
) -> Dict[str, Any]:
    """Run the full query -> filters -> search -> summary -> cards pipeline.

    This function is pure in the sense that it only uses the provided module
    APIs (which themselves may use cached loaders). The return value contains
    only JSON-serializable Python primitives (lists/dicts/str/int/float/None).

    Returns a dict with keys: filters, summary, cards, results
    - filters: dict of parsed filters
    - summary: human readable string
    - cards: list of card dicts (formatted for UI)
    - results: list of raw result records (dicts) with primitive values
    """
    # load dataset (uses lru_cache inside loader)
    projects_df = load_projects_df()

    # parse filters
    if use_gemini:
        gem = gemini_extract_filters(query)
        filters = gem if gem else rule_based_parse(query, projects_df=projects_df)
    else:
        filters = rule_based_parse(query, projects_df=projects_df)

    # search (returns a list of dicts)
    results_records = search_projects(filters, projects_df, top_k=top_k)

    # create a DataFrame view of results for summary/cards generation (empty DF when no results)
    results_df = pd.DataFrame(results_records)

    # summary and cards (formatting helper accepts a DataFrame)
    summary = generate_summary_from_df(results_df, filters)
    cards = results_to_cards(results_df)

    return {
        "filters": filters,
        "summary": summary,
        "cards": cards,
        "results": results_records,
    }
