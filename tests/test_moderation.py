"""Moderation both ways: player text before a model reads it, model lines before a player hears them."""

import json

import httpx
import pytest

from tests.test_model_voice import FakeModel
from thespis.expression import Mind, StatePack, Utterance, Validator
from thespis.moderation import (
    PASS,
    UNAVAILABLE,
    Blocklist,
    ContentSafety,
    Layered,
    NoModeration,
    Pace,
    Verdict,
    content_safety_from_env,
)

ENDPOINT = "https://safety.test"


def severities(**by_category):
    """A Content Safety answer: every category at 0 unless given."""
    cats = {"Hate": 0, "SelfHarm": 0, "Sexual": 0, "Violence": 0, **by_category}
    return httpx.Response(200, json={"blocklistsMatch": [],
                                      "categoriesAnalysis": [{"category": c, "severity": s} for c, s in cats.items()]})


def safety(answer, **kwargs):
    """A ContentSafety client whose service answers with `answer(text)`; every request is kept."""
    seen = []

    def handle(request):
        seen.append(request)
        result = answer(json.loads(request.content)["text"])
        if isinstance(result, Exception):
            raise result
        return result
    return ContentSafety(ENDPOINT, "the-key", transport=httpx.MockTransport(handle), **kwargs), seen


class Flags:
    """A moderator that flags any text containing one of its words, and counts what it was asked."""

    def __init__(self, *words, local=None):
        self.words, self.asked, self._local = words, [], local

    def check(self, texts):
        self.asked += texts
        return [Verdict(True, "test") if any(w in t for w in self.words) else PASS for t in texts]

    def local(self):
        return self._local or NoModeration()


# ---------------------------------------------------------------- the moderators
def test_the_blocklist_matches_whole_words_and_phrases_in_any_case():
    b = Blocklist(["darn", "blast it", " "])
    assert [v.flagged for v in b.check(["Darn you", "darning socks", "BLAST IT all", "blast"])] == \
        [True, False, True, False]
    assert Blocklist([]).check(["anything"]) == [PASS]


def test_content_safety_sends_the_text_with_its_key():
    cs, seen = safety(lambda text: severities())
    assert cs.check(["Out of my way."]) == [PASS]
    r = seen[0]
    assert str(r.url) == f"{ENDPOINT}/contentsafety/text:analyze?api-version=2024-09-01"
    assert r.headers["Ocp-Apim-Subscription-Key"] == "the-key"
    assert json.loads(r.content) == {"text": "Out of my way.", "categories": ["Hate", "SelfHarm", "Sexual", "Violence"]}


def test_a_category_at_its_threshold_is_flagged():
    answers = {"duel": severities(Violence=4), "gore": severities(Violence=6), "slur": severities(Hate=4),
               "mild": severities(Hate=2)}
    cs, _ = safety(lambda text: answers[text])
    assert cs.check(["duel", "gore", "slur", "mild"]) == [PASS, Verdict(True, "Violence 6"), Verdict(True, "Hate 4"),
                                                          PASS]


def test_thresholds_can_be_set_per_category():
    cs, _ = safety(lambda text: severities(Hate=2), thresholds={"Hate": 2})
    assert cs.check(["mild"]) == [Verdict(True, "Hate 2")]


@pytest.mark.parametrize("failure", [httpx.Response(500), httpx.Response(200, json={"oops": 1}),
                                     httpx.ConnectTimeout("slow")])
def test_it_fails_closed_and_asks_again_next_time(failure):
    cs, seen = safety(lambda text: failure)
    assert cs.check(["hello"]) == [Verdict(True, UNAVAILABLE)]
    cs.check(["hello"])
    assert len(seen) == 2  # an outage is never remembered as a verdict


def test_verdicts_are_remembered():
    cs, seen = safety(lambda text: severities())
    for text in ("a", "b", "a", "a"):
        cs.check([text])
    assert [json.loads(r.content)["text"] for r in seen] == ["a", "b"]


class Clock:
    """Time that moves only when something sleeps."""

    def __init__(self):
        self.now, self.slept = 0.0, []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(round(seconds, 3))
        self.now += seconds


