"""One story, one weight; the one who started a losing story pays for it; and the loser is let go.

A newcomer's market village found three things that felt wrong: the honest gossip who passed on what a witness saw was
trusted less, as if she had lied; the player's one lie, heard from a friend and then from the player, counted twice
and got a man arrested; and a merchant kept a lie she had been shown false, believing it more than the truth."""

from thespis.api import Game, Session
from thespis.ledger import Claim

TOML = """
[game]
id = "market"
[places]
market = "the market"
gate = "the gatehouse"
[player]
start = "market"
[npc.rolf]
name = "Rolf"
start = "gate"
persona = "The captain of the watch."
goal = "Keep the peace"
trust_in = { bess = 3, nell = 2, finch = -3, player = 0 }
[npc.bess]
name = "Bess"
start = "market"
persona = "A spice merchant."
goal = "Sell her pepper"
trust_in = { finch = -1, player = 0 }
[npc.nell]
name = "Nell"
start = "market"
persona = "A barmaid."
goal = "Hear everything first"
trust_in = { finch = 1 }
[npc.finch]
name = "Finch"
start = "market"
persona = "A pickpocket."
goal = "Eat tonight"
[claims]
one_actor = ["stole_from"]
first_hand = 3
[words.claims]
stole_from = "{a} stole from {b}"
"""
GAME = Game.parse(TOML, "market")
TRUTH = {"pred": "stole_from", "a": "player", "b": "bess"}
LIE = {"pred": "stole_from", "a": "finch", "b": "bess"}


def belief(s: Session, npc: str, claim: dict):
    return s.world.beliefs.get(npc, Claim.from_json(claim))


def village() -> Session:
    """The player robs Bess in front of Finch, and tells Bess it was Finch. Finch tells Nell what he saw."""
    s = Session.new(GAME)
    s.observe("steal", "player", at="market", claim=TRUTH, witnesses=["finch"])
    s.observe("tell", "player", "bess", at="market", claim=LIE, said=True)
    s.observe("tell", "finch", "nell", at="market", claim=TRUTH, said=True)
    return s


def test_whoever_started_the_losing_story_pays_not_whoever_passed_it_on():
    s = village()
    s.observe("tell", "bess", "rolf", at="gate", claim=LIE, said=True)  # she passes on the player's lie
    s.observe("tell", "nell", "rolf", at="gate", claim=TRUTH, said=True)  # Nell passes on what Finch saw
    trust = s.world.npcs["rolf"].trust_in
    assert belief(s, "rolf", TRUTH).status == "retracted"  # Bess is trusted more: her story wins
    assert trust["nell"] == 2  # Nell only passed it on: she keeps his trust
    assert trust["finch"] == -5  # the story was Finch's: he pays, 2 down
    assert belief(s, "rolf", TRUTH).evidence[0].origin == ("finch",)


def test_one_story_by_two_mouths_counts_once():
    s = village()
    s.observe("tell", "bess", "rolf", at="gate", claim=LIE, said=True)  # the player's lie, from Bess: 0.9
    assert belief(s, "rolf", LIE).conf == 0.9
    s.update("player", loc="gate")
    s.observe("tell", "player", "rolf", at="gate", claim=LIE, said=True)  # and from the player: still one liar's word
    assert belief(s, "rolf", LIE).conf == 0.9
    s.observe("tell", "nell", "rolf", at="gate", claim=LIE, said=True)  # Nell's own word, if she said it, would add
    assert [e.story for e in belief(s, "rolf", LIE).evidence] == [("player",), ("player",), ("nell",)]


def test_the_losing_story_is_let_go_even_when_the_winner_is_weakly_held():
    s = village()
    s.observe("tell", "finch", "bess", at="market", claim=TRUTH, said=True)  # who saw it, though she distrusts him
    lie, truth = belief(s, "bess", LIE), belief(s, "bess", TRUTH)
    assert truth.active and truth.conf == 0.2  # his word is worth 0.2 to her, but he was there: his story wins
    assert lie.status == "retracted"  # the lie (0.4) used to stay active, above the truth: she keeps one story
    assert s.world.npcs["bess"].trust_in["player"] == -2  # and the player, whose lie it was, is caught


def test_an_old_save_without_origins_fuses_as_it_did():
    s = village()
    s.observe("tell", "bess", "rolf", at="gate", claim=LIE, said=True)
    snap = s.snapshot()
    for b in snap["world"]["beliefs"]:
        for e in b["evidence"]:
            e.pop("origin", None)  # saved before origins: each report is its teller's own story
    again = Session.restore(GAME, snap)
    assert belief(again, "rolf", LIE).conf == 0.9 and belief(again, "rolf", LIE).evidence[0].origin == ()
