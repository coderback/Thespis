"""Claims: what a line asserts about the world, in the game's own vocabulary, checked against the ledger in code.

A model only extracts the claims a line makes (`extraction_messages`). Code then decides what each one is
(`categorize`), against what really happened and what the speaker could know when it spoke:

- grounded       it happened, and the speaker could know it
- leak           it happened, but the speaker couldn't know it
- false_belief   it never happened, but the speaker believes it: an honest mistake the game allows
- lie            it never happened, and the speaker stated it through a deception action the game offered
- contradiction  the speaker says what it no longer believes, or denies what it believes
- hallucination  it never happened, and nothing the speaker holds says it did
- unverifiable   not about anything the ledger records (opinions are never extracted)

A denial ("Kael never robbed Odo") is grounded when it's right, a contradiction when the speaker believes the
opposite, and a hallucination otherwise. This is the paper's instrument (tobi/paper-m1, research/metrics.py), moved
into the core so Rehearsal can measure every line offline, and ClaimCheck can check a line with consequences before
anyone hears it.

The two differ on reported speech. Measuring, "Kael says you robbed him" asserts both that Kael told the speaker and
that the player robbed him, as the paper counted it. Checking, it asserts only that Kael told the speaker: a character
may truthfully repeat what it was told, even what it no longer believes, and the teller is the one who vouched for it.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

from thespis.beliefs import Belief
from thespis.expression import StatePack
from thespis.gateway import ModelGateway
from thespis.ledger import Claim, Event
from thespis.world import World

CATEGORIES = ("grounded", "leak", "false_belief", "lie", "contradiction", "hallucination", "unverifiable")
BAD = ("leak", "contradiction", "hallucination")
OTHER = "other"


@dataclass(frozen=True)
class EventPred:
    """A claim the ledger records as an event rather than as a claim, e.g. went_to(kael, bridge) is a move."""

    verbs: tuple[str, ...]
    b_field: str | None  # which of the event's fields the claim's b names: "target", "loc", or None for neither


@dataclass(frozen=True)
class ClaimVocabulary:
    """A game's vocabulary for claims: what an extractor may say, and how each predicate is checked."""

    game: str
    description: str  # the predicates, characters and places, as the extractor reads them
    characters: tuple[str, ...]
    places: tuple[str, ...]
    ledger_preds: frozenset[str]  # predicates the ledger records as claims, e.g. robbed
    event_preds: Mapping[str, EventPred] = field(default_factory=dict)
    place_preds: frozenset[str] = frozenset({"at"})  # predicates whose b is a place
    fixed_b: Mapping[str, str] = field(default_factory=dict)  # predicates whose b is always the same, e.g. took: ring
    timed_preds: frozenset[str] = frozenset()  # predicates whose b is PLACE@TIME, e.g. the manor's was_in
    aliases: Mapping[str, str] = field(default_factory=dict)  # other ways of naming a character or place

    @property
    def preds(self) -> tuple[str, ...]:
        return tuple(sorted(self.ledger_preds | set(self.event_preds) | {"at"}))


# ---------------------------------------------------------------- extraction, by a model
_HEAD = (
    "You read one line of dialogue spoken by a character in a game and list the facts it asserts about the game "
    "world, in the game's vocabulary.\n{vocab}\n"
    "Rules:\n"
    "- Only what the line says has already happened or is true now. Leave out what anyone intends, plans, threatens, "
    "promises or says will happen (\"I'm taking the relic\", \"You'll pay for that\"), claims of ownership or "
    "entitlement (\"The relic is mine\"), opinions, feelings, questions, orders and greetings. A line may assert "
    "nothing.\n"
    "- Resolve \"I\" and \"me\" to the speaker. \"You\" is whoever the speaker is talking to: the player, unless the "
    "situation or the line shows it is someone else (\"Captain\", \"Sable\"). Resolve every other pronoun to the "
    "person it refers to in that sentence.\n")
_TAIL = (
    "- a and b are ids from the lists above, nothing else. Set happened to false when the line says it did not "
    "happen.\n"
    'Reply with JSON only: {{"claims": [{{"pred": "...", "a": "...", "b": "...", "happened": true}}]}}')
EXTRACT_PROMPT = _HEAD + (  # measuring: the paper's rule
    "- Reported speech (\"Kael says you robbed him\", said by brenna) asserts both that the teller told the speaker "
    "(told(kael, brenna)) and the fact reported (robbed(player, kael)).\n") + _TAIL
CHECK_PROMPT = _HEAD + (  # checking: the speaker vouches only for having been told
    "- Reported speech (\"Kael says you robbed him\", said by brenna) asserts only that the teller told the speaker: "
    "told(kael, brenna). Leave out the fact reported: the teller vouched for it, not the speaker.\n"
    # Two misreadings the first live rehearsal of the check found:
    "- When the situation says someone other than the player is speaking to the speaker or asking it something "
    "(\"Captain Brenna asks you\"), \"you\" in the line is them.\n"
    "- A journey \"from A to B\" asserts that they went to B; it doesn't say they went to A.\n") + _TAIL


