"""Guard rail: the core must never depend on a game adapter."""

import ast
import pathlib

CORE = pathlib.Path(__file__).resolve().parents[1] / "thespis"


def test_core_does_not_import_games():
    offenders = []
    for path in CORE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if any(n == "games" or n.startswith("games.") for n in names):
                offenders.append(str(path.relative_to(CORE.parent)))
    assert not offenders, f"core imports a game adapter: {offenders}"
