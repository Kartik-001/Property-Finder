"""Generate short grounded summaries from filtered results."""

import pandas as pd


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

    # price min/max (from filtered results only)
    min_p = df["price_lakhs"].dropna()
    max_p = df["price_lakhs"].dropna()
    min_p_val = float(min_p.min()) if not min_p.empty else None
    max_p_val = float(max_p.max()) if not max_p.empty else None

    # possession distribution (canonicalize keys)
    poss_series = (
        df["possession_norm"].dropna().astype(str).str.replace(" ", "_").str.title()
    )
    ready_count = int((poss_series == "Ready").sum()) if not poss_series.empty else 0
    uc_count = (
        int((poss_series == "Under_Construction").sum()) if not poss_series.empty else 0
    )

    # most common locality (if any)
    localities = df["locality_norm"].dropna()
    top_locality = None
    if not localities.empty:
        top_locality = localities.value_counts().idxmax()

    parts = []
    # sentence 1: total matches (and optional city/bhk/budget context)
    s1 = f"{n} matching project{'s' if n > 1 else ''} found."
    parts.append(s1)

    # sentence 2: possession distribution
    s2_parts = []
    if ready_count:
        s2_parts.append(f"Ready: {ready_count}")
    if uc_count:
        s2_parts.append(f"Under_Construction: {uc_count}")
    if s2_parts:
        parts.append("Possession status — " + ", ".join(s2_parts) + ".")

    # sentence 3: price range
    if min_p_val is not None and max_p_val is not None:
        parts.append(
            f"Price range: {price_format_from_lakhs(min_p_val)} — {price_format_from_lakhs(max_p_val)}."
        )

    # sentence 4: top locality
    if top_locality:
        parts.append(f"Most listings are in {top_locality.title()}.")

    # join 2-4 short sentences, grounded in data
    return " ".join(parts)
