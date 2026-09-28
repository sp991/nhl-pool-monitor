"""Scoring engine: turns raw stats into pool points using each pool's own rules."""
from __future__ import annotations

import pandas as pd

SKATER_KEYS = ["goals", "assists", "points", "plus_minus", "pim", "ppp", "shp", "gwg", "shots", "hits", "blocks", "fow"]
GOALIE_KEYS = ["wins", "losses", "ot_losses", "saves", "goals_against", "shutouts"]

# Early in the season, current stats are noisy. Blend with last season until a
# player reaches this many games; after that, current season dominates.
BLEND_GAMES = 20


def fantasy_points(df: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    total = pd.Series(0.0, index=df.index)
    for stat, w in (weights or {}).items():
        if stat in df.columns and w:
            total = total + df[stat].fillna(0) * float(w)
    return total


def score(current: pd.DataFrame, previous: pd.DataFrame, scoring: dict) -> pd.DataFrame:
    """Return one row per player with season points and a blended points-per-game.

    `scoring` looks like {"skater": {...}, "goalie": {...}}.
    """
    frames = []
    for group, keys in (("skater", SKATER_KEYS), ("goalie", GOALIE_KEYS)):
        weights = scoring.get(group, {})
        is_g = current["position"].eq("G") if not current.empty else pd.Series(dtype=bool)
        cur = current[is_g] if group == "goalie" else current[~is_g]
        if not previous.empty:
            pg = previous["position"].eq("G")
            prev = previous[pg] if group == "goalie" else previous[~pg]
        else:
            prev = previous

        cur = cur.copy()
        cur["fpts"] = fantasy_points(cur, weights)
        cur["fpg_cur"] = (cur["fpts"] / cur["gp"].where(cur["gp"] > 0)).fillna(0)

        if not prev.empty:
            p = prev.copy()
            p["fpg_prev"] = (fantasy_points(p, weights) / p["gp"].where(p["gp"] > 0)).fillna(0)
            cur = cur.merge(p[["player_id", "fpg_prev"]], on="player_id", how="left")
        else:
            cur["fpg_prev"] = float("nan")

        w_cur = (cur["gp"] / BLEND_GAMES).clip(upper=1.0)
        has_prev = cur["fpg_prev"].notna()
        cur["fpg"] = cur["fpg_cur"].where(~has_prev, w_cur * cur["fpg_cur"] + (1 - w_cur) * cur["fpg_prev"])
        frames.append(cur)

    out = pd.concat(frames, ignore_index=True) if frames else current.assign(fpts=0.0, fpg=0.0)
    return out.sort_values("fpg", ascending=False).reset_index(drop=True)
