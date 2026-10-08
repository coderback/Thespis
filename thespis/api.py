"""The one import a game needs. Everything else in `thespis` is internal and may change between 0.x releases.

    from thespis.api import Game, Session

    game = Game.load("game.toml")
    s = Session.new(game)
    s.observe("insult", "player", "garrick", claim={"pred": "insulted", "a": "player", "b": "garrick"},
              witnesses=["wren"])
    s.update("garrick", nudge={"grudge": 4})
    line = s.decide("garrick", "turn")  # what he does, and what he says as he does it

thespis.session explains the calls; thespis.http serves the same ones as /v1.
"""

from thespis import __version__
from thespis.considerations import DefinitionError
from thespis.gateway import ModelGateway, gateway_from_env
from thespis.ledger import Claim, Event
from thespis.play import NotAllowed
from thespis.session import FINAL, PROVISIONAL, SNAPSHOT_VERSION, WITHDRAWN, Game, Line, Session, Unknown

__all__ = ["Claim", "DefinitionError", "Event", "FINAL", "Game", "Line", "ModelGateway", "NotAllowed", "PROVISIONAL",
           "SNAPSHOT_VERSION", "Session", "Unknown", "WITHDRAWN", "__version__", "gateway_from_env"]
