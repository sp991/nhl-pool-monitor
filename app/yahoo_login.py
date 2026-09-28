"""One-time Yahoo login. Run interactively:

    docker compose run --rm collector python -m app.yahoo_login

It prints a Yahoo URL; open it, approve, paste the code back. The token is saved
to the data volume and refreshed automatically afterwards.
"""
from .config import load_pools
from .yahoo import _query


def main() -> None:
    pool = next((p for p in load_pools() if p.get("source") == "yahoo"), None)
    if not pool:
        raise SystemExit("No pool with source: yahoo in config.")
    league = _query(pool["league_id"], interactive=True).get_league_metadata()
    print(f"Connected to Yahoo league: {getattr(league, 'name', pool['league_id'])}")


if __name__ == "__main__":
    main()
