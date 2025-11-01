# streamlit_app.py
import streamlit as st

# To make this Streamlit app self-contained for quick demos, include a local
# copy of the minimal pipeline and data-loading helpers. We prefer reading the
# precomputed `data/projects_df.csv` when available; otherwise fall back to the
# package loader in `backend.data_loader`.
import os
import re
from difflib import SequenceMatcher
from typing import Dict, Any, List, Optional
import pandas as pd

# Budget regex and parsing (copied from backend/parsing.py)
BUDGET_RE = re.compile(
    r"under\s+₹?\s*?([\d\.,]+)\s*(cr|crore|lakh|lakh?s|l|k)?|below\s+₹?\s*?([\d\.,]+)\s*(cr|crore|lakh|lakh?s|l|k)?|up to\s+₹?\s*?([\d\.,]+)\s*(cr|crore|lakh|lakh?s|l|k)?",
    re.IGNORECASE,
)


def parse_budget_to_lakhs_from_match(m):
    if not m:
        return None
    groups = [g for g in m.groups() if g]
    if not groups:
        return None
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
        filters["possession"] = "Ready"
    if "under construction" in q or re.search(r"\buc\b", q):
        filters["possession"] = "Under_Construction"

    if projects_df is None:
        projects_df = load_projects_df_local()

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
        matched = None
        try:
            from rapidfuzz import fuzz, process  # type: ignore

            best = process.extractOne(q, proj_names, scorer=fuzz.partial_ratio)
            if best and best[1] >= 80:
                matched = best[0]
        except Exception:
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


def _partial_ratio(a: str, b: str) -> float:
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


def _normalize_record_value(v: Any):
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    if hasattr(v, "item"):
        try:
            return v.item()
        except Exception:
            return v
    return v


def search_projects(
    filters: Dict, projects_df: pd.DataFrame, top_k: int = 10
) -> List[Dict[str, Any]]:
    df = projects_df.copy()
    if filters.get("city"):
        df = df[df["city_norm"].str.lower() == str(filters["city"]).strip().lower()]
    if filters.get("bhk") is not None:
        df = df[df["bhk"] == filters["bhk"]]
    if filters.get("budget_lakhs_max") is not None:
        df = df[df["price_lakhs"].notna()]
        df = df[df["price_lakhs"] <= filters["budget_lakhs_max"]]
    if filters.get("possession"):
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
            try:
                from rapidfuzz import fuzz as _rf_fuzz  # type: ignore

                part_score = _rf_fuzz.partial_ratio(
                    qname, str(row.get("project_name", ""))
                )
            except Exception:
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

    records = []
    raw = df.to_dict(orient="records")
    for r in raw:
        nr = {k: _normalize_record_value(v) for k, v in r.items()}
        records.append(nr)
    return records


def price_format_from_lakhs(val):
    if pd.isna(val) or val is None:
        return "N/A"
    v = float(val)
    if v >= 100:
        return f"₹{v / 100:.2f} Cr"
    return f"₹{v:.2f} L"


def generate_summary_from_df(df: pd.DataFrame, filters: dict) -> str:
    n = len(df)
    if n == 0:
        return "No matches found for the requested filters."

    min_p = df["price_lakhs"].dropna()
    max_p = df["price_lakhs"].dropna()
    min_p_val = float(min_p.min()) if not min_p.empty else None
    max_p_val = float(max_p.max()) if not max_p.empty else None

    poss_series = (
        df["possession_norm"].dropna().astype(str).str.replace(" ", "_").str.title()
    )
    ready_count = int((poss_series == "Ready").sum()) if not poss_series.empty else 0
    uc_count = (
        int((poss_series == "Under_Construction").sum()) if not poss_series.empty else 0
    )

    localities = df["locality_norm"].dropna()
    top_locality = None
    if not localities.empty:
        top_locality = localities.value_counts().idxmax()

    parts = []
    s1 = f"{n} matching project{'s' if n > 1 else ''} found."
    parts.append(s1)
    s2_parts = []
    if ready_count:
        s2_parts.append(f"Ready: {ready_count}")
    if uc_count:
        s2_parts.append(f"Under_Construction: {uc_count}")
    if s2_parts:
        parts.append("Possession status — " + ", ".join(s2_parts) + ".")
    if min_p_val is not None and max_p_val is not None:
        parts.append(
            f"Price range: {price_format_from_lakhs(min_p_val)} — {price_format_from_lakhs(max_p_val)}."
        )
    if top_locality:
        parts.append(f"Most listings are in {top_locality.title()}.")
    return " ".join(parts)


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9\-]", "-", s.lower()).strip("-")


def make_project_card(row: dict) -> dict:
    bk = row.get("bhk") if isinstance(row, dict) else row["bhk"]
    locality = (
        row.get("locality_norm") if isinstance(row, dict) else row["locality_norm"]
    )
    city = row.get("city_norm") if isinstance(row, dict) else row["city_norm"]
    project_name = (
        row.get("project_name") if isinstance(row, dict) else row["project_name"]
    )
    price_l = row.get("price_lakhs") if isinstance(row, dict) else row["price_lakhs"]
    possession = (
        row.get("possession_norm") if isinstance(row, dict) else row["possession_norm"]
    )

    title = f"{int(bk) if bk is not None and not pd.isna(bk) else ''}BHK in {locality.title() if locality else (city.title() if city else '')}".strip()
    city_locality = (
        f"{city.title() if city else ''}, {locality.title() if locality else ''}".strip(
            ", "
        )
    )
    price = price_format_from_lakhs(price_l)
    pname = project_name.title() if project_name else ""
    possession = possession.title() if possession else "Unknown"

    def _price_slug(val):
        try:
            if pd.isna(val) or val is None:
                return "price-na"
            v = float(val)
        except Exception:
            return "price-na"
        if v >= 100:
            cr = v / 100.0
            return f"{cr:.2f}".replace(".", "-") + "-cr"
        if abs(v - round(v)) < 1e-6:
            return f"{int(round(v))}-l"
        return f"{v:.2f}".replace(".", "-") + "-l"

    proj_slug = slugify(pname) if pname else "unknown"
    loc_slug = slugify(locality) if locality else ""
    price_part = _price_slug(price_l)
    slug = f"{proj_slug}-{loc_slug}--{price_part}".strip("-")
    cta = f"/project/{slug}"
    card = {
        "title": title,
        "city_locality": city_locality,
        "bhk": int(bk) if bk is not None and not pd.isna(bk) else None,
        "price": price,
        "project_name": pname,
        "possession": possession,
        "amenities": [],
        "cta": cta,
        "relevance_score": float(row.get("relevance_score", 0.0))
        if hasattr(row, "get")
        else float(row["relevance_score"]),
    }
    return card


