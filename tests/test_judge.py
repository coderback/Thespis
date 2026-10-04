"""#37: the judge tool collects validated lines with their packs, plants canaries, and reports two labelled rates."""

import json

import httpx

from tests.test_model_voice import FakeModel
from thespis.gateway import OpenAICompatGateway, Provider
from tools import harness, judge


def fair_judge():
    """A stand-in judge: a line is consistent when every id it cites is in its state pack."""
    def answer(request):
        said = json.loads(json.loads(request.content)["messages"][1]["content"])
        pack, line = said["state_pack"], said["said"]
        ids = {x["id"] for x in pack["beliefs"] + pack["events"]}
        verdict = {"consistent": set(line["cites"]) <= ids, "in_character": True, "reason": "checked the cites"}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(verdict)}}]})
    return OpenAICompatGateway([Provider("judge", "https://judge.test/v1", "k", "judge-model")],
                               transport=httpx.MockTransport(answer))


def test_lines_are_collected_with_the_packs_they_were_spoken_from(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "unused.sqlite"))
    samples = judge.collect(FakeModel(), 12)
    assert len(samples) == 12
    assert all(s.line and set(s.cites) <= s.pack.ids for s in samples)
    assert {s.kind for s in samples} == {"decide", "react"}


def test_a_fair_judge_passes_real_lines_and_flags_every_canary(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "unused.sqlite"))
    samples = judge.collect(FakeModel(), 20)
    plants = judge.canaries(samples)
    assert plants and all(p.canary and not set(p.cites) & p.pack.ids for p in plants)
    verdicts = judge.judge(fair_judge(), samples + plants)
    s = judge.summarise(samples, verdicts[:len(samples)], plants, verdicts[len(samples):])
    assert (s["consistent"], s["in_character"], s["judged"]) == (20, 20, 20)
    assert s["caught"] == s["canaries_judged"] == len(plants) and not s["flagged"]
    text = judge.block(s, "speaker-model", "judge-model", "today")
    assert text.startswith(harness.START) and text.endswith(harness.END) and "Model-judged" in text


def test_the_block_is_replaced_in_place_and_kept_by_a_harness_rewrite():
    first = harness.START + "\nold numbers\n" + harness.END
    doc = harness.with_block("# Results\n\nharness text\n", first)
    assert doc.endswith(first + "\n") and "harness text" in doc
    second = harness.START + "\nnew numbers\n" + harness.END
    doc = harness.with_block(doc, second)
    assert "new numbers" in doc and "old numbers" not in doc and doc.count(harness.START) == 1
    rewritten = harness.with_block("# Results\n\nfresh harness text\n", harness.existing_block(doc))
    assert "fresh harness text" in rewritten and "new numbers" in rewritten
    assert harness.with_block("plain", None) == "plain"
