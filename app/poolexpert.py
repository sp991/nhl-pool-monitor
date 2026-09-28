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
# data-type on player links: 1 = G, 2 = team, 3/4/5 = forwards, 6 = D (seen on gcomp.aspx)
TEAM_TYPE = "2"


class SessionExpired(Exception):
    pass


def _load_cookies() -> list[dict]:
    try:
        return json.loads(COOKIE_FILE.read_text())
    except Exception:
        return []


LOGIN_FAIL_FILE = DATA_DIR / "poolexpert_login_failed.json"
LOGIN_FAIL_SHOT = DATA_DIR / "poolexpert_login_failed.png"
# After a failed sign-in, wait this long before trying again: never hammer the
# account (repeated failures can lock it) if the password is wrong.
LOGIN_BACKOFF_SECONDS = 6 * 3600
SIGNIN_BUTTON = "#ctl00_ph_cc_ucTopUserLoginForm_btnSignIn_input"


def _login_blocked_until() -> float:
    try:
        return float(json.loads(LOGIN_FAIL_FILE.read_text())["retry_after"])
    except Exception:
        return 0.0


def browser_login() -> list[dict]:
    """Sign in with headless Chromium and store the cookies. Runs only when needed.

    The sign-in form is ASP.NET + Telerik: the "Sign in" control is a plain
    type=button whose script fills hidden fields (e.g. pxpf) and posts the form,
    so the fields are typed like a person would and the real button is clicked.
    """
    import time

    from playwright.sync_api import sync_playwright

    email, pwd = os.getenv("POOLEXPERT_EMAIL"), os.getenv("POOLEXPERT_PASSWORD")
    if not email or not pwd:
        raise RuntimeError("POOLEXPERT_EMAIL / POOLEXPERT_PASSWORD are not set")
    wait = _login_blocked_until() - time.time()
    if wait > 0:
        raise RuntimeError(
            f"PoolExpert sign-in failed recently; next attempt in {wait / 3600:.1f} h "
            f"(delete {LOGIN_FAIL_FILE.name} in the data folder to retry now)"
        )

    log.info("PoolExpert session expired: signing in with headless browser")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=UA, locale="en-CA", viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        try:
            page.goto(f"{BASE}/signinform.aspx", wait_until="networkidle", timeout=45000)
            email_box = page.locator(f'input[name="{FORM}email"]')
            pwd_box = page.locator(f'input[name="{FORM}pwd"]')
            email_box.click()
            email_box.press_sequentially(email, delay=40)
            pwd_box.click()
            pwd_box.press_sequentially(pwd, delay=40)
            remember = page.locator(f'input[name="{FORM}remember"]')
            if remember.count() and not remember.first.is_checked():
                remember.first.check(force=True)
            page.locator(SIGNIN_BUTTON).click()
            try:
                page.wait_for_url(lambda u: "signinform" not in u.lower(), timeout=30000)
            except Exception:
                pass
            page.wait_for_load_state("networkidle", timeout=30000)

            if "signinform" in page.url.lower() or pwd_box.count():
                # Keep evidence for diagnosis (no credentials are in it: the password box is masked).
                page.screenshot(path=str(LOGIN_FAIL_SHOT), full_page=True)
                msg = page.evaluate(
                    """() => [...document.querySelectorAll(
                        '[class*="error" i],[class*="valid" i],[id*="error" i],[id*="msg" i],.rwDialogText')]
                        .map(e => e.innerText.trim()).filter(t => t && t.length < 200).slice(0, 3).join(' | ')"""
                )
                LOGIN_FAIL_FILE.write_text(json.dumps({
                    "at": time.time(), "retry_after": time.time() + LOGIN_BACKOFF_SECONDS, "page_message": msg,
                }))
                raise RuntimeError(
                    "PoolExpert sign-in failed"
                    + (f": PoolExpert says '{msg}'" if msg else " (no message on the page)")
                    + f". Screenshot saved as {LOGIN_FAIL_SHOT.name} in the data folder; "
                    "next automatic attempt in 6 h."
                )
            cookies = ctx.cookies()
        finally:
            browser.close()

    LOGIN_FAIL_FILE.unlink(missing_ok=True)
    LOGIN_FAIL_SHOT.unlink(missing_ok=True)
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
            if a.get("data-type") == TEAM_TYPE:  # team slot (e.g. "Avalanche Colorado"), not a player
                continue
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
