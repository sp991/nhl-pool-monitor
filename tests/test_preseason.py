import pandas as pd

from app import recommend, scoring
from app.collector import merge_seasons

PREV = pd.DataFrame([
    {"player_id": 1, "name": "Star", "position": "C", "team": "MTL", "gp": 80, "goals": 40, "assists": 60},
    {"player_id": 2, "name": "Depth", "position": "L", "team": "MTL", "gp": 80, "goals": 5, "assists": 5},
    {"player_id": 3, "name": "Free Agent", "position": "R", "team": "TOR", "gp": 80, "goals": 20, "assists": 20},
])
RULES = {"skater": {"goals": 2, "assists": 1}, "goalie": {"wins": 2}}


def test_preseason_empty_current_season():
    cur = merge_seasons(pd.DataFrame(), PREV)
    assert len(cur) == 3
    assert (cur["gp"] == 0).all() and (cur["goals"] == 0).all()

    s = scoring.score(cur, PREV, RULES).set_index("player_id")
    assert s.loc[1, "fpg"] > s.loc[3, "fpg"] > s.loc[2, "fpg"]   # last season decides

    recs = recommend.pickups(scoring.score(cur, PREV, RULES), {1, 2}, set(), {})
    assert list(recs["add"]) == ["Free Agent"] and recs.loc[0, "drop"] == "Depth"


def test_player_without_game_this_season_is_kept():
    cur = merge_seasons(PREV.iloc[[0]].assign(gp=2, goals=1, assists=1), PREV)
    assert set(cur["player_id"]) == {1, 2, 3}
    assert cur.set_index("player_id").loc[1, "gp"] == 2


def test_empty_results_are_saved_without_error():
    import sqlite3
    from app.collector import _save
    con = sqlite3.connect(":memory:")
    _save(con, pd.DataFrame(), "pickups_x")            # nothing to show yet
    _save(con, pd.DataFrame({"a": [1]}), "roster_x")
    _save(con, pd.DataFrame(), "roster_x")             # previous table removed
    names = {r[0] for r in con.execute("SELECT name FROM sqlite_master")}
    assert names == set()
