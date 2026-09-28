import pandas as pd

from app import recommend, scoring


def _stats():
    cur = pd.DataFrame([
        {"player_id": 1, "name": "Star", "position": "C", "team": "MTL", "gp": 2, "goals": 2, "assists": 2},
        {"player_id": 2, "name": "Depth", "position": "L", "team": "MTL", "gp": 2, "goals": 0, "assists": 0},
        {"player_id": 3, "name": "Free Agent", "position": "R", "team": "TOR", "gp": 2, "goals": 1, "assists": 1},
        {"player_id": 4, "name": "Goalie", "position": "G", "team": "MTL", "gp": 2, "wins": 2, "shutouts": 1},
    ])
    prev = pd.DataFrame([
        {"player_id": 1, "name": "Star", "position": "C", "team": "MTL", "gp": 80, "goals": 40, "assists": 60},
        {"player_id": 3, "name": "Free Agent", "position": "R", "team": "TOR", "gp": 80, "goals": 20, "assists": 20},
    ])
    return cur, prev


RULES = {"skater": {"goals": 2, "assists": 1}, "goalie": {"wins": 2, "shutouts": 3}}


def test_points_and_blend():
    cur, prev = _stats()
    s = scoring.score(cur, prev, RULES).set_index("player_id")
    assert s.loc[1, "fpts"] == 6          # 2*2 + 2*1
    assert s.loc[4, "fpts"] == 7          # 2*2 + 1*3
    # 2 games of 20 -> 10% current (3.0/gp), 90% last season (140/80 = 1.75)
    assert abs(s.loc[1, "fpg"] - (0.1 * 3.0 + 0.9 * 1.75)) < 1e-9
    assert s.loc[2, "fpg"] == 0           # no previous season: current only


def test_pickup_replaces_weakest_forward():
    cur, prev = _stats()
    s = scoring.score(cur, prev, RULES)
    recs = recommend.pickups(s, roster_ids={1, 2, 4}, taken_ids=set(), games={"TOR": 3})
    assert list(recs["add"]) == ["Free Agent"]
    assert recs.loc[0, "drop"] == "Depth"
    assert recs.loc[0, "add_games_week"] == 3
