"""Calibrating a stand-in judge against the reference (rehearsal/calibrate.py): kappa, kept lines, and a whole
calibration over real replayed lines with two scripted judges."""

import json

import pytest

from rehearsal import calibrate, measure
from rehearsal.__main__ import RECORDINGS, rehearse
from rehearsal.record import ReplayGateway
from rehearsal.scenarios import scenarios
from thespis.gateway import ModelReply


def test_kappa_discounts_agreement_by_chance():
    assert calibrate.kappa([True, True, False, False], [True, False, False, False]) == pytest.approx(0.5)
    assert calibrate.kappa([True, False] * 5, [True, False] * 5) == 1.0
    assert calibrate.kappa([False] * 10, [False] * 10) is None  # nothing to agree on beyond chance
    # 90% raw agreement, all of it on "fine": a judge that never says "bad" earns nothing
    assert calibrate.kappa([True] + [False] * 9, [False] * 10) == pytest.approx(0.0)


class Judge:
    """Says every line claims the player robbed Kael (a hallucination on most lines), or nothing at all."""

    providers = models = ("scripted",)

    def __init__(self, accuse: bool):
        self.accuse = accuse

    def complete_many(self, calls):
        claims = [{"pred": "robbed", "a": "player", "b": "kael", "happened": True}] if self.accuse else []
        return [ModelReply({"claims": claims}, "scripted", "scripted", 0.1) for _ in calls]


@pytest.fixture(scope="module")
def judged_lines(tmp_path_factory):
    """Real lines from replaying one crypt road scenario, judged by a reference that found nothing wrong."""
    gateway = ReplayGateway(json.loads(RECORDINGS.read_text(encoding="utf-8")))
    _, recorder, _ = rehearse(gateway, [s for s in scenarios() if s.game == "crypt_road"][:2], gateway.claim_check)
    lines = [s for s in recorder.samples if s["source"] == "llm" and s["line"]]
    measure.extract(Judge(accuse=False), lines, progress=lambda _: None)
    measure.categorise(lines, recorder.snapshots)
    path = tmp_path_factory.mktemp("kept") / "run.lines.json.gz"
    calibrate.keep(path, "reference", "now", "abc1234", lines, recorder.snapshots)
    return path, lines


def test_kept_lines_round_trip_with_only_the_snapshots_they_need(judged_lines):
    path, lines = judged_lines
    kept = calibrate.load(path)
    assert kept["judge"] == "reference" and len(kept["samples"]) == len(lines)
    assert set(kept["snapshots"]) == {s["snapshot"] for s in lines}


def test_agreement_on_nothing_is_undefined_and_a_judge_that_flags_at_random_scores_zero(judged_lines):
    path, _ = judged_lines
    same = calibrate.calibrate([path], "same", Judge(accuse=False), progress=lambda _: None)
    assert same["agreement"]["any_bad"]["agree"] == 1.0 and same["agreement"]["any_bad"]["kappa"] is None
    wild = calibrate.calibrate([path], "wild", Judge(accuse=True), progress=lambda _: None)
    a = wild["agreement"]
    assert a["any_bad"]["judge_yes"] > 0 and a["any_bad"]["reference_yes"] == 0 and a["any_bad"]["extra"] > 0
    assert a["any_bad"]["kappa"] == pytest.approx(0.0)  # it says "bad" no more knowingly than chance
    assert "kappa 0.00" in calibrate.describe(wild)


def test_a_report_says_how_far_its_judge_is_calibrated():
    report = json.loads((RECORDINGS.parent / "reports" / "local-gemma4-e4b.json").read_text(encoding="utf-8"))
    report["claims"]["judge"] = "qwen3.5-4b"
    assert "Judge calibration: none" in measure.markdown(report)
    report["claims"]["calibration"] = {"judge": "qwen3.5-4b", "reference": ["DeepSeek-V4-Pro"], "when": "2026-10-08",
                                       "agreement": {"n": 100, "any_bad": {"kappa": 0.71, "lo": 0.5, "hi": 0.85,
                                                                           "agree": 0.95}}}
    assert "kappa 0.71 [0.50, 0.85] (n=100, 95% raw agreement" in measure.markdown(report)
    report["claims"]["judge"] = "DeepSeek-V4-Pro"  # the reference needs no calibration line
    assert "Judge calibration" not in measure.markdown(report)


class Checklist(Judge):
    """Extracts a false accusation from every line, then, asked about it, says the line doesn't state it."""

    def __init__(self, stated: bool):
        super().__init__(accuse=True)
        self.stated = stated

    def complete_many(self, calls):
        return [ModelReply({"states": self.stated}, "scripted", "scripted", 0.1) if c[0] == "verify" else r
                for c, r in zip(calls, super().complete_many(calls))]


def test_the_checklist_pass_drops_claims_the_line_doesnt_state(judged_lines):
    path, _ = judged_lines
    unstated = calibrate.calibrate([path], "careful", Checklist(stated=False), progress=lambda _: None, verify=True)
    assert unstated["judge"] == "careful+verify" and unstated["agreement"]["any_bad"]["judge_yes"] == 0
    stated = calibrate.calibrate([path], "careful", Checklist(stated=True), progress=lambda _: None, verify=True)
    assert stated["agreement"]["any_bad"]["judge_yes"] > 0 and stated["disagreements"]
