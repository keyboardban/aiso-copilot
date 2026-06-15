"""Generate CODE_REFERENCE.md from the source tree.

Parses each Python file with `ast` (no import/execution of target code) and emits,
per module: its task (module docstring) and every public class/function with its
signature and docstring summary. Re-run after code changes to keep the reference
in sync:

    python scripts/gen_code_reference.py
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "CODE_REFERENCE.md"

# Logical ordering of packages/files (anything else is appended alphabetically).
PACKAGE_ORDER = [
    "src/config.py",
    "src/utils", "src/input", "src/crawler", "src/query", "src/retrieval",
    "src/audit", "src/search_console", "src/llm", "src/automation",
    "src/reports", "src/services",
    "api", "app",
]

PACKAGE_TASKS = {
    "src/utils": "Shared low-level helpers (tokenization, text).",
    "src/input": "Input validation and sample/demo data loading.",
    "src/crawler": "Fetching and parsing pages into the structured page object.",
    "src/query": "Query fan-out generation and bilingual intent/glossary logic.",
    "src/retrieval": "Chunking and the hybrid coverage retrieval engine.",
    "src/audit": "Rule-based audits and the score combiner.",
    "src/search_console": "Search Console CSV loading and opportunity scoring.",
    "src/llm": "Optional LLM provider abstraction (no_llm / openrouter / ollama).",
    "src/automation": "n8n workflow blueprint generation.",
    "src/reports": "Markdown report and JSON export.",
    "src/services": "Pipeline orchestration, metrics, run storage.",
    "api": "Optional FastAPI backend.",
    "app": "Streamlit dashboard.",
}


def fmt_args(a: ast.arguments) -> str:
    parts = []
    all_pos = a.posonlyargs + a.args
    ndef = len(a.defaults)
    off = len(all_pos) - ndef
    for i, arg in enumerate(all_pos):
        s = arg.arg
        if arg.annotation is not None:
            s += f": {ast.unparse(arg.annotation)}"
        if i >= off:
            s += f"={ast.unparse(a.defaults[i - off])}"
        parts.append(s)
        if a.posonlyargs and i == len(a.posonlyargs) - 1:
            parts.append("/")
    if a.vararg:
        parts.append("*" + a.vararg.arg)
    elif a.kwonlyargs:
        parts.append("*")
    for arg, d in zip(a.kwonlyargs, a.kw_defaults):
        s = arg.arg
        if arg.annotation is not None:
            s += f": {ast.unparse(arg.annotation)}"
        if d is not None:
            s += f"={ast.unparse(d)}"
        parts.append(s)
    if a.kwarg:
        parts.append("**" + a.kwarg.arg)
    return ", ".join(parts)


def summary(node) -> str:
    doc = ast.get_docstring(node)
    if not doc:
        return ""
    # first paragraph, whitespace-normalized
    para = doc.strip().split("\n\n")[0]
    return " ".join(para.split())


def py_files() -> list:
    files = []
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if any(part in (".venv", "__pycache__", "scripts") for part in rel.split("/")):
            continue
        if rel.endswith("__init__.py") or rel.startswith("tests/") or rel.startswith("evals/"):
            continue
        if rel == "conftest.py":
            continue
        files.append(rel)

    def sort_key(rel):
        for i, prefix in enumerate(PACKAGE_ORDER):
            if rel == prefix or rel.startswith(prefix + "/") or rel.startswith(prefix):
                return (i, rel)
        return (len(PACKAGE_ORDER), rel)

    return sorted(files, key=sort_key)


def package_of(rel: str) -> str:
    parts = rel.split("/")
    return "/".join(parts[:2]) if len(parts) > 2 else parts[0]


def render_function(node, lines, prefix="def"):
    sig = f"{node.name}({fmt_args(node.args)})"
    ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    lines.append(f"- **`{sig}{ret}`**" + (f" — {summary(node)}" if summary(node) else ""))


def render_file(rel: str, lines: list):
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    lines.append(f"### `{rel}`")
    mod_doc = summary(tree)
    if mod_doc:
        lines.append(f"\n_{mod_doc}_\n")
    funcs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and not n.name.startswith("_")]
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    if funcs:
        lines.append("**Functions**\n")
        for fn in funcs:
            render_function(fn, lines)
        lines.append("")
    for cls in classes:
        lines.append(f"**class `{cls.name}`**" + (f" — {summary(cls)}" if summary(cls) else ""))
        methods = [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and (not n.name.startswith("_") or n.name == "__init__")]
        for m in methods:
            render_function(m, lines)
        lines.append("")


def main():
    files = py_files()
    lines = [
        "# AISO Copilot — Code Reference",
        "",
        "Per-module task and per-function description, **auto-generated from "
        "docstrings** by `scripts/gen_code_reference.py` (parsed with `ast`, no "
        "code executed). Re-run that script after code changes to refresh.",
        "",
        f"Covers {len(files)} modules across `src/`, `api/`, and `app/`. For how "
        "the modules fit together see [ARCHITECTURE_DETAILED.md](ARCHITECTURE_DETAILED.md).",
        "",
        "## Contents",
        "",
    ]
    # group by package for the TOC
    seen_pkg = []
    for rel in files:
        pkg = package_of(rel)
        if pkg not in seen_pkg:
            seen_pkg.append(pkg)
    for pkg in seen_pkg:
        anchor = pkg.replace("/", "").replace(".", "")
        lines.append(f"- [`{pkg}`](#{anchor})")
    lines.append("")

    current_pkg = None
    for rel in files:
        pkg = package_of(rel)
        if pkg != current_pkg:
            current_pkg = pkg
            anchor = pkg.replace("/", "").replace(".", "")
            lines.append(f"\n<a id=\"{anchor}\"></a>")
            lines.append(f"## `{pkg}`")
            if pkg in PACKAGE_TASKS:
                lines.append(f"\n{PACKAGE_TASKS[pkg]}\n")
        render_file(rel, lines)

    OUT.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)} ({len(files)} modules)")


if __name__ == "__main__":
    main()
