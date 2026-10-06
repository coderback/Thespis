"""The claim check (docs/cast-review.md, Phase 2): before a line with consequences is heard, what it claims is checked
against what its speaker could know, and a line that leaks, hallucinates, contradicts itself or fails to state what
its action asserts falls back to its template."""

import pytest

from games.crypt_road import claims as cr_claims
from games.crypt_road import rules
from games.crypt_road.content import new_world
from games.manor import rules as mn_rules
from games.manor.content import new_world as manor_world
from tests.test_model_voice import FakeModel, play_demo
from thespis import claims
from thespis.claims import CHECK_PROMPT, EXTRACT_PROMPT, ClaimCheck, ClaimChecking, checking_from_env
from thespis.expression import Mind, StatePack, Utterance, Validator
from thespis.gateway import ModelReply
from thespis.ledger import Claim

CHECKING = ClaimChecking()


def says(*found):
    """An extractor that finds these claims, (pred, a, b) or (pred, a, b, happened), in every line."""
    claims_ = [{"pred": c[0], "a": c[1], "b": c[2], "happened": c[3] if len(c) > 3 else True} for c in found]
    return lambda request: {"claims": claims_}


class Extractor:
    providers = models = ("x",)

    def __init__(self, extract):
        self.extract, self.calls = extract, []

    def complete(self, call_type, messages, schema=None):
        self.calls.append((call_type, schema))
        data = self.extract(messages)
        return None if data is None else ModelReply(data, "x", "x", 0.0)

    def complete_many(self, calls):
        return [self.complete(*c) for c in calls]


@pytest.fixture
def tavern():
    """The player insulted Kael before Mags and Odo, then a phase passed; Brenna, at the guard post, saw none of it."""
    w = new_world(1)
    rules.act(w, "insult", "kael")
    rules.act(w, "wait")
    return w


def pack(npc, asserted=None, stakes=True):
    return StatePack(npc=npc, name=npc.title(), persona="", goal="", situation="", here=[], drives={}, trust_in={},
                     beliefs=[], events=[{"id": "e0001", "what": "x"}], stakes=stakes, asserted=asserted)


def check(w, extract):
    return ClaimCheck(Extractor(extract), cr_claims.VOCABULARY, lambda p: cr_claims.facts(w, p.npc))


def test_what_the_speaker_could_know_passes(tavern):
    c = check(tavern, lambda m: {"claims": [{"pred": "insulted", "a": "player", "b": "kael", "happened": True},
                                            {"pred": "other", "a": "kael", "b": "a sore loser", "happened": True}]})
    assert c.problems([(pack("mags"), "You insulted Kael, and he's a sore loser.")]) == [None]


@pytest.mark.parametrize("npc,found,why", [
    ("brenna", ("insulted", "player", "kael"), "leak: insulted(player, kael)"),
    ("mags", ("robbed", "odo", "kael"), "hallucination: robbed(odo, kael)"),
    ("mags", ("insulted", "player", "kael", False), "contradiction: not insulted(player, kael)"),
])
def test_a_line_that_leaks_hallucinates_or_contradicts_is_refused(tavern, npc, found, why):
    c = check(tavern, lambda m: says(found)(m))
    assert c.problems([(pack(npc), "...")]) == [why]


def test_no_answer_from_the_extractor_refuses_the_line(tavern):
    assert check(tavern, lambda m: None).problems([(pack("mags"), "...")]) == ["unavailable"]
    assert check(tavern, lambda m: {"nothing": []}).problems([(pack("mags"), "...")]) == ["unavailable"]


def test_a_lie_the_game_chose_passes_and_must_be_stated():
    w = manor_world()
    mn_rules.act(w, "move", "kitchen")
    alibi = Claim("was_in", "sable", "kitchen@1")
    c = ClaimCheck(Extractor(says(("was_in", "sable", "kitchen@1"))), mn_rules.claims.VOCABULARY,
                   lambda p: mn_rules.claims.facts(w, p.npc))
    assert c.problems([(pack("sable", asserted=alibi), "The kitchen, all morning.")]) == [None]
    assert c.problems([(pack("sable"), "The kitchen, all morning.")]) == ["hallucination: was_in(sable, kitchen@1)"]
    vague = ClaimCheck(Extractor(says()), mn_rules.claims.VOCABULARY, lambda p: mn_rules.claims.facts(w, p.npc))
    assert vague.problems([(pack("sable", asserted=alibi), "Busy day.")]) == \
        ["doesn't state was_in(sable, kitchen@1)"]


