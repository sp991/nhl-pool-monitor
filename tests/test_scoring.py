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
        {"player_id": 2, "name": "Depth", "position": "L", "team": "MTL", "gp": 80, "goals": 5, "assists": 5},
        {"player_id": 3, "name": "Free Agent", "position": "R", "team": "TOR", "gp": 80, "goals": 20, "assists": 20},
    ])
    return cur, prev


RULES = {"skater": {"goals": 2, "assists": 1}, "goalie": {"wins": 2, "shutouts": 3}}


def test_points_and_blend():
    cur, prev = _stats()
    s = scoring.score(cur, prev, RULES).set_index("player_id")
    assert s.loc[1, "fpts"] == 6          # 2*2 + 2*1
    assert s.loc[4, "fpts"] == 7          # 2*2 + 1*3
    # Pooled estimate: last season at half weight, this season, 15 games at prior.
    import numpy as np
    prior = float(np.quantile([140 / 80, 15 / 80, 60 / 80], 0.30))   # 30th pct of regulars
    expected = (140 * 0.5 + 6 + 15 * prior) / (80 * 0.5 + 2 + 15)
    assert abs(s.loc[1, "fpg"] - expected) < 1e-9
    assert s.loc[1, "fpg"] > s.loc[3, "fpg"] > s.loc[2, "fpg"]


def test_pickup_replaces_weakest_forward():
    cur, prev = _stats()
    s = scoring.score(cur, prev, RULES)
    recs = recommend.pickups(s, roster_ids={1, 2, 4}, taken_ids=set(), games={"TOR": 3})
    assert list(recs["add"]) == ["Free Agent"]
    assert recs.loc[0, "drop"] == "Depth"
    assert recs.loc[0, "add_games_week"] == 3



def test_tiny_sample_is_pulled_to_replacement_level():
    cur = pd.DataFrame([
        {"player_id": 10, "name": "Starter", "position": "G", "team": "A", "gp": 0, "wins": 0, "shutouts": 0},
        {"player_id": 11, "name": "One Game Wonder", "position": "G", "team": "B", "gp": 0, "wins": 0, "shutouts": 0},
    ])
    prev = pd.DataFrame([
        {"player_id": 10, "name": "Starter", "position": "G", "team": "A", "gp": 60, "wins": 35, "shutouts": 4},
        {"player_id": 11, "name": "One Game Wonder", "position": "G", "team": "B", "gp": 1, "wins": 1, "shutouts": 1},
        {"player_id": 12, "name": "Backup", "position": "G", "team": "C", "gp": 45, "wins": 15, "shutouts": 1},
    ])
    s = scoring.score(cur, prev, RULES).set_index("player_id")
    # Raw rate 5.0/game for the one-gamer, but the proven starter must rank higher.
    assert s.loc[10, "fpg"] > s.loc[11, "fpg"]