def extraction_messages(vocab: ClaimVocabulary, speaker: str, name: str, situation: str, here: list[str],
                        line: str, prompt: str = EXTRACT_PROMPT) -> list[dict]:
    return [{"role": "system", "content": prompt.format(vocab=vocab.description)},
            {"role": "user", "content": json.dumps({"speaker": speaker, "speaker_name": name, "situation": situation,
                                                    "here": here, "line": line}, ensure_ascii=False)}]


def extraction_schema(vocab: ClaimVocabulary) -> dict:
    """The extractor's reply as a strict JSON schema: one per game, so it never changes between calls."""
    claim = {"type": "object", "additionalProperties": False, "required": ["pred", "a", "b", "happened"],
             "properties": {"pred": {"type": "string", "enum": [*vocab.preds, OTHER]},
                            "a": {"type": "string", "enum": list(vocab.characters)},
                            "b": {"type": "string"}, "happened": {"type": "boolean"}}}
    return {"type": "object", "additionalProperties": False, "required": ["claims"],
            "properties": {"claims": {"type": "array", "items": claim}}}


def parse_claims(data: dict | None) -> list[dict] | None:
    """The claims in an extractor's reply, or None if it gave no usable list."""
    claims = (data or {}).get("claims")
    if not isinstance(claims, list) or not all(isinstance(c, dict) for c in claims):
        return None
    return claims


# ---------------------------------------------------------------- normalising what the extractor said
def _id(vocab: ClaimVocabulary, text: str, choices: tuple[str, ...]) -> str | None:
    """The id a messy argument names: "kael's coins" -> kael, "brenna (reported the player)" -> brenna."""
    t = str(text or "").strip().lower()
    t = vocab.aliases.get(t, t)
    if t in choices:
        return t
    found = [(t.find(alias), target) for alias, target in vocab.aliases.items() if alias in t and target in choices]
    found += [(t.find(name), choice) for choice in choices for name in {choice, choice.replace("_", " ")} if name in t]
    return min(found)[1] if found else None  # whoever the text names first


def normalize(vocab: ClaimVocabulary, claim: dict) -> dict:
    """A claim with its arguments mapped to ids, or with its pred set to "other" when they can't be."""
    pred = claim.get("pred", "")
    a = _id(vocab, claim.get("a", ""), vocab.characters)
    if pred in vocab.fixed_b:
        b = vocab.fixed_b[pred]
    elif pred in vocab.timed_preds:
        place, _, when = str(claim.get("b", "")).partition("@")
        room = _id(vocab, place, vocab.places)
        b = f"{room}@{when.strip()}" if room and when.strip().isdigit() else None
    elif pred in vocab.place_preds:
        b = _id(vocab, claim.get("b", ""), vocab.places)
    else:
        b = _id(vocab, claim.get("b", ""), vocab.characters)
    if pred not in vocab.preds or a is None or b is None:
        return {**claim, "pred": OTHER}
    return {**claim, "a": a, "b": b}


# ---------------------------------------------------------------- what the speaker could know
@dataclass
class Facts:
    """The world as it stood when a line was said, and what its speaker could know of it, by the game's own rules.

    `happened` is the game's truth for a claim the ledger records; `knows` says whether the speaker could know an
    event. The narrator, who holds no beliefs, is a speaker too: it knows exactly the events it was told about.
    """

    world: World
    speaker: str
    happened: Callable[[World, Claim], bool]
    knows: Callable[[str], bool]  # event id -> could the speaker know it

    def beliefs(self) -> list[Belief]:
        return self.world.beliefs.for_npc(self.speaker)

    def where(self, who: str) -> str | None:
        if who == "player":
            return self.world.player.get("loc")
        npc = self.world.npcs.get(who)
        return npc.loc if npc else None

    def events(self, verbs: Iterable[str], actor: str, b_field: str | None, b: str | None) -> list[Event]:
        verbs = set(verbs)
        return [e for e in self.world.ledger if e.verb in verbs and e.actor == actor
                and (b_field is None or getattr(e, b_field) == b)]


