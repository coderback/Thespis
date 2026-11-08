"""The quickstart (examples/quickstart): it runs on the fallback with only `thespis.api`, does what the README says it
does, and the README shows its code as it is."""

import ast
import re
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "examples" / "quickstart" / "quickstart.py"


def run(monkeypatch, capsys) -> list[str]:
    for name in ("LLM_BASE_URL", "LLM_BACKUP_BASE_URL"):
        monkeypatch.setenv(name, "")  # set, so a local .env can't switch the model on
    runpy.run_path(str(SCRIPT), run_name="__main__")
    return capsys.readouterr().out.splitlines()


def test_mara_refuses_the_thief_and_the_lie_falls(monkeypatch, capsys):
    out = run(monkeypatch, capsys)
    assert out[0].startswith("Mara: Not you. I know what you did.  (refuse:player scores ")
    held = {re.sub(r" at [\d.]+, from.*", "", line.strip()): float(re.search(r" at ([\d.]+),", line).group(1))
            for line in out[1:]}
    wat, edda, mara = (held[f"{n} active: player stole_from mara"] for n in ("wat", "edda", "mara"))
    assert wat == 1.0 > edda > mara > 0.5  # weaker with each mouth, and still enough to act on
    assert held["mara retracted: wat stole_from mara"] < 0.5  # the lie loses to the story from her friend


def test_it_needs_only_the_public_api():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    imported |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert {m for m in imported if m.split(".")[0] in ("thespis", "games", "tools", "rehearsal")} == {"thespis.api"}


def test_the_readme_shows_the_script_as_it_is():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    shown = re.search(r"<!-- quickstart:start -->\n```python\n(.*?)```\n<!-- quickstart:end -->", readme, re.S)
    assert shown, "the README's quickstart block is missing"
    code = SCRIPT.read_text(encoding="utf-8")
    body = code[code.index('"""', 3) + 3 :].lstrip("\n")  # the script without its docstring
    assert shown.group(1) == body
