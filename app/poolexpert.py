"""PoolExpert access.

PoolExpert is ASP.NET WebForms with no JSON API. The sign-in form carries a hidden
`pxpf` field filled by JavaScript, so a plain HTTP login may be rejected. Strategy:

- Poll with plain HTTP (httpx) using saved cookies.
- Only when the session has expired, log in once with headless Chromium (Playwright),
  "remember me" checked, and save the new cookies.
"""
from __future__ import annotations

import json
import logging
import os

import httpx
from bs4 import BeautifulSoup

from .config import DATA_DIR

log = logging.getLogger(__name__)

BASE = "https://www.poolexpert.com/en"
COOKIE_FILE = DATA_DIR / "poolexpert_cookies.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
FORM = "ctl00$ph_cc$ucTopUserLoginForm$"


class SessionExpired(Exception):
    pass


def _load_cookies() -> list[dict]:
    try:
        return json.loads(COOKIE_FILE.read_text())
    except Exception:
        return []


def browser_login() -> list[dict]:
    """Sign in with headless Chromium and store the cookies. Runs only when needed."""
    from playwright.sync_api import sync_playwright

    email, pwd = os.getenv("POOLEXPERT_EMAIL"), os.getenv("POOLEXPERT_PASSWORD")
    if not email or not pwd:
        raise RuntimeError("POOLEXPERT_EMAIL / POOLEXPERT_PASSWORD are not set")

    log.info("PoolExpert session expired: signing in with headless browser")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=UA, locale="en-CA")
        page = ctx.new_page()
        page.goto(f"{BASE}/signinform.aspx", wait_until="networkidle")
        page.fill(f'input[name="{FORM}email"]', email)
        page.fill(f'input[name="{FORM}pwd"]', pwd)
        remember = page.locator(f'input[name="{FORM}remember"]')
        if remember.count() and not remember.first.is_checked():
            remember.first.check(force=True)
        with page.expect_navigation(wait_until="networkidle", timeout=30000):
            page.press(f'input[name="{FORM}pwd"]', "Enter")
        if "signinform" in page.url.lower():
            browser.close()
            raise RuntimeError("PoolExpert login failed: still on the sign-in page (check credentials)")
        cookies = ctx.cookies()
        browser.close()

    COOKIE_FILE.write_text(json.dumps(cookies))
    log.info("PoolExpert login OK, %d cookies saved", len(cookies))
    return cookies


class PoolExpertClient:
    def __init__(self, pool_id: int, entry_id: int):
        self.pool_id, self.entry_id = pool_id, entry_id
        self.http = self._client(_load_cookies())

    @staticmethod
    def _client(cookies: list[dict]) -> httpx.Client:
        jar = httpx.Cookies()
        for c in cookies:
            jar.set(c["name"], c["value"], domain=c.get("domain", ""), path=c.get("path", "/"))
        return httpx.Client(cookies=jar, headers={"User-Agent": UA}, timeout=30, follow_redirects=True)

    def _get(self, path: str, params: dict | None = None) -> str:
        r = self.http.get(f"{BASE}/{path}", params=params)
        r.raise_for_status()
        final = str(r.url).lower()
        if "signinform" in final or f'name="{FORM}pwd"' in r.text:
            raise SessionExpired
        # When not signed in, private pages quietly redirect elsewhere (e.g. to the
        # public demo pool) instead of the sign-in page.
        if r.history and path.lower() not in final:
            log.info("PoolExpert redirected %s to %s: treating session as expired", path, r.url)
            raise SessionExpired
        return r.text

    def _page(self, path: str, params: dict | None = None) -> str:
        """Fetch a page, logging in once with the browser if the session has expired."""
        try:
            html = self._get(path, params)
        except SessionExpired:
            self.http = self._client(browser_login())
            try:
                html = self._get(path, params)
            except SessionExpired:
                raise RuntimeError(
                    f"PoolExpert still redirects {path} after signing in: check the pool/entry ids "
                    "and that this account belongs to the pool"
                ) from None
        return html

    def _select_pool(self) -> None:
        # Most pages rely on the active pool held in the server session.
        self._page("grank.aspx", {"j": self.pool_id})

    @staticmethod
    def _players(html: str) -> list[dict]:
        """Every distinct player link on a page: `a[data-playerid]` inside div grids."""
        soup = BeautifulSoup(html, "html.parser")
        seen, out = set(), []
        for a in soup.select("a[data-playerid]"):
            pid = a.get("data-playerid")
            name = a.get_text(" ", strip=True)
            if not pid or not name or pid in seen:
                continue
            seen.add(pid)
            out.append({"pe_id": int(pid), "name": name})
        return out

    def my_roster(self) -> list[dict]:
        self._select_pool()
        players = self._players(self._page("gcomp.aspx", {"ba": self.entry_id}))
        if not players:
            log.warning("PoolExpert roster page returned no players (season not started or layout changed)")
        return players

    def all_rostered(self) -> list[dict]:
        """Players on any team in the pool (they are not available as pickups)."""
        self._select_pool()
        return self._players(self._page("gallinone.aspx"))
