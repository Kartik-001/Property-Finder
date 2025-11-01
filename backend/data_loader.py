"""Load and normalize CSV data; provide cached datasets."""

from __future__ import annotations
import os
import re
from functools import lru_cache
from typing import Tuple, Optional, List
import pandas as pd


def _repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _data_dir() -> str:
    return os.path.join(_repo_root(), "data")


def _read_csv(fname: str) -> pd.DataFrame:
    path = os.path.join(_data_dir(), fname)
    # read loosely to tolerate minor CSV inconsistencies in the dataset
    try:
        return pd.read_csv(path, encoding="utf-8", on_bad_lines="skip")
    except TypeError:
        # older pandas versions used error_bad_lines kw; fall back
        return pd.read_csv(path, encoding="utf-8", engine="python")


def parse_price_to_lakhs(price_str):
    if pd.isna(price_str):
        return None
    s = str(price_str).strip().lower().replace("₹", "").replace(",", "")
    # crore
    if "cr" in s or "crore" in s:
        m = re.findall(r"\d+\.?\d*", s)
        if not m:
            return None
        return float(m[0]) * 100.0
    # lakh
    if "lakh" in s or re.search(r"\b\d+\.?\d*\s*l\b", s):
        m = re.findall(r"\d+\.?\d*", s)
        if not m:
            return None
        return float(m[0])
    # thousands
    if "k" in s and not s.endswith("k"):
        # avoid matching '2k' as lakhs; fallback
        pass
    try:
        v = float(s)
        if v > 100000:
            return v / 100000.0
        return v
    except Exception:
        return None


def normalize_bhk(bhk_str):
    if pd.isna(bhk_str):
        return None
    s = str(bhk_str).strip().lower()
    if "studio" in s:
        return 0
    m = re.search(r"(\d+)", s)
    if m:
        return int(m.group(1))
    try:
        return int(float(s))
    except Exception:
        return None


# module level cache for fast repeated loads
_CACHED_DF: Optional[pd.DataFrame] = None


