"""Recommendations: lineup value this week and free-agent upgrades."""
from __future__ import annotations

import pandas as pd

# Treat D and forwards separately so a pickup replaces a like-for-like player.
POS_GROUP = {"C": "F", "L": "F", "R": "F", "LW": "F", "RW": "F", "D": "D", "G": "G"}


def _group(pos: str) -> str:
    return POS_GROUP.get((pos or "").upper(), "F")


def roster_view(scored: pd.DataFrame, roster_ids: set[int], games: dict[str, int]) -> pd.DataFrame:
    r = scored[scored["player_id"].isin(roster_ids)].copy()
    r["games_week"] = r["team"].map(games).fillna(0).astype(int)
    r["proj_week"] = (r["fpg"] * r["games_week"]).round(1)
    r["group"] = r["position"].map(_group)
    return r.sort_values("proj_week", ascending=False)


def pickups(
    scored: pd.DataFrame,
    roster_ids: set[int],
    taken_ids: set[int],
    games: dict[str, int],
    min_gain: float = 0.05,
    top_n: int = 10,
) -> pd.DataFrame:
    """Free agents whose points/game beat the weakest rostered player at the same position group."""
    if not roster_ids:
        return pd.DataFrame()
    s = scored.copy()
    s["group"] = s["position"].map(_group)
    s["games_week"] = s["team"].map(games).fillna(0).astype(int)
    mine = s[s["player_id"].isin(roster_ids)]
    # fpg > 0 rather than gp > 0: in preseason nobody has played yet, and
    # last season's rate still makes a player a valid pickup.
    pool = s[~s["player_id"].isin(taken_ids | roster_ids) & (s["fpg"] > 0)]

    recs = []
    for grp, mine_g in mine.groupby("group"):
        worst = mine_g.sort_values("fpg").iloc[0]
        cands = pool[(pool["group"] == grp) & (pool["fpg"] > worst["fpg"] + min_gain)]
        for _, c in cands.head(top_n).iterrows():
            recs.append(
                {
                    "add": c["name"],
                    "add_team": c["team"],
                    "add_pos": c["position"],
                    "add_fpg": round(c["fpg"], 2),
                    "add_games_week": int(c["games_week"]),
                    "drop": worst["name"],
                    "drop_fpg": round(worst["fpg"], 2),
                    "gain_per_game": round(c["fpg"] - worst["fpg"], 2),
                }
            )
    if not recs:
        return pd.DataFrame()
    return pd.DataFrame(recs).sort_values("gain_per_game", ascending=False).head(top_n).reset_index(drop=True)