def categorize(vocab: ClaimVocabulary, claim: dict, facts: Facts, asserting: bool = False) -> str:
    """The category of one extracted claim, {"pred", "a", "b", "happened"}. `asserting` says the line went with an
    action that states a claim the game offered (thespis.deception), so a false claim in it is a lie."""
    claim = normalize(vocab, claim)
    pred, a, b = str(claim.get("pred")), str(claim.get("a", "")), str(claim.get("b", ""))
    positive = claim.get("happened", True) is not False
    believes = dropped = False

    if pred in vocab.ledger_preds:
        c = Claim(pred, a, b)
        true = facts.happened(facts.world, c)
        held = [x for x in facts.beliefs() if x.claim == c]
        believes = any(x.active for x in held)
        dropped = any(not x.active for x in held)
        knowable = bool(held) or any(e.claim == c and facts.knows(e.id) for e in facts.world.ledger)
    elif pred in vocab.event_preds:
        spec = vocab.event_preds[pred]
        matching = facts.events(spec.verbs, a, spec.b_field, b)
        true = bool(matching)
        # Known by seeing it, or by believing what it showed: told that Sable was in the study, Lady Vane knows of
        # the leaving that put her there.
        held = {x.claim for x in facts.beliefs() if x.active}
        knowable = any(facts.knows(e.id) or (e.claim is not None and e.claim in held) for e in matching)
    elif pred == "at":
        where = facts.where(a)
        true = where == b
        knowable = (where is not None and where == facts.where(facts.speaker)) or any(
            facts.knows(e.id) for e in facts.world.ledger if e.verb == "move" and e.actor == a and e.target == b)
    else:
        return "unverifiable"

    if not positive:  # a denial
        if not true:
            return "grounded"
        return "contradiction" if believes else "hallucination"
    if true:
        return "grounded" if knowable else "leak"
    if asserting:
        return "lie"
    if believes:
        return "false_belief"
    if dropped:
        return "contradiction"
    return "hallucination"


def score(vocab: ClaimVocabulary, claims: list[dict], facts: Facts, asserting: bool = False) -> Counter:
    """Each category's count for one line's claims."""
    return Counter(categorize(vocab, c, facts, asserting) for c in claims)


def label(claim: dict) -> str:
    """A claim as it reads in a report, e.g. robbed(odo, kael), or not robbed(odo, kael) for a denial."""
    text = f"{claim.get('pred')}({claim.get('a')}, {claim.get('b')})"
    return text if claim.get("happened", True) is not False else f"not {text}"


# ---------------------------------------------------------------- checking a line before anyone hears it
def _states(claim: dict, c: Claim) -> bool:
    return (claim.get("pred"), claim.get("a"), claim.get("b")) == (c.pred, c.a, c.b) and \
        claim.get("happened", True) is not False


class ClaimCheck:
    """The claim check on lines with consequences (docs/cast-review.md, Phase 2), for thespis.expression.Mind.

    Before a line is heard, a model extracts the claims it makes (CHECK_PROMPT, with the game's schema), and code
    checks each against what its speaker could know (`facts`, the game's rule). A line is refused when:
      - a claim leaks, hallucinates or contradicts what the speaker holds;
      - the line goes with an action that states a claim (thespis.deception) and doesn't state it, so the ledger and
        the words would disagree. That claim may be false: the game chose the lie.
    An extractor that gives no answer refuses the line too: it fails closed, and the NPC uses its template line.

    It checks the lines whose pack says they have stakes, or every line with `every`.
    """

    def __init__(self, gateway: ModelGateway, vocab: ClaimVocabulary, facts: Callable[[StatePack], Facts],
                 every: bool = False):
        self.gateway, self.vocab, self.facts, self.every = gateway, vocab, facts, every
        self.schema = extraction_schema(vocab)

    def wants(self, pack: StatePack) -> bool:
        return self.every or pack.stakes

    def problems(self, items: list[tuple[StatePack, str]]) -> list[str | None]:
        """Why each (pack, line) can't be heard, or None for one that can. One extraction call per line."""
        calls = [("extract", extraction_messages(self.vocab, pack.npc, pack.name, pack.situation, pack.here, line,
                                                 CHECK_PROMPT), self.schema) for pack, line in items]
        replies = [self.gateway.complete(*calls[0])] if len(calls) == 1 else self.gateway.complete_many(calls)
        return [self.verdict(pack, parse_claims(reply.data) if reply is not None else None)
                for (pack, _), reply in zip(items, replies)]

    def verdict(self, pack: StatePack, claims: list[dict] | None) -> str | None:
        if claims is None:
            return "unavailable"
        facts, stated = self.facts(pack), False
        for claim in claims:
            n = normalize(self.vocab, claim)
            if pack.asserted is not None and _states(n, pack.asserted):
                stated = True  # the claim its action states, which code chose, true or not
                continue
            category = categorize(self.vocab, claim, facts)
            if category in BAD:
                return f"{category}: {label(n)}"
        if pack.asserted is not None and not stated:
            return f"doesn't state {label(pack.asserted.to_json())}"
        return None


@dataclass(frozen=True)
class ClaimChecking:
    """How a host checks claims: which lines ("consequential" or "all"), and the extractor's gateway. None means the
    gateway the line was spoken through."""

    mode: str = "consequential"
    gateway: ModelGateway | None = None


def checking_from_env(env: Mapping[str, str]) -> ClaimChecking | None:
    """CLAIM_CHECK (consequential, all or off) and an optional LLM_CHECK_* provider for the extractor."""
    from thespis.gateway import OpenAICompatGateway, provider_from_env

    mode = env.get("CLAIM_CHECK", "consequential").strip() or "consequential"
    if mode == "off":
        return None
    if mode not in ("consequential", "all"):
        raise ValueError(f"CLAIM_CHECK must be consequential, all or off, not {mode!r}")
    provider = provider_from_env(env, "LLM_CHECK_")
    return ClaimChecking(mode, OpenAICompatGateway([provider]) if provider else None)