def test_the_pace_spaces_requests_out():
    clock = Clock()
    pace = Pace(4, clock, clock.sleep)
    assert all(pace.take(2.0) for _ in range(3))
    assert clock.slept == [0.25, 0.25]  # the first goes at once, then one every quarter of a second
    clock.now += 5.0  # after a quiet spell the next goes at once
    assert pace.take(0.0) and clock.slept == [0.25, 0.25]
    assert not pace.take(0.1)  # a turn further off than the budget isn't waited for


def test_a_429_is_retried_once_after_the_wait_it_asks_for():
    clock, answers = Clock(), iter([httpx.Response(429, headers={"Retry-After": "1"}), severities()])
    cs, seen = safety(lambda text: next(answers), clock=clock, sleep=clock.sleep)
    assert cs.check(["hello"]) == [PASS] and len(seen) == 2 and 1.0 in clock.slept


def test_a_second_429_or_a_long_one_fails_closed():
    clock = Clock()
    cs, seen = safety(lambda text: httpx.Response(429, headers={"Retry-After": "1"}), clock=clock, sleep=clock.sleep)
    assert cs.check(["hello"]) == [Verdict(True, UNAVAILABLE)] and len(seen) == 2
    cs, seen = safety(lambda text: httpx.Response(429, headers={"Retry-After": "30"}), clock=clock, sleep=clock.sleep)
    assert cs.check(["hello"]) == [Verdict(True, UNAVAILABLE)] and len(seen) == 1  # 30 s is past the wait


def test_a_busy_service_fails_closed_rather_than_stalling_the_game():
    clock = Clock()
    cs, seen = safety(lambda text: severities(), rate=1, wait=0.5, clock=clock, sleep=clock.sleep)
    assert cs.check(["one"]) == [PASS]
    assert cs.check(["two"]) == [Verdict(True, UNAVAILABLE)] and len(seen) == 1  # its turn is a second off


def test_the_rate_comes_from_the_environment():
    env = {"CONTENT_SAFETY_ENDPOINT": ENDPOINT, "CONTENT_SAFETY_KEY": "k"}
    assert content_safety_from_env(env)._pace.rate == 4
    assert content_safety_from_env({**env, "CONTENT_SAFETY_RPS": "100"})._pace.rate == 100


def test_content_safety_has_no_offline_part():
    cs, seen = safety(lambda text: severities(Hate=6))
    assert cs.local().check(["anything"]) == [PASS] and not seen


def test_layers_check_in_order_and_the_first_flag_decides():
    offline, remote = Blocklist(["darn"]), Flags("gore")
    layered = Layered(offline, None, remote)
    assert layered.check(["darn it", "gore", "fine"]) == [Verdict(True, "blocklist"), Verdict(True, "test"), PASS]
    assert remote.asked == ["gore", "fine"]  # what the blocklist caught never left the server
    assert layered.local().check(["gore", "darn"]) == [PASS, Verdict(True, "blocklist")]
    assert str(Layered()) == "none"


def test_content_safety_comes_from_the_environment():
    assert content_safety_from_env({}) is None
    assert content_safety_from_env({"CONTENT_SAFETY_ENDPOINT": ENDPOINT}) is None
    cs = content_safety_from_env({"CONTENT_SAFETY_ENDPOINT": ENDPOINT + "/", "CONTENT_SAFETY_KEY": "k",
                                  "MODERATION_THRESHOLDS": '{"Violence": 4}'})
    assert cs.url.startswith(ENDPOINT + "/contentsafety") and cs.thresholds["Violence"] == 4


# ---------------------------------------------------------------- inside the Mind
def pack(untrusted=()):
    return StatePack(npc="kael", name="Kael", persona="Proud.", goal="Win", situation='The player says: "hi"',
                     here=[], drives={}, trust_in={}, beliefs=[], events=[{"id": "e0001", "what": "x"}],
                     names={"kael"}, untrusted=list(untrusted))


FALLBACK = Utterance(None, "Hm.", ["e0001"], "fallback")


class Cache:
    def __init__(self):
        self.replies = {}

    def get_reply(self, key):
        return self.replies.get(key)

    def put_reply(self, key, call_type, data, provider):
        self.replies.setdefault(key, (data, provider))


def mind(model, moderator, cache=None, **kw):
    return Mind(model, Validator({"kael": "kael"}), cache, moderator=moderator, **kw)


