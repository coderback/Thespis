"""Before the Ice Goes Out: the case plays as the design says (docs/before-the-ice-goes-out.md).

The game file is games/before-the-ice/coldwater.toml and the world's side is case.json beside it, which the Godot game
reads too. With no model the minds are deterministic, so each ending is a short scene played here: the calls the
game makes, and what the town comes to believe and do."""

import json
from pathlib import Path

import pytest

from thespis.api import Game, Session
from thespis.ledger import Claim

HERE = Path(__file__).resolve().parents[1] / "games" / "before-the-ice"
GAME = Game.load(HERE / "coldwater.toml")
CASE = json.loads((HERE / "case.json").read_text(encoding="utf-8"))
## What a seed can make of the week: draw -> option name -> the option (case.json's week; case.gd rolls it).
WEEK = {d["name"]: {o["name"]: o for o in d["options"]} for d in CASE["week"]["draws"]}
## The week most seeds come near: the heaviest option of each draw, Martha not seeing the face.
USUAL = {d: max(opts.values(), key=lambda o: o["weight"])["name"] for d, opts in WEEK.items()}

ALIBI = {"pred": "with_vera", "a": "player"}
NO_ALIBI = {**ALIBI, "neg": True}
LANTERN = {"pred": "lantern", "a": "someone"}


def fired(who: str) -> dict:
    return {"pred": "fired", "a": who, "b": "otto"}


def lantern(who: str) -> dict:
    return {"pred": "lantern", "a": who}


def observe(s: Session, o: dict) -> None:
    o = {k: v for k, v in o.items() if k not in ("note", "id")}
    s.observe(o.pop("verb"), o.pop("actor"), o.pop("target", None), **o)


def week(face: bool = False, seed: int = 1, **drawn: str) -> Session:
    """The morning of day 1: the night of the fire, as each saw their piece of it, in a week a seed might make: the
    usual one, but for the draws given (by name, a space as _), as case.gd plays it."""
    picks = {**USUAL, "face": "seen" if face else "not seen", **{k.replace("_", " "): v for k, v in drawn.items()}}
    options = [WEEK[d][picks[d]] for d in WEEK]
    see: dict[str, list] = {}
    for o in options:
        for event, who in o.get("see", {}).items():
            see.setdefault(event, []).extend(who)
    s = Session.new(GAME, seed=seed)
    for o in CASE["night"]:
        observe(s, {**o, "witnesses": o.get("witnesses", []) + see.get(o.get("id", ""), [])})
    for o in options:
        for x in o.get("observe", ()):
            observe(s, x)
        for a, b, kind in o.get("tie", ()):
            s.tie(a, b, kind)
        for npc, change in o.get("update", {}).items():
            s.update(npc, **change)
    return s


def remember(s: Session, stage: str) -> None:
    """Tamás sees a piece of the night again: the lantern, or a face (whose: an option of the week's draw)."""
    for o in CASE["tamas"]["lantern"]["observe"] if stage == "lantern" else WEEK["whose face"][stage]["remember"]:
        observe(s, o)


def conf(s: Session, npc: str, claim: dict) -> float:
    b = s.world.beliefs.get(npc, Claim.from_json(claim))
    return 0.0 if b is None or b.status != "active" else round(b.conf, 2)


def say(s: Session, to: str, claim: dict, at: str, speaker: str = "player", witnesses=()) -> None:
    s.observe("tell", speaker, to, at=at, claim=claim, said=True, witnesses=list(witnesses))


def evening(s: Session, teller: str = "Billy Tuck") -> str:
    return s.decide("gilchrist", "evening", bindings={"teller": teller}).action


def steamer(s: Session) -> str:
    return s.decide("gilchrist", "steamer").action


# ---------------------------------------------------------------- the file and the night
def test_the_game_has_nine_people_and_the_case_names_only_them():
    assert sorted(GAME.cast.data["npc"]) == sorted(CASE["everyone"])
    assert set(CASE["flags"].values()) <= set(GAME.places)


def test_the_night_leaves_each_witness_their_own_piece():
    s = week()
    assert conf(s, "vera", {"pred": "left_vera", "a": "player"}) == 1.0  # she watched his lantern cross home
    assert conf(s, "billy", LANTERN) == conf(s, "otto", LANTERN) == conf(s, "martha", LANTERN) == 1.0  # no face
    assert conf(s, "martha", {"pred": "sold_bottle", "a": "maggie", "b": "tamas"}) == 1.0
    assert conf(s, "gilchrist", fired("someone")) == 1.0  # someone burned the store; nobody knows who
    assert not any(conf(s, n, fired("player")) for n in CASE["everyone"])
    assert conf(week(face=True), "martha", lantern("player")) == 1.0  # on some seeds she saw his face