def _first_existing_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    """Return first candidate that exists in df.columns (case-insensitive already lowered)."""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def load_data() -> pd.DataFrame:
    """Load, normalize and return projects DataFrame (cached).

    - Reads CSVs from data/ using `_read_csv`
    - Normalizes column names to lowercase and stripped
    - Parses prices into `price_lakhs`
    - Normalizes BHK into `bhk`
    - Extracts `city_norm` and `locality_norm` from address fields
    - Returns a cached DataFrame (a copy is returned to callers)
    """
    global _CACHED_DF
    if _CACHED_DF is not None:
        return _CACHED_DF.copy()

    project_df = _read_csv("project.csv")
    address_df = _read_csv("ProjectAddress.csv")
    config_df = _read_csv("ProjectConfiguration.csv")
    variant_df = _read_csv("ProjectConfigurationVariant.csv")

    # normalize column names: strip + lowercase
    for df in [project_df, address_df, config_df, variant_df]:
        df.columns = df.columns.str.strip().str.lower()
        # clean string columns
        for col in df.select_dtypes(["object"]):
            df[col] = df[col].astype(str).str.strip()

    # harmonize price column name in variant_df
    price_col = _first_existing_column(variant_df, ["price", "price_lakhs", "amount"])
    if price_col is not None:
        variant_df["price_lakhs"] = variant_df[price_col].apply(parse_price_to_lakhs)
    else:
        variant_df["price_lakhs"] = None

    # bhk normalization: check several possibilities
    bhk_source = _first_existing_column(
        config_df, ["custombhk", "custom_bhk", "bhk", "type"]
    )
    if bhk_source is not None:
        config_df["bhk_norm"] = config_df[bhk_source].apply(normalize_bhk)
    else:
        config_df["bhk_norm"] = None

    # possession/status
    status_col = _first_existing_column(project_df, ["status", "possession"])
    if status_col is not None:
        project_df["possession_norm"] = (
            project_df[status_col]
            .astype(str)
            .str.lower()
            .replace(
                {
                    "ready to move": "ready",
                    "ready_to_move": "ready",
                    "ready-to-move": "ready",
                    "under construction": "under construction",
                    "uc": "under construction",
                }
            )
        )
    else:
        project_df["possession_norm"] = None

    # Merge step-by-step using lowered column names
    merged = project_df.copy()

    # address: find full address field
    address_full_col = (
        _first_existing_column(
            address_df, ["fulladdress", "full_address", "address", "fulladdressline"]
        )
        or "fulladdress"
    )
    address_cols = [
        c
        for c in ["projectid", "landmark", address_full_col, "pincode"]
        if c in address_df.columns
    ]
    if address_cols:
        merged = pd.merge(
            merged,
            address_df[address_cols],
            left_on="id",
            right_on="projectid",
            how="left",
        )

    # config merge
    config_cols = [
        c
        for c in [
            "id",
            "projectid",
            "propertycategory",
            "type",
            "custombhk",
            "bhk_norm",
        ]
        if c in config_df.columns
    ]
    config_renamed = (
        config_df[config_cols].rename(
            columns={"id": "configid", "projectid": "projectid_config"}
        )
        if config_cols
        else config_df
    )
    if "projectid_config" in config_renamed.columns:
        merged = pd.merge(
            merged,
            config_renamed,
            left_on="id",
            right_on="projectid_config",
            how="left",
        )

    # variant merge
    variant_cols = [
        c
        for c in ["id", "configurationid", "bathrooms", "price_lakhs"]
        if c in variant_df.columns
    ]
    variant_renamed = (
        variant_df[variant_cols].rename(columns={"id": "variantid"})
        if variant_cols
        else variant_df
    )
    if "configurationid" in variant_renamed.columns and "configid" in merged.columns:
        merged = pd.merge(
            merged,
            variant_renamed,
            left_on="configid",
            right_on="configurationid",
            how="left",
        )

    # extract city/locality from full address
    def extract_city_locality(full_address):
        if pd.isna(full_address):
            return None, None
        parts = [p.strip() for p in str(full_address).split(",") if p.strip()]
        if len(parts) >= 2:
            locality = parts[-2].lower()
            city = parts[-1].lower()
            return city, locality
        if len(parts) == 1:
            return None, parts[-1].lower()
        return None, None

    merged["city_norm"], merged["locality_norm"] = zip(
        *merged[address_full_col].apply(extract_city_locality)
    )

    # select and canonicalize columns
    keep: List[str] = []
    if "id" in merged.columns:
        keep.append("id")
    # prefer projectname variants
    proj_name_col = (
        _first_existing_column(merged, ["projectname", "project_name", "name"]) or None
    )
    if proj_name_col and proj_name_col in merged.columns:
        keep.append(proj_name_col)
    for c in [
        "city_norm",
        "locality_norm",
        "bhk_norm",
        "price_lakhs",
        "possession_norm",
    ]:
        if c in merged.columns:
            keep.append(c)

    df = merged[keep].drop_duplicates()

    # rename to canonical names
    rename_map = {}
    if "id" in df.columns:
        rename_map["id"] = "project_id"
    if proj_name_col and proj_name_col in df.columns:
        rename_map[proj_name_col] = "project_name"
    if "bhk_norm" in df.columns:
        rename_map["bhk_norm"] = "bhk"
    df = df.rename(columns=rename_map)

    # ensure bhk numeric
    if "bhk" in df.columns:
        df["bhk"] = pd.to_numeric(df["bhk"], errors="coerce")

    final_cols = [
        "project_id",
        "project_name",
        "city_norm",
        "locality_norm",
        "bhk",
        "price_lakhs",
        "possession_norm",
    ]
    for c in final_cols:
        if c not in df.columns:
            df[c] = None

    # cache and return a copy to callers to avoid accidental mutation
    _CACHED_DF = df[final_cols].copy()
    return _CACHED_DF.copy()