def test_flagged_player_text_never_reaches_the_model():
    model, mod = FakeModel(), Flags("filth")
    u = mind(model, mod).react_many([(pack(["some filth"]), FALLBACK), (pack(["hello"]), FALLBACK)])
    assert (u[0].source, u[0].note) == ("fallback", "player text flagged: test")
    assert u[1].source == "llm" and len(model.calls) == 1


def test_a_flagged_model_line_is_neither_heard_nor_cached():
    cache = Cache()
    model = FakeModel(lambda kind, p: {"line": "Something vile.", "cites": ["e1"]})
    u = mind(model, Flags("vile"), cache).react_many([(pack(), FALLBACK)])[0]
    assert (u.source, u.line, u.note) == ("fallback", "Hm.", "model reply rejected: moderation (test)")
    assert cache.replies == {}


def test_a_clean_line_is_cached_and_a_cache_hit_only_meets_the_offline_check():
    cache, remote = Cache(), Flags("never")
    first = mind(FakeModel(), remote, cache).react_many([(pack(), FALLBACK)])[0]
    assert first.source == "llm" and len(cache.replies) == 1 and remote.asked == ["So be it."]
    remote.asked.clear()
    again = mind(FakeModel(), remote, cache).react_many([(pack(), FALLBACK)])[0]
    assert again.source == "cache" and remote.asked == []
    offline = Flags(local=Flags("So be it"))
    assert mind(FakeModel(), offline, cache).react_many([(pack(), FALLBACK)])[0].note == \
        "cached reply rejected: moderation (test)"


def test_replay_never_asks_the_moderator():
    remote = Flags("x")
    u = mind(FakeModel(), remote, Cache(), replay=True).react_many([(pack(["hello"]), FALLBACK)])[0]
    assert u.note == "replay: not in the cache" and remote.asked == []


# ---------------------------------------------------------------- the games
@pytest.fixture
def app_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from games.crypt_road.app import app
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.sqlite"))
    with TestClient(app) as client:
        app.state.gateway = FakeModel()
        app.state.moderator = Flags("filth")
        yield app, client


def test_talk_with_flagged_text_gets_the_code_line(app_client):
    app, client = app_client
    headers = {"X-Session": client.post("/session", json={}).json()["session"]}
    client.post("/act", json={"verb": "insult", "target": "kael"}, headers=headers)  # something for Mags to cite
    clean = client.post("/act", json={"verb": "talk", "target": "mags", "text": "Seen anything?"}, headers=headers)
    assert clean.json()["replies"][0]["source"] == "llm"
    calls = len(app.state.gateway.calls)
    flagged = client.post("/act", json={"verb": "talk", "target": "mags", "text": "You filth."}, headers=headers)
    assert flagged.status_code == 200 and flagged.json()["replies"][0]["source"] == "fallback"
    assert len(app.state.gateway.calls) == calls  # the model never read it


def test_a_flagged_persona_is_refused(app_client):
    _, client = app_client
    headers = {"X-Session": client.post("/session", json={}).json()["session"]}
    r = client.post("/dev/persona", json={"npc": "kael", "persona": "A man of pure filth."}, headers=headers)
    assert r.status_code == 400 and r.json()["reason"] == "That persona can't be used; try another"
    assert client.post("/dev/persona", json={"npc": "kael", "persona": "Gruff."}, headers=headers).status_code == 200


def test_an_edited_persona_is_checked_as_player_text(app_client):
    app, client = app_client
    headers = {"X-Session": client.post("/session", json={}).json()["session"]}
    client.post("/dev/persona", json={"npc": "kael", "persona": "Speaks in riddles."}, headers=headers)
    client.post("/act", json={"verb": "insult", "target": "kael"}, headers=headers)
    assert "Speaks in riddles." in app.state.moderator.asked


def test_the_server_has_no_moderation_unless_configured(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from games.crypt_road.app import app
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.sqlite"))
    monkeypatch.delenv("CONTENT_SAFETY_ENDPOINT", raising=False)
    with TestClient(app):
        assert str(app.state.moderator) == "none" and str(app.state.manor_moderator) == "none"
    monkeypatch.setenv("CONTENT_SAFETY_ENDPOINT", ENDPOINT)
    monkeypatch.setenv("CONTENT_SAFETY_KEY", "k")
    with TestClient(app):
        assert str(app.state.moderator).startswith("Azure AI Content Safety")