# ---------------------------------------------------------------- the evenings
def test_his_question_each_evening_is_what_he_heard_that_day():
    s = week()
    assert evening(s) == "ask_night"
    say(s, "maggie", ALIBI, "maggies")  # Anton's story, told to the town's quickest tongue
    s.tick(2)
    assert conf(s, "gilchrist", ALIBI) > 0  # over supper, from Maggie
    assert evening(s) == "ask_alibi"
    line = s.decide("gilchrist", "evening", bindings={"teller": "Billy Tuck"})
    assert line.text.startswith("At your sister's till late")


def test_the_lantern_line_names_whoever_he_has_it_from():
    s = week()
    say(s, "gilchrist", LANTERN, "police", speaker="billy")
    line = s.decide("gilchrist", "evening", bindings={"teller": "Billy Tuck"})
    assert line.action == "ask_lantern"
    assert line.text == "Billy Tuck says a lantern went down the back lane at one that night. Yours, perhaps?"


def test_vera_covers_for_him_while_she_trusts_him_and_tells_the_truth_when_she_doesnt():
    s = week()
    say(s, "gilchrist", ALIBI, "police")
    s.update("gilchrist", loc="vera")
    assert s.decide("vera", "questioned", to="gilchrist").action == "cover"
    assert conf(s, "gilchrist", NO_ALIBI) == 0
    s.update("vera", trust_in={"player": 1})  # he threatened her, or she caught him lying
    assert s.decide("vera", "questioned", to="gilchrist").action == "truth"
    assert conf(s, "gilchrist", NO_ALIBI) == 0.4
    assert evening(s) == "doubt_alibi"
    s.update("gilchrist", flags={"doubted": True})
    say(s, "gilchrist", LANTERN, "police", speaker="billy")
    assert evening(s) == "warn"  # her word, and a lantern in the lane: don't leave town


def test_vera_keeps_quiet_about_him_while_she_trusts_him():
    s = week()
    stopped = s.trace({"pred": "left_vera", "a": "player"})["stopped"]
    assert {"npc": "vera", "why": "keeps it quiet ([[npc.vera.keeps]] 1)"} in stopped
    s.update("vera", trust_in={"player": 2})
    assert s.trace({"pred": "left_vera", "a": "player"})["next"]  # now she tells Maggie


# ---------------------------------------------------------------- the case grows without Anton
def test_no_account_and_a_lantern_draws_the_warning():
    s = week()
    s.update("gilchrist", flags={"asked_night": True})  # he asked where Anton was, and Anton never said
    say(s, "gilchrist", LANTERN, "police", speaker="billy")
    assert evening(s) == "warn"


def test_an_account_given_is_not_no_account():
    s = week()
    s.update("gilchrist", flags={"asked_night": True})
    say(s, "gilchrist", ALIBI, "police")
    say(s, "gilchrist", LANTERN, "police", speaker="billy")
    assert evening(s) != "warn"


def test_out_of_his_sisters_at_half_past_eleven_and_a_lantern_draws_the_warning():
    s = week()
    say(s, "gilchrist", {"pred": "left_vera", "a": "player"}, "police", speaker="maggie")  # Věra's word, by Maggie
    say(s, "gilchrist", LANTERN, "police", speaker="billy")
    assert evening(s) == "warn"


def test_once_he_has_asked_he_crosses_to_the_sister():
    s = week()
    assert s.decide("gilchrist", "rounds").action != "see_vera"
    s.update("gilchrist", flags={"asked_night": True})
    assert s.decide("gilchrist", "rounds").action == "see_vera"


def test_vera_shaken_tells_the_truth():
    s = week()
    s.update("gilchrist", loc="vera")
    s.update("vera", trust_in={"player": 2})  # threatened once
    assert s.decide("vera", "questioned", to="gilchrist").action == "truth"


def test_a_face_in_the_lane_and_no_account_is_enough_to_take_him():
    s = week(face=True)
    s.update("gilchrist", flags={"asked_night": True})
    s.update("gilchrist", loc="maggies")
    s.update("martha", trust_in={"gilchrist": 1})
    s.decide("martha", "questioned", to="gilchrist")  # the face, at Martha's word: 0.4
    assert steamer(s) == "arrest"


