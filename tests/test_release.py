"""What a release needs before its tag is pushed: the package is thespis-sdk, and the changelog has a section for the
version the package says it is (tools/release_notes.py, which the release workflow runs)."""

import tomllib
from pathlib import Path

import thespis
from tools.release_notes import notes, version

ROOT = Path(__file__).resolve().parents[1]


def test_the_package_is_thespis_sdk_and_installs_as_thespis():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["name"] == "thespis-sdk"
    assert project["scripts"] == {"thespis": "thespis.__main__:main"}
    assert all(not dep.startswith("thespis[") for extra in project["optional-dependencies"].values() for dep in extra)


def test_the_changelog_has_the_version_the_package_says_it_is():
    assert version() == thespis.__version__
    assert notes(thespis.__version__, (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))


def test_notes_are_one_section_whatever_follows_the_number():
    log = "# Changelog\n\n## 0.2.0\n\nNew.\n\n## 0.1.0 (3 October 2026)\n\nOld.\n"
    assert notes("0.2.0", log) == "New."
    assert notes("0.1.0", log) == "Old."
    assert notes("0.1", log) is None