def test_checking_asks_for_what_the_speaker_vouches_for():
    """Measuring counts a reported fact as asserted, as the paper did; checking counts only that it was reported."""
    assert EXTRACT_PROMPT != CHECK_PROMPT
    assert EXTRACT_PROMPT.replace("asserts both that the teller told the speaker", "") != EXTRACT_PROMPT
    assert "Leave out the fact reported" in CHECK_PROMPT and "Leave out the fact reported" not in EXTRACT_PROMPT
    schema = claims.extraction_schema(cr_claims.VOCABULARY)
    assert schema["properties"]["claims"]["items"]["properties"]["pred"]["enum"][-1] == "other"


# ---------------------------------------------------------------- in the Mind
def test_only_lines_with_stakes_are_checked():
    model = FakeModel()
    w = new_world(1)
    rules.act(w, "insult", "kael", gateway=model, checking=CHECKING)  # a reaction: no stakes
    assert [c for c, _ in model.calls] == ["react"]
    model = FakeModel()
    play_demo(model, checking=CHECKING)
    checked = [p["speaker"] for c, p in model.calls if c == "extract"]
    assert sorted(set(checked)) == ["brenna", "kael", "odo"]  # the accusation, the arrest, questioning, testimony
    assert all(s == claims.extraction_schema(cr_claims.VOCABULARY) for (c, _), s in zip(model.calls, model.schemas)
               if c == "extract")


def test_a_refused_line_falls_back_and_is_never_cached(tmp_path):
    from thespis.store import Store

    def accusing(request):  # Kael's accusation claims Odo robbed him, which never happened
        return {"claims": [{"pred": "robbed", "a": "odo", "b": "kael", "happened": True}]}             if request["speaker"] == "kael" else {"claims": []}

    cache = Store(tmp_path / "c.sqlite")
    w, _ = play_demo(FakeModel(extract=accusing), checking=CHECKING, cache=cache)
    accuse = next(d for d in w.decisions if d.chosen == "accuse:player")
    assert accuse.source == "fallback" and "claim check (hallucination: robbed(odo, kael))" in accuse.reason
    assert accuse.line and accuse.cites  # Kael's template accusation, which code wrote from his belief
    again = FakeModel(extract=accusing)
    play_demo(again, checking=CHECKING, cache=cache)
    assert [c for c, _ in again.calls] == ["act", "extract"]  # every line came from the cache but the refused one


def test_a_checked_line_is_cached_under_its_own_key(tmp_path):
    from thespis.store import Store

    cache = Store(tmp_path / "c.sqlite")
    first = FakeModel()
    play_demo(first, checking=CHECKING, cache=cache)
    again = FakeModel()
    play_demo(again, checking=CHECKING, cache=cache)
    assert any(c == "extract" for c, _ in first.calls) and again.calls == []  # hits are free, checks included
    unchecked = FakeModel()
    play_demo(unchecked, cache=cache)  # without the check, the lines with stakes are other entries
    assert sorted(c for c, _ in unchecked.calls) == ["act", "act", "act", "react"]  # accuse, detain, question, testify


def test_the_budget_covers_the_check():
    w = new_world(1)
    p = pack("mags")
    model = FakeModel(lambda kind, payload: {"cites": ["e1"], "line": "So."})
    u = Mind(model, Validator({}), budget=1, checker=check(w, says())).react_many(
        [(p, Utterance(None, "Hm.", ["e0001"], "fallback"))])[0]
    assert (u.source, u.note) == ("fallback", "model call cap reached: no claim check")
    mind = Mind(model, Validator({}), budget=2, checker=check(w, says()))
    assert mind.react_many([(p, Utterance(None, "Hm.", ["e0001"], "fallback"))])[0].source == "llm"
    assert mind.asked == 2


