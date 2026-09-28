"""Client for the public (undocumented) NHL APIs.

api.nhle.com/stats/rest  -> season stat tables for every skater and goalie
api-web.nhle.com/v1      -> schedule
"""
from __future__ import annotations

import datetime as dt
import logging
from collections import Counter

import httpx

log = logging.getLogger(__name__)

STATS = "https://api.nhle.com/stats/rest/en"
WEB = "https://api-web.nhle.com/v1"
PAGE = 100


def season_id(today: dt.date | None = None) -> int:
    """20262027 style id. A new season starts in September."""
    d = today or dt.date.today()
    start = d.year if d.month >= 9 else d.year - 1
    return start * 10000 + start + 1


def previous_season(sid: int) -> int:
    start = sid // 10000 - 1
    return start * 10000 + start + 1


class NHLClient:
    def __init__(self, timeout: float = 30.0):
        self.http = httpx.Client(timeout=timeout, headers={"User-Agent": "nhl-pool-monitor"})

    def _report(self, kind: str, report: str, sid: int) -> list[dict]:
        """Page through a stats report (regular season only)."""
        rows: list[dict] = []
        start = 0
        while True:
            r = self.http.get(
                f"{STATS}/{kind}/{report}",
                params={
                    "start": start,
                    "limit": PAGE,
                    "sort": "playerId",
                    "cayenneExp": f"seasonId={sid} and gameTypeId=2",
                },
            )
            r.raise_for_status()
            data = r.json().get("data", [])
            rows.extend(data)
            if len(data) < PAGE:
                return rows
            start += PAGE

    def skaters(self, sid: int) -> list[dict]:
        """One row per skater with every stat the scoring engine understands."""
        summary = self._report("skater", "summary", sid)
        realtime = {r["playerId"]: r for r in self._report("skater", "realtime", sid)}
        faceoffs = {r["playerId"]: r for r in self._report("skater", "faceoffwins", sid)}
        out = []
        for s in summary:
            pid = s["playerId"]
            rt = realtime.get(pid, {})
            fo = faceoffs.get(pid, {})
            out.append(
                {
                    "player_id": pid,
                    "name": s.get("skaterFullName"),
                    "position": s.get("positionCode"),
                    "team": (s.get("teamAbbrevs") or "").split(",")[-1].strip(),
                    "gp": s.get("gamesPlayed") or 0,
                    "goals": s.get("goals") or 0,
                    "assists": s.get("assists") or 0,
                    "points": s.get("points") or 0,
                    "plus_minus": s.get("plusMinus") or 0,
                    "pim": s.get("penaltyMinutes") or 0,
                    "ppp": s.get("ppPoints") or 0,
                    "shp": s.get("shPoints") or 0,
                    "gwg": s.get("gameWinningGoals") or 0,
                    "shots": s.get("shots") or 0,
                    "hits": rt.get("hits") or 0,
                    "blocks": rt.get("blockedShots") or 0,
                    "fow": fo.get("totalFaceoffWins") or 0,
                }
            )
        return out

    def goalies(self, sid: int) -> list[dict]:
        out = []
        for g in self._report("goalie", "summary", sid):
            out.append(
                {
                    "player_id": g["playerId"],
                    "name": g.get("goalieFullName"),
                    "position": "G",
                    "team": (g.get("teamAbbrevs") or "").split(",")[-1].strip(),
                    "gp": g.get("gamesPlayed") or 0,
                    "wins": g.get("wins") or 0,
                    "losses": g.get("losses") or 0,
                    "ot_losses": g.get("otLosses") or 0,
                    "saves": g.get("saves") or 0,
                    "goals_against": g.get("goalsAgainst") or 0,
                    "shutouts": g.get("shutouts") or 0,
                }
            )
        return out

    def games_this_week(self) -> Counter:
        """Number of games each team plays in the current schedule week."""
        r = self.http.get(f"{WEB}/schedule/now")
        r.raise_for_status()
        counts: Counter = Counter()
        for day in r.json().get("gameWeek", []):
            for g in day.get("games", []):
                counts[g["homeTeam"]["abbrev"]] += 1
                counts[g["awayTeam"]["abbrev"]] += 1
        return counts
