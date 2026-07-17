"""CI guard: the store/sync/adapter core must contain zero ML- or
app-specific vocabulary as actual code (identifiers, string literals used as
logic) — not counting docstrings, which may use domain terms illustratively.
Only `redthread.adapters.examples` is allowed to know what an epoch is.
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "redthread"
EXCLUDED_PREFIXES = ("adapters/examples",)

BANNED_TERMS = [
    "epoch",
    "checkpoint",
    "val_acc",
    "test_acc",
    "train_loss",
    "hyperparam",
    "learning_rate",
    "coverage_pct",
    "bundle_size",
]


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    bodies = [tree.body] if hasattr(tree, "body") else []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Module):
            bodies.append(node.body)
    for body in bodies:
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            ids.add(id(body[0].value))
    return ids


def _code_vocabulary(source: str) -> set[str]:
    tree = ast.parse(source)
    skip = _docstring_ids(tree)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.arg):
            found.add(node.arg)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            found.add(node.name)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in skip
        ):
            found.add(node.value)
    return found


def _core_files() -> list[Path]:
    files = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        if any(rel.startswith(p) for p in EXCLUDED_PREFIXES):
            continue
        files.append(path)
    return files


@pytest.mark.parametrize("path", _core_files(), ids=lambda p: str(p.relative_to(SRC)))
def test_core_module_has_no_domain_vocabulary(path):
    vocabulary = {s.lower() for s in _code_vocabulary(path.read_text(encoding="utf-8"))}
    hits = [term for term in BANNED_TERMS if any(term in word for word in vocabulary)]
    assert not hits, f"{path.relative_to(SRC)} leaks domain vocabulary in code: {hits}"
