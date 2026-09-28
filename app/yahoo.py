"""Yahoo Fantasy access through yfpy (official Yahoo API, OAuth2)."""
from __future__ import annotations

import logging
import os
import re
import unicodedata

from .config import DATA_DIR

log = logging.getLogger(__name__)

# Yahoo stat display names -> our stat keys, per position type (P = skater, G = goalie).
YAHOO_STATS = {
    ("P", "G"): "goals", ("P", "A"): "assists", ("P", "P"): "points", ("P", "+/-"): "plus_minus",
    ("P", "PIM"): "pim", ("P", "PPP"): "ppp", ("P", "SHP"): "shp", ("P", "GWG"): "gwg",
    ("P", "SOG"): "shots", ("P", "HIT"): "hits", ("P", "BLK"): "blocks", ("P", "FW"): "fow",
    ("G", "W"): "wins", ("G", "L"): "losses", ("G", "OTL"): "ot_losses", ("G", "SV"): "saves",
    ("G", "GA"): "goals_against", ("G", "SHO"): "shutouts",
}


def norm_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", "", s.lower()).strip()


def _query(league_id: str, interactive: bool = False):
    from dotenv import load_dotenv

    # The token is written to DATA_DIR/.env by the one-time login (another process),
    # so re-read it on every run.
    load_dotenv(DATA_DIR / ".env", override=True)
    token = os.getenv("YAHOO_ACCESS_TOKEN_JSON") or None
    if not token and not interactive:
        raise RuntimeError(
            "Yahoo not authorized yet: run `python -m app.yahoo_login` once in the collector container"
        )

    from yfpy.query import YahooFantasySportsQuery

    return YahooFantasySportsQuery(
        league_id=str(league_id),
        game_code="nhl",
        yahoo_consumer_key=os.getenv("YAHOO_CONSUMER_KEY"),
        yahoo_consumer_secret=os.getenv("YAHOO_CONSUMER_SECRET"),
        yahoo_access_token_json=token,
        env_file_location=DATA_DIR,
        save_token_data_to_env_file=True,
    )


def _val(obj, *names, default=None):
    for n in names:
        v = getattr(obj, n, None)
        if v not in (None, ""):
            return v
    return default


def league_scoring(league_id: str) -> dict:
    """Read the points-per-stat set in the Yahoo league."""
    s = _query(league_id).get_league_settings()
    cats = {}
    for c in _val(getattr(s, "stat_categories", None), "stats", default=[]) or []:
        stat = getattr(c, "stat", c)
        cats[str(_val(stat, "stat_id"))] = (_val(stat, "position_type", default="P"), _val(stat, "display_name", "abbr"))
    scoring: dict = {"skater": {}, "goalie": {}}
    for m in _val(getattr(s, "stat_modifiers", None), "stats", default=[]) or []:
        stat = getattr(m, "stat", m)
        key = cats.get(str(_val(stat, "stat_id")))
        if not key or key not in YAHOO_STATS:
            log.warning("Unmapped Yahoo stat %s", key)
            continue
        group = "goalie" if key[0] == "G" else "skater"
        scoring[group][YAHOO_STATS[key]] = float(_val(stat, "value", default=0))
    return scoring


def rosters(league_id: str) -> dict[int, list[dict]]:
    """All teams' rosters: {team_id: [{name, team, position}, ...]}."""
    q = _query(league_id)
    out: dict[int, list[dict]] = {}
    for t in q.get_league_teams():
        tid = int(_val(t, "team_id"))
        roster = q.get_team_roster_by_week(tid, "current")
        players = []
        for p in _val(roster, "players", default=[]) or []:
            p = getattr(p, "player", p)
            name = _val(p, "full_name") or _val(getattr(p, "name", None), "full", default="")
            players.append(
                {
                    "name": name,
                    "team": (_val(p, "editorial_team_abbr", default="") or "").upper(),
                    "position": _val(p, "primary_position", "display_position", default=""),
                }
            )
        out[tid] = players
    return out