# ---------------------------------------------------------------- Martha
def test_martha_tells_the_inspector_only_once_he_has_earned_it():
    s = week(face=True)
    s.update("gilchrist", loc="maggies")
    assert s.decide("martha", "questioned", to="gilchrist").action == "say_nothing"
    s.update("martha", trust_in={"gilchrist": 1})
    line = s.decide("martha", "questioned", to="gilchrist")
    assert line.action == "statement_face" and "Anton Holub" in line.text
    assert conf(s, "gilchrist", lantern("player")) == 0.4


def test_martha_keeps_the_bottle_from_everyone_to_protect_maggie():
    stopped = week().trace({"pred": "sold_bottle", "a": "maggie", "b": "tamas"})["stopped"]
    assert {"npc": "martha", "why": "keeps it quiet ([[npc.martha.keeps]] 1)"} in stopped


def test_martha_is_never_the_one_he_takes():
    s = week()
    for teller in ("otto", "sandor", "maggie"):  # the town says it was "one of the Indians"
        say(s, "gilchrist", fired("martha"), "police", speaker=teller)
        say(s, "gilchrist", lantern("martha"), "police", speaker=teller)
    assert conf(s, "gilchrist", fired("martha")) > 0.4
    assert all("martha" not in c["do"] for c in s.explain("gilchrist", "steamer"))
    assert steamer(s) == "nobody"


# ---------------------------------------------------------------- the endings
def test_breakup_an_old_man_a_bottle_and_a_lamp():
    s = week()
    say(s, "gilchrist", {"pred": "drunk", "a": "tamas"}, "police")
    say(s, "gilchrist", {"pred": "sold_bottle", "a": "maggie", "b": "tamas"}, "police")
    assert steamer(s) == "breakup"


def test_another_mans_coat():
    s = week()
    say(s, "gilchrist", lantern("ashby"), "police")
    assert steamer(s) == "take:ashby"


def test_a_hand_on_the_shoulder_her_word_and_his_sisters():
    s = week(face=True)
    say(s, "gilchrist", ALIBI, "police")
    s.update("vera", trust_in={"player": 1})
    s.update("gilchrist", loc="vera")
    s.decide("vera", "questioned", to="gilchrist")  # the truth
    s.update("gilchrist", loc="maggies")
    s.update("martha", trust_in={"gilchrist": 1})
    s.decide("martha", "questioned", to="gilchrist")  # the face in the lane
    assert steamer(s) == "arrest"


def test_tamas_remembers_and_the_lie_told_him_comes_back():
    s = week()
    s.update("player", loc="mission")
    say(s, "tamas", lantern("ashby"), "mission")  # "it was the stranger's lantern you saw"
    assert conf(s, "tamas", lantern("ashby")) == 0.9  # he believes the one who sits with him
    remember(s, "lantern")
    assert conf(s, "tamas", lantern("ashby")) == 0.9  # a lantern, no face: no rival story
    remember(s, "Anton's")
    assert conf(s, "tamas", lantern("ashby")) == 0.0 and conf(s, "tamas", lantern("player")) == 1.0
    assert s.decide("tamas", "visit").action == "cold"
    line = s.decide("tamas", "decision", to="gilchrist")
    assert line.action == "go_to_inspector"
    assert conf(s, "gilchrist", fired("player")) == 0.9
    assert steamer(s) == "arrest"


def test_tamas_forgives_a_friend_who_never_lied_to_him():
    s = week()
    remember(s, "Anton's")
    assert s.decide("tamas", "visit").action == "remembers"
    assert s.decide("tamas", "decision", to="gilchrist").action == "forgive"
    assert steamer(s) == "nobody"


def test_the_confession():
    s = week()
    s.observe("confess", "player", "gilchrist", at="police", claim=fired("player"), said=True)
    s.update("gilchrist", flags={"confessed": True})
    assert evening(s) == "hear_confession"
    assert steamer(s) == "mercy"


def test_vera_takes_it_on_herself():
    s = week()
    s.observe("confess", "player", "vera", at="vera", claim=fired("player"), said=True)
    assert conf(s, "vera", fired("player")) == 0.9
    s.update("vera", flags={"brother_lost": True})
    assert s.decide("vera", "last_morning", to="gilchrist").action == "confess_for_him"
    assert steamer(s) == "take:vera"