def results_to_cards(df: pd.DataFrame):
    return [make_project_card(row) for _, row in df.iterrows()]


def load_projects_df_local() -> pd.DataFrame:
    """Load a precomputed `projects_df.csv` from data/ if available, otherwise
    fall back to the package loader in backend.data_loader.
    """
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    data_dir = os.path.join(repo_root, "data")
    csv_path = os.path.join(data_dir, "projects_df.csv")
    if os.path.exists(csv_path):
        try:
            return pd.read_csv(csv_path)
        except Exception:
            pass
    # fallback: try calling the package loader if present
    try:
        from backend.data_loader import load_projects_df as _pkg_loader  # type: ignore

        return _pkg_loader()
    except Exception:
        cols = [
            "project_id",
            "project_name",
            "city_norm",
            "locality_norm",
            "bhk",
            "price_lakhs",
            "possession_norm",
        ]
        return pd.DataFrame(columns=cols)


def run_query_pipeline(
    query: str, use_gemini: bool = False, top_k: int = 5
) -> Dict[str, Any]:
    projects_df = load_projects_df_local()
    filters = rule_based_parse(query, projects_df=projects_df)
    results_records = search_projects(filters, projects_df, top_k=top_k)
    results_df = pd.DataFrame(results_records)
    summary = generate_summary_from_df(results_df, filters)
    cards = results_to_cards(results_df)
    return {
        "filters": filters,
        "summary": summary,
        "cards": cards,
        "results": results_records,
    }


st.set_page_config(page_title="🏠 NoBrokerage Property Finder", layout="wide")

st.title("🏠 NoBrokerage Property Finder (AI Chat)")
st.markdown("""
Type natural language queries like:
- *“1BHK in Mumbai”*
- *“3BHK flat in Pune under ₹1.2 Cr”*
- *“Ready to move 2BHK in Baner below 75 L”*
""")


# Store chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Render previous messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"], unsafe_allow_html=True)

# Chat input

if query := st.chat_input("Ask about properties..."):
    # Append user message
    st.session_state.messages.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)

    # Call backend API
    summary = "No summary available."
    cards = []
    assistant_content = ""

    with st.chat_message("assistant"):
        with st.spinner("Searching properties..."):
            try:
                # Always run the local pipeline directly for Streamlit
                if run_query_pipeline is None:
                    raise RuntimeError(
                        "Local pipeline not available in this Streamlit app"
                    )
                try:
                    data = run_query_pipeline(query, use_gemini=False, top_k=5)
                except Exception as e:
                    raise RuntimeError(f"Local pipeline error: {e}")

                summary = data.get("summary", "No summary available.")
                cards = data.get("cards", [])
                filters = data.get("filters", {})
                results = data.get("results", [])

                # Display summary prominently
                st.markdown(f"**{summary}**")

                # Show parsed filters used by the pipeline for transparency
                with st.expander("Parsed filters used (click to expand)"):
                    st.json(filters)

                # Show raw results (list of dicts) for debugging and inspection
                if results:
                    with st.expander(f"Raw results ({len(results)})"):
                        st.json(results)

                # Render cards (UI-friendly view)
                if cards:
                    for card in cards:
                        st.markdown(
                            f"""
                        <div style='padding:15px; border:1px solid #ddd; border-radius:12px; margin-bottom:10px;'>
                            <h4>{card.get("title", "N/A")} – {card.get("price", "N/A")}</h4>
                            <p><b>Project:</b> {card.get("project_name", "N/A")}<br>
                            <b>Location:</b> {card.get("city_locality", "N/A")}<br>
                            <b>BHK:</b> {card.get("bhk", "N/A")} | 
                            <b>Possession:</b> {card.get("possession", "N/A")}<br>
                            <b>Amenities:</b> {", ".join(card.get("amenities", [])) or "Not listed"}<br>
                            <a href='{card.get("cta", "#")}' target='_blank'>View Project</a></p>
                        </div>
                        """,
                            unsafe_allow_html=True,
                        )
                else:
                    st.warning("No matching properties found.")

                # build assistant content for session history (include filters + top cards summary)
                assistant_content = f"Filters: {filters} \n\nSummary: {summary}"
                if cards:
                    assistant_content += "\n\nTop cards:\n"
                    for card in cards[:3]:
                        assistant_content += f"- {card.get('title', 'N/A')} — {card.get('price', 'N/A')}\n"
            except Exception as e:
                err_msg = f"Error calling backend: {e}"
                st.error(err_msg)
                assistant_content = err_msg

    # Store assistant message (ensure assistant_content is defined)
    st.session_state.messages.append(
        {"role": "assistant", "content": assistant_content}
    )
