"""Recall by meaning (thespis.recall): an NPC's pack holds what bears on the moment, chosen from only what it knows,
the same every time; without an embedder, the usual pack."""

import hashlib
import json
import math
import re
from pathlib import Path

import httpx

from thespis.api import Game, Session
from thespis.recall import CachedEmbedder, HttpEmbedder, embedder_from_env

ROOT = Path(__file__).resolve().parents[1]
HAMLET = Game.load(ROOT / "examples" / "hamlet" / "game.toml")
CHEAT = {"pred": "cheated", "a": "ada", "b": "osric"}


class Words:
    """A stand-in embedder: each word hashed into 64 dimensions, so texts sharing words are close. Counts calls."""

    def __init__(self):
        self.calls, self.texts = 0, 0

    def embed(self, texts):
        self.calls += 1
        self.texts += len(texts)
        out = []
        for t in texts:
            v = [0.0] * 64
            for word in re.findall(r"[a-z]+", t.lower()):
                v[int(hashlib.md5(word.encode()).hexdigest(), 16) % 64] += 1.0
            out.append(v)
        return out


class Broken:
    def embed(self, texts):
        raise ConnectionError("down")


def busy_mill(s: Session) -> None:
    """Ada cheats Osric, then the mill fills with six events that have nothing to do with her."""
    s.observe("cheat", "ada", "osric", claim=CHEAT)
    for _ in range(3):
        s.observe("help", "maud", "hild", at="mill", witnesses=["osric"],
                  claim={"pred": "helped", "a": "maud", "b": "hild"})
        s.observe("help", "hild", "maud", at="mill", witnesses=["osric"],
                  claim={"pred": "helped", "a": "hild", "b": "maud"})


def test_without_an_embedder_the_pack_is_the_usual_one():
    plain, declared = Session.new(HAMLET), Session.new(HAMLET, embedder=None)
    for s in (plain, declared):
        busy_mill(s)
    assert declared.voice.recall is None
    assert [e["id"] for e in plain.voice.pack(plain.world, "osric", "x").events] == \
        ["e0003", "e0004", "e0005", "e0006", "e0007"]  # the latest five: Ada's cheating has dropped out


def test_what_bears_on_the_moment_is_recalled_though_older():
    s = Session.new(HAMLET, embedder=Words())
    busy_mill(s)
    pack = s.voice.pack(s.world, "osric", "Ada is back at the counter, asking for flour.")
    assert "e0001" in [e["id"] for e in pack.events]  # Ada cheated him: old, but it's Ada at the counter
    assert [e["id"] for e in pack.events] == sorted(e["id"] for e in pack.events)  # still oldest first
    assert pack.beliefs[0]["claim"] == "Ada cheated Osric"


def test_nothing_the_npc_never_knew_is_recalled():
    s = Session.new(HAMLET, embedder=Words())
    s.observe("cheat", "ada", "hild", at="forge", claim={"pred": "cheated", "a": "ada", "b": "hild"})  # Osric's away
    s.observe("help", "maud", "osric", claim={"pred": "helped", "a": "maud", "b": "osric"})
    pack = s.voice.pack(s.world, "osric", "Ada cheated Hild at the forge.")  # the very words of what he didn't see
    assert [e["id"] for e in pack.events] == ["e0002"] and pack.beliefs[0]["claim"] == "Maud helped Osric"


def test_the_same_moment_recalls_the_same_and_embeds_each_text_once():
    words = Words()
    s = Session.new(HAMLET, embedder=CachedEmbedder(words))
    busy_mill(s)
    first = s.voice.pack(s.world, "osric", "Ada is back at the counter.").payload()
    texts = words.texts
    assert s.voice.pack(s.world, "osric", "Ada is back at the counter.").payload() == first
    assert words.texts == texts  # every text was cached


def test_an_embedder_that_fails_costs_nothing_but_recall():
    s, plain = Session.new(HAMLET, embedder=Broken()), Session.new(HAMLET)
    for x in (s, plain):
        busy_mill(x)
    assert s.voice.pack(s.world, "osric", "Ada?").payload() == plain.voice.pack(plain.world, "osric", "Ada?").payload()


def test_any_openai_compatible_embeddings_endpoint():
    def answer(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "bge-small" and request.url.path == "/v1/embeddings"
        data = [{"index": i, "embedding": [float(len(t)), 1.0]} for i, t in reversed(list(enumerate(body["input"])))]
        return httpx.Response(200, json={"data": data})
    e = HttpEmbedder("http://127.0.0.1:9/v1", "bge-small", transport=httpx.MockTransport(answer))
    assert e.embed(["ab", "abcd"]) == [[2.0, 1.0], [4.0, 1.0]]  # in the order asked, whatever order they came
    assert embedder_from_env({}) is None
    assert isinstance(embedder_from_env({"EMBED_BASE_URL": "http://x/v1", "EMBED_MODEL": "m"}), CachedEmbedder)
    assert math.isclose(sum(x * x for x in Words().embed(["a b"])[0]), 2.0)