def test_the_narrator_can_tell_anything_that_happened_but_nothing_that_didnt():
    from games.crypt_road import narrator

    w = new_world(1)
    rules.act(w, "insult", "kael")
    rules.act(w, "wait")
    window = [e for e in w.ledger if e.phase == 0 and e.verb == "move"]  # it is told only the moves
    told = []
    for found in [("insulted", "player", "kael"), ("robbed", "player", "kael")]:
        c = ClaimCheck(Extractor(says(found)), cr_claims.VOCABULARY, lambda p: cr_claims.narrator_facts(w))
        told.append(narrator.narrate(Mind(FakeModel(), Validator({}), checker=c), window)[2])
    assert told == ["llm", "fallback"]  # the insult happened, outside its window; the robbery never did


def test_the_manors_lie_is_checked():
    def sable_says(found):
        return lambda request: says(*found)(request) if request["speaker"] == "sable" else {"claims": []}

    def asked(extract):
        w = manor_world()
        mn_rules.act(w, "move", "kitchen")
        mn_rules.act(w, "ask", "sable", "morning", gateway=FakeModel(extract=extract), checking=CHECKING)
        return [d for d in w.decisions if d.npc == "sable"][-1]

    assert asked(sable_says([("was_in", "sable", "kitchen@1")])).source == "llm"
    d = asked(sable_says([]))
    assert d.source == "fallback" and "doesn't state was_in(sable, kitchen@1)" in d.reason
    d = asked(sable_says([("was_in", "sable", "kitchen@1"), ("took", "pell", "ring")]))
    assert d.source == "fallback" and "hallucination: took(pell, ring)" in d.reason


# ---------------------------------------------------------------- configuration
def test_checking_from_the_environment():
    assert checking_from_env({}) is None  # off until it stops refusing lines it misreads
    assert checking_from_env({"CLAIM_CHECK": "consequential"}) == ClaimChecking("consequential", None)
    assert checking_from_env({"CLAIM_CHECK": "all"}).mode == "all"
    with pytest.raises(ValueError):
        checking_from_env({"CLAIM_CHECK": "sometimes"})
    own = checking_from_env({"CLAIM_CHECK": "consequential", "LLM_CHECK_BASE_URL": "https://check.test/v1",
                             "LLM_CHECK_API_KEY": "k", "LLM_CHECK_MODEL": "small"})
    assert own.gateway.models == ("small",)
    own.gateway.close()


def test_every_line_is_checked_when_asked():
    model = FakeModel()
    w = new_world(1)
    rules.act(w, "insult", "kael", gateway=model, checking=ClaimChecking("all"))
    assert [c for c, _ in model.calls] == ["react", "extract"]


def test_the_host_checks_only_when_asked(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from games.crypt_road.app import app
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.sqlite"))
    with TestClient(app):
        assert app.state.checking is None
    monkeypatch.setenv("CLAIM_CHECK", "consequential")
    with TestClient(app):
        assert app.state.checking == ClaimChecking("consequential", None)


def test_what_a_speaker_believes_tells_it_of_the_event_behind_it():
    """Lady Vane never saw Sable leave the study, but once she believes Pell, she knows of it: no leak."""
    w = manor_world()
    left = {"pred": "left", "a": "sable", "b": "study", "happened": True}
    assert claims.categorize(mn_rules.claims.VOCABULARY, left, mn_rules.claims.facts(w, "vane")) == "leak"
    for verb, target, topic in [("move", "study", None), ("ask", "pell", "morning"), ("move", "hall", None),
                                ("request_questioning", "pell", None)]:
        mn_rules.act(w, verb, target, topic)
    assert claims.categorize(mn_rules.claims.VOCABULARY, left, mn_rules.claims.facts(w, "vane")) == "grounded"


def test_checking_reads_journeys_and_who_is_addressed():
    assert "A journey \"from A to B\" asserts that they went to B" in CHECK_PROMPT
    assert "\"you\" in the line is them" in CHECK_PROMPT
    assert "A journey" not in EXTRACT_PROMPT  # measuring keeps the paper's prompt, so reports stay comparable