# ---------------------------------------------------------------- the week the seed makes
def test_every_draw_names_its_options_and_the_rules_name_real_ones():
    assert USUAL == {"lantern": "Billy and Otto", "face": "not seen", "memory": "day 4", "whose face": "Anton's",
                     "talk": "nothing yet", "sister": "he left at half past eleven", "kitchen": "Věra",
                     "woodpile": "Otto", "back room": "she says so"}
    for opts in WEEK.values():
        assert all(o["weight"] > 0 for o in opts.values())
    rules = CASE["week"]["rules"]
    for cond in rules["one_of"] + rules["never"]:
        for d, want in cond.items():
            assert want.removeprefix("!") in WEEK[d], (d, want)


def test_someone_besides_martha_always_saw_the_lantern():
    for name in WEEK["lantern"]:
        s = week(lantern=name)
        saw = [n for n in ("billy", "otto") if conf(s, n, LANTERN) == 1.0]
        assert saw and conf(s, "martha", LANTERN) == 1.0, name


def test_the_fever_can_give_him_the_wrong_face():
    s = week(whose_face="Ashby's")
    remember(s, "lantern")
    remember(s, "Ashby's")
    assert conf(s, "tamas", fired("ashby")) == 1.0  # he's sure: he saw it
    assert not s.world.ledger.happened(Claim.from_json(fired("ashby")))  # and it never happened
    assert s.decide("tamas", "visit").action == "remembers_ashby"  # Anton can hear it, sitting with him
    assert s.decide("tamas", "decision", to="gilchrist").action == "accuse_ashby"
    assert conf(s, "gilchrist", fired("ashby")) == 0.9
    assert steamer(s) == "take:ashby"


def test_what_the_town_says_is_a_story_someone_tells_not_a_sighting():
    for name, o in WEEK["talk"].items():
        s = week(talk=name)
        for x in o.get("observe", ()):
            assert x["said"] and x["actor"] == "someone"
            assert conf(s, x["target"], x["claim"]) == 0.6, name
            assert not s.world.ledger.happened(Claim.from_json(x["claim"])), name
        assert bool(o.get("news")) == bool(o.get("observe")), name  # Anton hears what the town is saying


def test_a_sister_who_saw_his_lantern_come_back_keeps_it_while_she_trusts_him():
    s = week(sister="his lantern came back")
    assert conf(s, "vera", fired("player")) == 1.0
    assert {"npc": "vera", "why": "keeps it quiet ([[npc.vera.keeps]] 1)"} in s.trace(fired("player"))["stopped"]
    s.update("vera", flags={"brother_lost": True})  # warned and searched: she gives herself up for him
    assert s.decide("vera", "last_morning", to="gilchrist").action == "confess_for_him"
    assert steamer(s) == "take:vera"


def test_on_some_weeks_martha_talks_to_maggie_too():
    s = week(face=True, kitchen="Věra and Maggie")
    s.tick(2)
    assert conf(s, "maggie", lantern("player")) >= 0.4  # enough for her to pass on
    s = week(face=True)
    s.tick(2)
    assert conf(s, "maggie", lantern("player")) < 0.4  # word of mouth, too faint for her to pass on


# ---------------------------------------------------------------- Otto's and Billy's lies
OTTO = fired("otto")
BILLY = lantern("billy")


def round_to(s: Session, who: str) -> str:
    """Gilchrist's round: whom he goes to ask; there, what they tell him."""
    action = s.decide("gilchrist", "rounds").action
    if action == f"see_{who}":
        s.update("gilchrist", loc=s.world.npcs[who].loc, flags={f"asked_{who}": True})
        return s.decide(who, "questioned", to="gilchrist").action
    return action


def test_a_story_about_otto_sends_him_to_ask_where_otto_was_and_otto_lies():
    s = week()
    assert s.decide("gilchrist", "rounds").action != "see_otto"
    s.observe("tell", "someone", "gilchrist", at="police", claim=OTTO, said=True, conf=0.2)  # faint hearsay
    assert round_to(s, "otto") == "in_bed"
    assert conf(s, "gilchrist", {"pred": "in_bed", "a": "otto"}) > 0
    assert not s.world.ledger.happened(Claim.from_json({"pred": "in_bed", "a": "otto"}))


