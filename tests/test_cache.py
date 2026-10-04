"""#18: validated model replies are cached, so a route played again costs no calls, and REPLAY=1 never calls out."""

import dataclasses

import pytest

from games.crypt_road import rules, voice
from games.crypt_road.content import new_world
from tests.test_model_voice import FakeModel, play_demo
from thespis import expression
from thespis.store import Store

KAEL_DECIDES = "You are at The Tavern. Decide what to do now."


class Offline(FakeModel):
    """A model that must never be called: replay means no network."""

    def complete(self, call_type, messages):
        raise AssertionError(f"a {call_type} call was made in replay mode")


@pytest.fixture
def cache(tmp_path):
    return Store(tmp_path / "cache.sqlite")


def spoken(w):
    """What every NPC chose and said, leaving out where it came from."""
    return [(d.kind, d.npc, d.phase, d.trigger, d.chosen, d.line, d.cites) for d in w.decisions]


def without_decisions(w):
    data = w.to_json()
    del data["decisions"]
    return data


def test_key_covers_model_prompt_version_call_type_and_pack(monkeypatch):
    w = new_world(1)
    pack = voice.pack_for(w, "kael", KAEL_DECIDES, {"go_to": 3.0, "wait": 1.0})
    key = pack.cache_key("gpt-6-luna", "decide")
    assert len(key) == 64
    assert voice.pack_for(w, "kael", KAEL_DECIDES, {"go_to": 3.0, "wait": 1.0}).cache_key("gpt-6-luna", "decide") == key
    reordered = dataclasses.replace(pack, drives=dict(reversed(pack.drives.items())))
    assert reordered.cache_key("gpt-6-luna", "decide") == key  # canonical: key order inside the pack doesn't matter
    others = [pack.cache_key("gpt-5.4-nano", "decide"), pack.cache_key("gpt-6-luna", "react"),
              dataclasses.replace(pack, persona="A gentle soul.").cache_key("gpt-6-luna", "decide"),
              dataclasses.replace(pack, situation="It is raining.").cache_key("gpt-6-luna", "decide")]
    monkeypatch.setattr(expression, "PROMPT_VERSION", expression.PROMPT_VERSION + 1)
    others.append(pack.cache_key("gpt-6-luna", "decide"))
    assert key not in others and len(set(others)) == len(others)


def test_a_second_play_makes_no_model_calls(cache):
    """#18's done-when: the demo route played twice calls the model only the first time, and plays the same."""
    first_model, second_model = FakeModel(), FakeModel()
    first, _ = play_demo(first_model, cache=cache)
    second, _ = play_demo(second_model, cache=cache)
    assert first_model.calls and second_model.calls == []
    assert cache.cached_replies() == len(first_model.calls)
    assert spoken(second) == spoken(first)
    assert [d.source for d in second.decisions] == [d.source.replace("llm", "cache") for d in first.decisions]
    assert without_decisions(second) == without_decisions(first)
    assert (second.status, second.ended_at) == ("won", 5)


def test_replay_plays_the_route_from_the_cache_alone(cache):
    """REPLAY=1 passes offline: the warmed route plays with no model call, exactly as it played live."""
    live, _ = play_demo(FakeModel(), cache=cache)
    replayed, _ = play_demo(Offline(), cache=cache, replay=True)
    assert spoken(replayed) == spoken(live)
    assert [d.source for d in replayed.decisions] == [d.source.replace("llm", "cache") for d in live.decisions]
    assert without_decisions(replayed) == without_decisions(live)


def test_replay_falls_back_on_a_miss(cache):
    w, _ = play_demo(Offline(), cache=cache, replay=True)
    assert (w.status, w.ended_at) == ("won", 5)  # the fallback route still wins
    assert all(d.source == "fallback" for d in w.decisions)
    assert any(d.reason.endswith("replay: not in the cache") for d in w.decisions)
    assert cache.cached_replies() == 0


def test_only_replies_that_pass_are_cached(cache):
    def bad_cites(call_type, pack):
        return {**FakeModel.good(call_type, pack), "cites": ["e9999"]}

    model = FakeModel(bad_cites)
    play_demo(model, cache=cache)
    assert model.calls and cache.cached_replies() == 0
    again = FakeModel(bad_cites)
    play_demo(again, cache=cache)
    assert len(again.calls) == len(model.calls)  # nothing was kept, so it asks again


def test_a_reply_cached_under_any_configured_model_is_used(cache):
    play_demo(FakeModel(), cache=cache)  # its replies come from "model"
    switched = FakeModel()
    switched.models = ("a-new-primary", "model")  # e.g. a new primary, with the old model kept as the backup
    play_demo(switched, cache=cache)
    assert switched.calls == []


def test_a_cached_reply_the_validator_now_rejects_is_a_miss(cache):
    w = new_world(1)
    rules.act(w, "insult", "kael")
    pack = voice.pack_for(w, "mags", 'The player says to you: "Hello."')
    cache.put_reply(pack.cache_key("model", "react"), "react", {"line": "Hi.", "cites": ["e9999"]}, "fake/model")
    model = FakeModel()
    u = expression.Mind(model, voice.VALIDATOR, cache).react_many(
        [(pack, expression.Utterance(None, "Hm.", [], "fallback"))])[0]
    assert (u.source, u.line, len(model.calls)) == ("llm", "So be it.", 1)


def test_the_cache_survives_a_restart_and_keeps_the_first_reply(tmp_path):
    path = tmp_path / "t.sqlite"
    Store(path).put_reply("k", "react", {"line": "First."}, "a/model")
    Store(path).put_reply("k", "react", {"line": "Second."}, "b/model")
    assert Store(path).get_reply("k") == ({"line": "First."}, "a/model")
    assert Store(path).get_reply("missing") is None


def test_replay_env_reaches_the_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from games.crypt_road.app import app
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.sqlite"))

    def insult(model):
        with TestClient(app) as client:  # each one a fresh app lifespan on the same database: a restart
            app.state.gateway = model
            session = client.post("/session", json={}).json()["session"]
            r = client.post("/act", json={"verb": "insult", "target": "kael"}, headers={"X-Session": session})
            return r.json()["replies"][0]

    monkeypatch.setenv("REPLAY", "1")
    assert insult(Offline())["source"] == "fallback"  # nothing cached yet, and no call made
    monkeypatch.setenv("REPLAY", "0")
    live = insult(FakeModel())
    monkeypatch.setenv("REPLAY", "1")
    replayed = insult(Offline())
    assert (live["source"], replayed["source"]) == ("llm", "cache")
    assert (replayed["line"], replayed["cites"]) == (live["line"], live["cites"])