@lru_cache(maxsize=1)
def load_merged_projects() -> pd.DataFrame:
    """Load and normalize the CSVs and return a single `projects_df` like in the notebook.

    Returns: DataFrame with columns: project_id, project_name, city_norm, locality_norm, bhk, price_lakhs, possession_norm
    """
    project_df = _read_csv("project.csv")
    address_df = _read_csv("ProjectAddress.csv")
    config_df = _read_csv("ProjectConfiguration.csv")
    variant_df = _read_csv("ProjectConfigurationVariant.csv")

    # basic cleanup
    for df in [project_df, address_df, config_df, variant_df]:
        df.columns = df.columns.str.strip()
        for col in df.select_dtypes(["object"]):
            df[col] = df[col].astype(str).str.strip()

    # normalize price
    variant_df["price_lakhs"] = variant_df["price"].apply(parse_price_to_lakhs)

    # normalize bhk
    if "customBHK" in config_df.columns:
        config_df["bhk_norm"] = config_df["customBHK"].apply(normalize_bhk)
    else:
        config_df["bhk_norm"] = config_df["type"].apply(normalize_bhk)

    # possession
    if "status" in project_df.columns:
        project_df["possession_norm"] = (
            project_df["status"]
            .astype(str)
            .str.lower()
            .replace(
                {
                    "ready to move": "ready",
                    "ready_to_move": "ready",
                    "ready-to-move": "ready",
                    "under construction": "under construction",
                    "uc": "under construction",
                }
            )
        )
    else:
        project_df["possession_norm"] = None

    # Merge step-by-step
    merged = project_df.copy()
    address_cols = ["projectId", "landmark", "fullAddress", "pincode"]
    address_keep = [c for c in address_cols if c in address_df.columns]
    merged = pd.merge(
        merged, address_df[address_keep], left_on="id", right_on="projectId", how="left"
    )

    config_cols = [
        c
        for c in [
            "id",
            "projectId",
            "propertyCategory",
            "type",
            "customBHK",
            "bhk_norm",
        ]
        if c in config_df.columns
    ]
    config_renamed = config_df[config_cols].rename(
        columns={"id": "configId", "projectId": "projectId_config"}
    )
    merged = pd.merge(
        merged, config_renamed, left_on="id", right_on="projectId_config", how="left"
    )

    variant_cols = [
        c
        for c in ["id", "configurationId", "bathrooms", "price_lakhs"]
        if c in variant_df.columns
    ]
    variant_renamed = variant_df[variant_cols].rename(columns={"id": "variantId"})
    merged = pd.merge(
        merged,
        variant_renamed,
        left_on="configId",
        right_on="configurationId",
        how="left",
    )

    # extract city/locality from fullAddress
    def extract_city_locality(full_address):
        if pd.isna(full_address):
            return None, None
        parts = [p.strip() for p in str(full_address).split(",") if p.strip()]
        if len(parts) >= 2:
            locality = parts[-2].lower()
            city = parts[-1].lower()
            return city, locality
        if len(parts) == 1:
            return None, parts[-1].lower()
        return None, None

    merged["city_norm"], merged["locality_norm"] = zip(
        *merged["fullAddress"].apply(extract_city_locality)
    )

    # select columns
    keep = []
    # use existing key names if present
    if "id" in merged.columns:
        keep.append("id")
    if "projectName" in merged.columns:
        keep.append("projectName")
    for c in [
        "city_norm",
        "locality_norm",
        "bhk_norm",
        "price_lakhs",
        "possession_norm",
    ]:
        if c in merged.columns:
            keep.append(c)

    df = merged[keep].drop_duplicates()
    # rename to canonical
    rename_map = {}
    if "id" in df.columns:
        rename_map["id"] = "project_id"
    if "projectName" in df.columns:
        rename_map["projectName"] = "project_name"
    if "bhk_norm" in df.columns:
        rename_map["bhk_norm"] = "bhk"
    df = df.rename(columns=rename_map)

    # ensure bhk is numeric
    if "bhk" in df.columns:
        df["bhk"] = pd.to_numeric(df["bhk"], errors="coerce")

    # keep final columns expected by the rest of the package
    final_cols = [
        "project_id",
        "project_name",
        "city_norm",
        "locality_norm",
        "bhk",
        "price_lakhs",
        "possession_norm",
    ]
    for c in final_cols:
        if c not in df.columns:
            df[c] = None

    return df[final_cols]


def load_projects_df() -> pd.DataFrame:
    """Backward compatible alias used in tests and other modules."""
    return load_data()


if __name__ == "__main__":
    print(load_projects_df().head())
