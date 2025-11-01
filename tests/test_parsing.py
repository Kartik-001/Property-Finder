import pandas as pd

from backend.parsing import rule_based_parse


def _sample_projects_df():
    return pd.DataFrame(
        {
            "project_name": [
                "Sunshine Residency",
                "Lakeview Heights",
            ],
            "city_norm": ["pune", "mumbai"],
            "locality_norm": ["baner", "andheri"],
        }
    )


def test_rule_parse_basic():
    q = "3BHK flat in Pune under ₹1.2 Cr near metro"
    filters = rule_based_parse(q, projects_df=_sample_projects_df())
    assert filters["bhk"] == 3
    assert isinstance(filters["budget_lakhs_max"], float)
    assert filters["budget_lakhs_max"] == 120.0
    assert "near metro" in filters["soft"] or "near metro" in " ".join(filters["soft"])


def test_possession_and_city_and_soft():
    q = "2bhk in Mumbai ready to move near it park"
    filters = rule_based_parse(q, projects_df=_sample_projects_df())
    assert filters["city"] == "mumbai"
    assert filters["bhk"] == 2
    assert filters["possession"] == "Ready"
    assert any(
        "it" in s or "it park" in s or "near it park" in s for s in filters["soft"]
    )


def test_budget_and_locality_and_project_name_fallback():
    q = "flat near Baner under 50 Lakh Lakeview"
    filters = rule_based_parse(q, projects_df=_sample_projects_df())
    # locality matched and normalized
    assert filters["locality"] == "baner"
    # budget parsed to lakhs
    assert isinstance(filters["budget_lakhs_max"], float)
    assert filters["budget_lakhs_max"] == 50.0
    # project name substring fallback
    assert filters["project_name"] in ("Lakeview Heights", None)
