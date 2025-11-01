"""Formatting helpers for results -> card dictionaries."""

import re

# quote_plus was used previously for CTA generation; slug generator now keeps slugs safe
import pandas as pd


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9\-]", "-", s.lower()).strip("-")


def price_format_from_lakhs(val):
    if pd.isna(val) or val is None:
        return "N/A"
    v = float(val)
    if v >= 100:
        return f"₹{v / 100:.2f} Cr"
    return f"₹{v:.2f} L"


def make_project_card(row: dict) -> dict:
    # row can be a Series or mapping
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

    # deterministic slug format: {project}-{locality}--{price-part}
    def _price_slug(val):
        try:
            if pd.isna(val) or val is None:
                return "price-na"
            v = float(val)
        except Exception:
            return "price-na"
        if v >= 100:
            cr = v / 100.0
            # replace decimal point with hyphen to keep slug safe
            return f"{cr:.2f}".replace(".", "-") + "-cr"
        # lakhs: prefer integer representation when possible
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


def results_to_cards(df):
    return [make_project_card(row) for _, row in df.iterrows()]
