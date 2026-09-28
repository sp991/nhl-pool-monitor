"""Scoring engine: turns raw stats into pool points using each pool's own rules.

Points per game are estimated from last season and this season together, and
small samples are pulled toward replacement level: a goalie with one great game
last year must not outrank a proven starter. Concretely, per player:

    fpg = (pts_prev * W + pts_cur + K * prior) / (gp_prev * W + gp_cur + K)

- W: weight of a game from last season versus one from this season (0.5).
- K: pseudo-games at the prior (15). With 80 real games K barely matters; with
  2 games the prior dominates.
- prior: replacement level for the player's position group (F, D or G), taken as
  the 30th percentile rate of regulars (40+ games last season).
"""
from __future__ import annotations

import pandas as pd

SKATER_KEYS = ["goals", "assists", "points", "plus_minus", "pim", "ppp", "shp", "gwg", "shots", "hits", "blocks", "fow"]
GOALIE_KEYS = ["wins", "losses", "ot_losses", "saves", "goals_against", "shutouts"]

PREV_WEIGHT = 0.5
PRIOR_GAMES = 15
REGULAR_GP = 40
PRIOR_QUANTILE = 0.30


def fantasy_points(df: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    total = pd.Series(0.0, index=df.index)
    for stat, w in (weights or {}).items():
        if stat in df.columns and w:
            total = total + df[stat].fillna(0) * float(w)
    return total


def _pos_group(pos: pd.Series) -> pd.Series:
    p = pos.fillna("").str.upper()
    return p.map(lambda x: "G" if x == "G" else ("D" if x == "D" else "F"))


def score(current: pd.DataFrame, previous: pd.DataFrame, scoring: dict) -> pd.DataFrame:
    """One row per player: this season's pool points (fpts) and estimated points per game (fpg).

    `scoring` looks like {"skater": {...}, "goalie": {...}}.
    """
    cur = current.copy()
    cur["grp"] = _pos_group(cur["position"])
    is_g = cur["grp"].eq("G")
    cur["fpts"] = 0.0
    cur.loc[~is_g, "fpts"] = fantasy_points(cur[~is_g], scoring.get("skater", {}))
    cur.loc[is_g, "fpts"] = fantasy_points(cur[is_g], scoring.get("goalie", {}))

    if previous is not None and not previous.empty:
        p = previous.copy()
        p["grp"] = _pos_group(p["position"])
        pg = p["grp"].eq("G")
        p["pts_prev"] = 0.0
        p.loc[~pg, "pts_prev"] = fantasy_points(p[~pg], scoring.get("skater", {}))
        p.loc[pg, "pts_prev"] = fantasy_points(p[pg], scoring.get("goalie", {}))
        p = p.rename(columns={"gp": "gp_prev"})

        regulars = p[p["gp_prev"] >= REGULAR_GP]
        rates = regulars["pts_prev"] / regulars["gp_prev"]
        priors = rates.groupby(regulars["grp"]).quantile(PRIOR_QUANTILE).to_dict()

        cur = cur.merge(p[["player_id", "pts_prev", "gp_prev"]], on="player_id", how="left")
    else:
        priors = {}
        cur["pts_prev"] = 0.0
        cur["gp_prev"] = 0

    cur[["pts_prev", "gp_prev"]] = cur[["pts_prev", "gp_prev"]].fillna(0)
    prior = cur["grp"].map(priors).fillna(0.0)
    k = PRIOR_GAMES if priors else 0
    num = cur["pts_prev"] * PREV_WEIGHT + cur["fpts"] + k * prior
    den = cur["gp_prev"] * PREV_WEIGHT + cur["gp"] + k
    cur["fpg"] = (num / den.where(den > 0)).fillna(0.0)

    out = cur.drop(columns=["grp", "pts_prev", "gp_prev"])
    return out.sort_values("fpg", ascending=False).reset_index(drop=True)
