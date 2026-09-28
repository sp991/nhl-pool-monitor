"""Streamlit dashboard: reads what the collector stored."""
from __future__ import annotations

import json
import sqlite3

import pandas as pd
import streamlit as st

from app.config import DB_PATH

st.set_page_config(page_title="NHL Pool Monitor", page_icon="🏒", layout="wide")
st.title("NHL Pool Monitor")

if not DB_PATH.exists():
    st.info("No data yet. The collector runs its first refresh at startup; reload in a minute.")
    st.stop()

con = sqlite3.connect(DB_PATH)


def table(name: str) -> pd.DataFrame:
    try:
        return pd.read_sql(f'SELECT * FROM "{name}"', con)
    except Exception:
        return pd.DataFrame()


meta = table("meta")
kv = dict(zip(meta["k"], meta["v"])) if not meta.empty else {}
status = json.loads(kv["status"]) if "status" in kv else {}
st.caption(f"Last refresh: {status.get('last_run', '—')} · Season {status.get('season', '—')}")
if "last_error" in kv:
    err = json.loads(kv["last_error"])
    if err.get("at", "") > status.get("last_run", ""):
        st.error(f"Last refresh attempt failed at {err['at']}: {err['error']}")

pools = status.get("pools", {})
if not pools:
    st.warning("No pools processed yet.")
    st.stop()

tabs = st.tabs([p["name"] for p in pools.values()])
for tab, (pid, info) in zip(tabs, pools.items()):
    with tab:
        if not info.get("ok"):
            st.error(f"Last refresh failed: {info.get('error')}")
            shot = DB_PATH.parent / "poolexpert_login_failed.png"
            rec = DB_PATH.parent / "poolexpert_login_failed.json"
            if "PoolExpert" in str(info.get("error")) and shot.exists():
                with st.expander("What the server's browser saw at sign-in", expanded=True):
                    if rec.exists():
                        details = json.loads(rec.read_text())
                        details.pop("retry_after", None)
                        st.json(details)
                    st.image(str(shot))
            continue
        if info.get("note"):
            st.info(info["note"])
        if info.get("unmatched"):
            st.warning("Players not matched to NHL data: " + ", ".join(info["unmatched"]))

        st.subheader("Suggested moves")
        adds = table(f"pickups_{pid}")
        if adds.empty:
            st.write("No free agent currently beats your weakest player at their position.")
        else:
            st.dataframe(adds, hide_index=True, use_container_width=True)

        st.subheader("My roster — projected points this week")
        roster = table(f"roster_{pid}")
        cols = [c for c in ["name", "team", "position", "gp", "fpts", "fpg", "games_week", "proj_week"] if c in roster]
        st.dataframe(roster[cols].round(2), hide_index=True, use_container_width=True)
        if not roster.empty:
            st.metric("Projected pool points this week", round(roster["proj_week"].sum(), 1))

        with st.expander("Top available and rostered players by points/game"):
            top = table(f"top_{pid}")
            cols = [c for c in ["name", "team", "position", "gp", "fpts", "fpg"] if c in top]
            st.dataframe(top[cols].round(2), hide_index=True, use_container_width=True)

        with st.expander("Scoring rules in use"):
            st.json(info.get("scoring", {}))
