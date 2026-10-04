"""#38: the minimal example uses only the core, and plays with no model at all."""

import ast
import runpy
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "minimal_client.py"


def test_the_minimal_example_runs_on_the_fallback(monkeypatch, capsys):
    for name in ("LLM_BASE_URL", "LLM_BACKUP_BASE_URL"):
        monkeypatch.setenv(name, "")  # set, so a local .env can't switch the model on
    runpy.run_path(str(EXAMPLE), run_name="__main__")
    out = capsys.readouterr().out
    assert out.startswith("Tamsin chooses report:player (fallback), citing ['b0001']")


def test_the_example_needs_nothing_from_a_game():
    tree = ast.parse(EXAMPLE.read_text(encoding="utf-8"))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    imported |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any(m.split(".")[0] == "games" for m in imported)
    assert {m for m in imported if m.startswith("thespis")} >= {"thespis.ledger", "thespis.expression"}
