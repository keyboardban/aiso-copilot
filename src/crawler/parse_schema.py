"""Extract structured data (JSON-LD, basic microdata) from HTML.

Implemented with plain json + BeautifulSoup rather than extruct so the core
stays dependency-light; extruct (requirements-local.txt) can be layered on
later for RDFa/microdata-heavy pages.
"""

import json
import re


def _collect_types(node, types: list) -> None:
    """Walk a JSON-LD structure collecting every @type value (handles @graph,
    nested entities, and list-valued @type)."""
    if isinstance(node, dict):
        node_type = node.get("@type")
        if isinstance(node_type, str):
            types.append(node_type)
        elif isinstance(node_type, list):
            types.extend(t for t in node_type if isinstance(t, str))
        for value in node.values():
            _collect_types(value, types)
    elif isinstance(node, list):
        for item in node:
            _collect_types(item, types)


def parse_json_ld_from_soup(soup) -> dict:
    """Return {json_ld: [objects], types: [str], parse_errors: [str]}."""
    blocks = []
    errors = []
    for script in soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)}):
        raw = script.string or script.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # one retry after stripping JS-style comments and trailing commas
            cleaned = re.sub(r"^\s*//.*$", "", raw, flags=re.M)
            cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
            try:
                data = json.loads(cleaned)
            except json.JSONDecodeError as exc:
                errors.append(f"JSON-LD block failed to parse: {exc.msg} (line {exc.lineno})")
                continue
        if isinstance(data, list):
            blocks.extend(d for d in data if isinstance(d, dict))
        elif isinstance(data, dict):
            blocks.append(data)

    types = []
    _collect_types(blocks, types)

    # de-duplicate while preserving order
    seen = set()
    unique_types = []
    for t in types:
        if t not in seen:
            seen.add(t)
            unique_types.append(t)

    return {"json_ld": blocks, "types": unique_types, "parse_errors": errors}


def parse_microdata_types(soup) -> list:
    """Very light microdata scan: collect schema.org itemtype values."""
    types = []
    for el in soup.find_all(attrs={"itemtype": True}):
        itemtype = el.get("itemtype", "")
        if "schema.org" in itemtype:
            name = itemtype.rstrip("/").rsplit("/", 1)[-1]
            if name and name not in types:
                types.append(name)
    return types
