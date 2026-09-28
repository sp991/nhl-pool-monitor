# NHL Pool Monitor

Self-hosted tool that follows two NHL pools (Yahoo Fantasy and PoolExpert), scores every
player with each pool's own rules, and suggests moves. Runs on TrueNAS as a Docker app.

## How it works

- **collector** refreshes every 20 minutes: NHL season stats and this week's schedule
  (public NHL API), Yahoo rosters and scoring (official Yahoo API through `yfpy`), and
  PoolExpert rosters: yours and every team's, so their players aren't suggested as pickups.
- **Scoring**: points per game under each pool's rules. Early in the season it blends
  with last season until a player has 20 games, so two lucky games don't dominate.
- **Recommendations**: free agents whose points per game beat your weakest player at the
  same position (F, D, G), with their number of games this week; projected points this week
  for your roster.
- **dashboard** (Streamlit) shows it all at `http://<truenas-ip>:30050`.
- Every push to `main` runs the tests and publishes `ghcr.io/sp991/nhl-pool-monitor:latest`;
  Watchtower on the server picks up new images automatically.

## One-time setup

1. **Yahoo app**: create one at https://developer.yahoo.com/apps/ (Fantasy Sports: Read,
   redirect URI `https://localhost:8080`). Keep the Client ID and Client Secret.
2. **Folders on TrueNAS**: create `data/` and `config/` in a dataset, e.g.
   `/mnt/Main/nhl-pool-monitor/`. Copy `config/pools.example.yaml` to
   `config/pools.yaml` there and fill it in.
3. **Image**: `ghcr.io/sp991/nhl-pool-monitor` is public (code only, no secrets), so
   TrueNAS and Watchtower pull it without a registry login.
4. **Install**: Apps → Discover Apps → ⋮ → Install via YAML, paste `docker-compose.yml`
   then replace the four `PASTE_...` values (Yahoo keys, PoolExpert sign-in).
5. **Yahoo login, once**: in the TrueNAS shell,
   `docker exec -it <collector-container> python -m app.yahoo_login`, open the printed URL,
   approve, then copy the code from the address bar (the page itself
   fails to load: `https://localhost:8080/?code=...`) and paste it. The token is stored in `data/.env` and refreshes itself.

## PoolExpert access

PoolExpert has no API, so pages are read as HTML. Its sign-in form uses a JavaScript
anti-bot field, so the collector signs in with headless Chromium **only when the saved
session has expired** ("remember me" checked), saves the cookies to `data/`, and does all
regular reads with plain HTTP. Set `POOLEXPERT_EMAIL` and `POOLEXPERT_PASSWORD` in the app's
environment. The pool admin makes all roster changes, so suggestions are to send to the admin.

## Local development

```bash
pip install -r requirements.txt
python -m pytest -q
DATA_DIR=./data CONFIG_PATH=./config/pools.yaml python -m app.collector --once
streamlit run app/dashboard.py
```

## Roadmap

- PoolExpert bonuses not yet modelled: OT/SO, hat tricks, player of the week/month, goalie points
- Live game-night view from PoolExpert's real-time endpoint
- Injury and goalie-start alerts through Home Assistant
- Optional AI-written daily summary
