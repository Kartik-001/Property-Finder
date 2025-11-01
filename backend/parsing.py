"""Text parsing utilities (rule-based, optional Gemini wrapper)."""

import re
from typing import Dict, Any, Optional
from .data_loader import load_projects_df


BUDGET_RE = re.compile(
    r"under\s+₹?\s*?([\d\.,]+)\s*(cr|crore|lakh|lakh?s|l|k)?|below\s+₹?\s*?([\d\.,]+)\s*(cr|crore|lakh|lakh?s|l|k)?|up to\s+₹?\s*?([\d\.,]+)\s*(cr|crore|lakh|lakh?s|l|k)?",
    re.IGNORECASE,
)


def parse_budget_to_lakhs_from_match(m):
    if not m:
        return None
    # find first numeric group
    groups = [g for g in m.groups() if g]
    if not groups:
        return None
    # extract numeric and unit
    num = None
    unit = None
    for i in range(0, len(m.groups()), 2):
        if m.groups()[i]:
            num = m.groups()[i]
            unit = m.groups()[i + 1] if i + 1 < len(m.groups()) else None
            break
    if not num:
        return None
    s = str(num).replace(",", "")
    val = float(s)
    if unit:
        unit = unit.lower()
        if "cr" in unit or "crore" in unit:
            return val * 100.0
        if unit.startswith("l"):
            return val
        if unit == "k":
            return val / 100.0
    if val > 1e5:
        return val / 100000.0
    return val


def rule_based_parse(query: str, projects_df=None) -> Dict[str, Any]:
    q = query.lower()
    filters = {
        "city": None,
        "bhk": None,
        "budget_lakhs_max": None,
        "possession": None,
        "locality": None,
        "project_name": None,
        "soft": [],
    }

    # bhk
    m = re.search(r"(\d+)\s*bhk", query, flags=re.IGNORECASE)
    if m:
        filters["bhk"] = int(m.group(1))

    m = BUDGET_RE.search(query)
    if m:
        filters["budget_lakhs_max"] = parse_budget_to_lakhs_from_match(m)

    # possession canonicalization
    if "ready to move" in q or "ready-to-move" in q or re.search(r"\bread\b", q):
        # canonical: "Ready"
        filters["possession"] = "Ready"
    if "under construction" in q or re.search(r"\buc\b", q):
        # canonical: "Under_Construction"
        filters["possession"] = "Under_Construction"

    if projects_df is None:
        projects_df = load_projects_df()

    # city/locality extraction (ensure lowercased + trimmed)
    cities = [
        str(c).strip().lower()
        for c in projects_df["city_norm"].dropna().unique().tolist()
    ]
    cities = sorted(set(cities), key=len, reverse=True)
    for city in cities:
        if city and re.search(r"\b" + re.escape(city) + r"\b", q):
            filters["city"] = city
            break

    localities = [
        str(loc).strip().lower()
        for loc in projects_df["locality_norm"].dropna().unique().tolist()
    ]
    localities = sorted(set(localities), key=len, reverse=True)
    for loc in localities:
        if loc and re.search(r"\b" + re.escape(loc) + r"\b", q):
            filters["locality"] = loc
            break

    proj_names = [
        str(p).strip() for p in projects_df["project_name"].dropna().unique().tolist()
    ]
    if proj_names:
        # Try fuzzy matching if available; otherwise deterministic substring match
        matched = None
        try:
            from rapidfuzz import fuzz, process  # type: ignore

            best = process.extractOne(q, proj_names, scorer=fuzz.partial_ratio)
            if best and best[1] >= 80:
                matched = best[0]
        except Exception:
            # deterministic fallback: longest project name that appears as substring
            proj_lower = [(p.lower(), p) for p in proj_names]
            proj_lower.sort(key=lambda x: len(x[0]), reverse=True)
            for low, orig in proj_lower:
                if low and low in q:
                    matched = orig
                    break
        if matched:
            filters["project_name"] = matched

    if "near metro" in q or " near metro" in q or re.search(r"\bmetro\b", q):
        filters["soft"].append("near metro")
    if "near it" in q or "it park" in q or re.search(r"\bit\b", q):
        filters["soft"].append("near it park")

    return filters


def gemini_extract_filters(query: str) -> Optional[Dict[str, Any]]:
    """Optional Gemini extractor. Returns None when not configured or on error."""
    try:
        import google.generativeai as genai
    except Exception:
        return None
    # Keep a lightweight wrapper (not enabled by default)
    try:
        model = genai.GenerativeModel("models/gemini-2.5-flash")
        prompt = f"Extract JSON with keys city,bhk,budget_lakhs_max,possession,locality,project_name,soft from: {query}"
        response = model.generate_content(prompt)
        import json

        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        return json.loads(text)
    except Exception:
        return None
