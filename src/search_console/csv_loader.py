"""Load and normalize a Google Search Console performance CSV export.

CSV upload only — no Search Console API, no OAuth, no billing. Column names
are matched leniently (GSC export variants like 'Top queries', percent-string
CTRs, comma thousands separators) and problems are reported as messages, not
exceptions.
"""

import pandas as pd

_COLUMN_ALIASES = {
    "query": ["query", "top queries", "search query", "queries"],
    "page": ["page", "top pages", "url", "landing page", "address"],
    "clicks": ["clicks", "url clicks"],
    "impressions": ["impressions"],
    "ctr": ["ctr", "url ctr", "site ctr"],
    "position": ["position", "avg position", "average position", "avg. position"],
}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename = {}
    lowered = {str(c).strip().lower(): c for c in df.columns}
    for canonical, aliases in _COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lowered:
                rename[lowered[alias]] = canonical
                break
    return df.rename(columns=rename)


def _to_number(series: pd.Series) -> pd.Series:
    cleaned = (
        series.astype(str)
        .str.replace("%", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.replace("<", "", regex=False)
        .str.strip()
    )
    return pd.to_numeric(cleaned, errors="coerce")


def load_search_console_csv(source) -> dict:
    """Accepts a path, a file-like object (Streamlit upload), or a DataFrame.

    Returns {ok, df, issues, summary}; on failure df is None and issues
    explains what to fix.
    """
    issues = []
    try:
        if isinstance(source, pd.DataFrame):
            df = source.copy()
        else:
            df = pd.read_csv(source, encoding="utf-8-sig")
    except Exception as exc:
        return {"ok": False, "df": None, "summary": {},
                "issues": [f"Could not read CSV: {exc.__class__.__name__}: {exc}"]}

    df = _normalize_columns(df)
    if "query" not in df.columns:
        return {"ok": False, "df": None, "summary": {}, "issues": [
            "CSV needs a 'query' column (GSC performance export: query, page, "
            f"clicks, impressions, ctr, position). Found: {', '.join(map(str, df.columns))}"
        ]}

    for column, default in (("page", ""), ("clicks", 0), ("impressions", 0),
                            ("ctr", None), ("position", None)):
        if column not in df.columns:
            df[column] = default
            issues.append(f"Column '{column}' missing — filled with defaults.")

    df["query"] = df["query"].astype(str).str.strip()
    df["page"] = df["page"].astype(str).str.strip()
    for column in ("clicks", "impressions", "ctr", "position"):
        df[column] = _to_number(df[column])
    df["clicks"] = df["clicks"].fillna(0)
    df["impressions"] = df["impressions"].fillna(0)

    # derive CTR (as percent) where missing
    derived = (df["clicks"] / df["impressions"].replace(0, pd.NA) * 100)
    df["ctr"] = df["ctr"].fillna(derived)
    # normalize fraction-style CTR (0.0093) to percent (0.93)
    if df["ctr"].dropna().le(1).all() and df["ctr"].dropna().gt(0).any():
        df["ctr"] = df["ctr"] * 100
    df["ctr"] = df["ctr"].fillna(0).round(2)
    df["position"] = df["position"].fillna(0).round(1)

    df = df[df["query"].str.len() > 0].reset_index(drop=True)
    if df.empty:
        return {"ok": False, "df": None, "summary": {}, "issues": ["CSV contained no usable rows."]}

    total_impressions = float(df["impressions"].sum())
    weighted_position = (
        float((df["position"] * df["impressions"]).sum() / total_impressions)
        if total_impressions else 0.0
    )
    summary = {
        "rows": int(len(df)),
        "total_clicks": int(df["clicks"].sum()),
        "total_impressions": int(total_impressions),
        "avg_ctr": round(float(df["clicks"].sum()) / total_impressions * 100, 2) if total_impressions else 0.0,
        "avg_position_weighted": round(weighted_position, 1),
    }
    return {"ok": True, "df": df, "issues": issues, "summary": summary}