def test_otto_caught_out_of_his_bed_is_taken_on_a_story():
    s = week()
    s.observe("tell", "someone", "gilchrist", at="police", claim=OTTO, said=True, conf=0.2)
    assert steamer(s) == "nobody"  # a story alone
    assert round_to(s, "otto") == "in_bed"
    assert steamer(s) == "nobody"  # and his word
    say(s, "gilchrist", {"pred": "back_room", "a": "otto"}, "police", speaker="maggie")  # her house: he was there
    assert steamer(s) == "take:otto"


def test_maggie_says_who_was_in_her_back_room_unless_she_takes_a_cut():
    back = {"pred": "back_room", "a": "otto"}
    assert conf(week(), "maggie", back) == 1.0
    assert not any(x.get("npc") == "maggie" for x in week().trace(back)["stopped"] if "keeps" in x.get("why", ""))
    s = week(back_room="she takes a cut")
    assert {"npc": "maggie", "why": "keeps it quiet ([[npc.maggie.keeps]] 3)"} in s.trace(back)["stopped"]


def test_otto_found_out_owns_up_to_the_back_room():
    s = week()
    s.update("otto", flags={"found_out": True})
    s.update("gilchrist", flags={"asked_otto": False})
    s.observe("tell", "player", "gilchrist", at="police", claim=OTTO, said=True)
    assert round_to(s, "otto") == "back_room"


def test_billy_asleep_who_was_seen_at_the_back_door_is_taken_on_a_story():
    for seen_by, taken in (("Otto", True), ("Martha", True), ("nobody", False)):
        s = week(woodpile=seen_by)
        s.observe("tell", "someone", "gilchrist", at="police", claim=BILLY, said=True, conf=0.2)
        assert round_to(s, "billy") == "asleep"
        for n in ("otto", "martha"):
            if conf(s, n, {"pred": "woodpile", "a": "billy"}) == 1.0:  # whoever saw him tells the Inspector
                say(s, "gilchrist", {"pred": "woodpile", "a": "billy"}, "police", speaker=n)
        assert (steamer(s) == "take:billy") == taken, seen_by


def test_billy_keeps_what_he_was_doing_at_the_back_door():
    s = week()
    assert conf(s, "billy", {"pred": "woodpile", "a": "billy"}) == 1.0
    assert {"npc": "billy", "why": "keeps it quiet ([[npc.billy.keeps]] 2)"} in \
        s.trace({"pred": "woodpile", "a": "billy"})["stopped"]


# ---------------------------------------------------------------- the town
def test_billy_paid_a_little_keeps_quiet_and_paid_too_much_wonders():
    s = week()
    assert s.decide("billy", "offered", bindings={"amount": 5}).action == "pocket"
    assert s.decide("billy", "offered", bindings={"amount": 40}).action == "wonder"
    s.update("billy", flags={"paid_off": True})
    assert {"npc": "billy", "why": "keeps it quiet ([[npc.billy.keeps]] 3)"} in s.trace(LANTERN)["stopped"]


def test_a_lie_told_to_sandor_becomes_a_fight():
    s = week()
    say(s, "sandor", fired("ashby"), "mission")
    s.update("sandor", loc="landing")
    s.update("ashby", loc="ice")
    assert s.decide("sandor", "meet", bindings={"who": "ashby"}).action == "greet"  # Ashby isn't there
    s.update("ashby", loc="landing")
    assert s.decide("sandor", "meet", bindings={"who": "ashby"}).action == "fight:ashby"


@pytest.mark.parametrize("text, verb", [
    ("I set the fire", "confess"),
    ("here's 5 dollars", "pay"),
    ("where were you the night of the fire", "ask"),
])
def test_the_players_words_read_with_no_model(text, verb):
    s = week()
    s.update("player", loc="maggies")
    r = s.understand(text, to="maggie")
    assert (r.status, r.intent.verb, r.path) == ("act", verb, "bank")


def test_the_game_ships_the_addon_as_the_sdk_has_it():
    """games/before-the-ice/addons/thespis is a copy of sdk/godot/addons/thespis: a change to one is made to both."""
    sdk = HERE.parents[1] / "sdk" / "godot" / "addons" / "thespis"
    ours = HERE / "addons" / "thespis"
    names = sorted(p.name for p in sdk.iterdir())
    assert sorted(p.name for p in ours.iterdir()) == names
    for name in names:
        assert (ours / name).read_bytes().replace(b"\r\n", b"\n") == (sdk / name).read_bytes().replace(b"\r\n", b"\n"), name
