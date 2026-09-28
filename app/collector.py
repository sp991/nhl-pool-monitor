"""Collector: pulls data, scores each pool, stores results for the dashboard."""
from __future__ import annotations

import datetime as dt
import json
import logging
import sqlite3
import sys

import pandas as pd
from apscheduler.schedulers.blocking import BlockingScheduler

from . import poolexpert, recommend, scoring, yahoo
from .config import DB_PATH, load_pools
from .nhl import NHLClient, previous_season, season_id

log = logging.getLogger("collector")
REFRESH_MINUTES = 20


def _db() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def _stats(nhl: NHLClient, sid: int) -> pd.DataFrame:
    return pd.DataFrame(nhl.skaters(sid) + nhl.goalies(sid))


def _previous_stats(nhl: NHLClient, sid: int) -> pd.DataFrame:
    """Last season never changes, so fetch it once and cache it."""
    table = f"stats_{sid}"
    with _db() as con:
        try:
            return pd.read_sql(f"SELECT * FROM {table}", con)
        except Exception:
            df = _stats(nhl, sid)
            df.to_sql(table, con, index=False)
            return df


class Matcher:
    """Resolve player names (or NHL ids) from Yahoo/config to NHL player ids."""

    def __init__(self, players: pd.DataFrame):
        self.by_name: dict[str, list[tuple[int, str]]] = {}
        self.ids = set(players["player_id"])
        for pid, name, team in players[["player_id", "name", "team"]].itertuples(index=False):
            self.by_name.setdefault(yahoo.norm_name(name), []).append((pid, team))

    def resolve(self, name, team: str = "") -> int | None:
        if isinstance(name, int) or str(name).isdigit():
            pid = int(name)
            return pid if pid in self.ids else None
        name = str(name)
        if "," in name:  # "McDavid, Connor" -> "Connor McDavid"
            last, first = name.split(",", 1)
            name = f"{first.strip()} {last.strip()}"
        hits = self.by_name.get(yahoo.norm_name(name), [])
        if len(hits) > 1 and team:
            hits = [h for h in hits if h[1] == team] or hits
        return hits[0][0] if hits else None


def run_once() -> None:
    started = dt.datetime.now().isoformat(timespec="seconds")
    nhl = NHLClient()
    sid = season_id()
    current = _stats(nhl, sid)
    previous = _previous_stats(nhl, previous_season(sid))
    # Include players with no games yet this season (known from last season).
    missing = previous[~previous["player_id"].isin(current["player_id"])].copy()
    stat_cols = [c for c in missing.columns if c not in ("player_id", "name", "position", "team")]
    missing[stat_cols] = 0
    current = pd.concat([current, missing], ignore_index=True)

    games = dict(nhl.games_this_week())
    matcher = Matcher(current)
    status = {"last_run": started, "season": sid, "pools": {}}

    for pool in load_pools():
        pid = pool["id"]
        try:
            taken: set[int] = set()
            mine: set[int] = set()
            if pool.get("source") == "yahoo":
                rules = pool.get("scoring") or yahoo.league_scoring(pool["league_id"])
                teams = yahoo.rosters(pool["league_id"])
                for tid, players in teams.items():
                    ids = {matcher.resolve(p["name"], p["team"]) for p in players} - {None}
                    taken |= ids
                    if tid == int(pool["team_id"]):
                        mine = ids
                unmatched = [p["name"] for p in teams.get(int(pool["team_id"]), [])
                             if matcher.resolve(p["name"], p["team"]) is None]
            elif pool.get("source") == "poolexpert":
                rules = pool.get("scoring", {})
                pe = poolexpert.PoolExpertClient(int(pool["pool_id"]), int(pool["entry_id"]))
                roster_names = [p["name"] for p in pe.my_roster()]
                mine = {matcher.resolve(n) for n in roster_names} - {None}
                taken = {matcher.resolve(p["name"]) for p in pe.all_rostered()} - {None}
                unmatched = [n for n in roster_names if matcher.resolve(n) is None]
            else:
                rules = pool.get("scoring", {})
                mine = {matcher.resolve(n) for n in pool.get("roster", [])} - {None}
                unmatched = [n for n in pool.get("roster", []) if matcher.resolve(n) is None]

            scored = scoring.score(current, previous, rules)
            roster = recommend.roster_view(scored, mine, games)
            adds = (
                recommend.pickups(scored, mine, taken, games)
                if pool.get("free_agents_allowed", True) else pd.DataFrame()
            )
            with _db() as con:
                roster.to_sql(f"roster_{pid}", con, index=False, if_exists="replace")
                adds.to_sql(f"pickups_{pid}", con, index=False, if_exists="replace")
                scored.head(300).to_sql(f"top_{pid}", con, index=False, if_exists="replace")
            status["pools"][pid] = {"name": pool.get("name", pid), "ok": True,
                                    "scoring": rules, "unmatched": unmatched,
                                    "note": pool.get("note", "")}
            log.info("%s: %d rostered, %d pickup ideas", pid, len(roster), len(adds))
        except Exception as e:  # keep other pools running
            log.exception("Pool %s failed", pid)
            status["pools"][pid] = {"name": pool.get("name", pid), "ok": False, "error": str(e)}

    with _db() as con:
        con.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
        con.execute("INSERT OR REPLACE INTO meta VALUES ('status', ?)", (json.dumps(status),))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if "--once" in sys.argv:
        run_once()
        return
    run_once()
    sched = BlockingScheduler()
    sched.add_job(run_once, "interval", minutes=REFRESH_MINUTES, max_instances=1, coalesce=True)
    log.info("Refreshing every %d minutes", REFRESH_MINUTES)
    sched.start()


if __name__ == "__main__":
    main()
