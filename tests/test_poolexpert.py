from app.poolexpert import PoolExpertClient

HTML = """
<div class="row"><div><a href="gplayer.aspx?h=101" data-playerid="101" data-date="10012"
  data-poolid="188663">Nathan MacKinnon</a></div><div>COL</div></div>
<div class="row"><div><a href="gplayer.aspx?h=202" data-playerid="202">Cale Makar</a></div></div>
<div class="row"><div><a href="gplayer.aspx?h=101" data-playerid="101">Nathan MacKinnon</a></div></div>
<a href="gplayer.aspx?h=303">No data attribute</a>
<a href="gplayer.aspx?h=10017" data-playerid="10017" data-type="2">Avalanche Colorado</a>
"""


def test_player_links_are_parsed_once():
    players = PoolExpertClient._players(HTML)
    assert players == [
        {"pe_id": 101, "name": "Nathan MacKinnon"},
        {"pe_id": 202, "name": "Cale Makar"},
    ]


def test_redirect_to_demo_pool_means_signed_out(monkeypatch):
    import httpx
    import pytest
    from app import poolexpert

    def handler(request):
        if "gcomp.aspx" in request.url.path:
            return httpx.Response(302, headers={"Location": "https://www.poolexpert.com/en/grank.aspx?j=57146"})
        return httpx.Response(200, text="<html>demo pool</html>")

    c = PoolExpertClient(188663, 2289042)
    c.http = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    with pytest.raises(poolexpert.SessionExpired):
        c._get("gcomp.aspx", {"ba": 2289042})
    assert "demo" in c._get("grank.aspx", {"j": 188663})   # no redirect: fine


def test_pool_is_selected_again_after_sign_in(monkeypatch):
    """A fresh session only serves the roster once our pool has been opened."""
    import httpx
    from app import poolexpert

    state = {"signed_in": False, "pool": None}

    def handler(request):
        path, q = request.url.path, dict(request.url.params)
        if "grank.aspx" in path:
            if state["signed_in"]:
                state["pool"] = q.get("j")
            return httpx.Response(200, text="<html>ranking</html>")
        if "gcomp.aspx" in path and state["pool"] == "188663":
            return httpx.Response(200, text='<a data-playerid="1">Player One</a>')
        return httpx.Response(302, headers={"Location": "https://www.poolexpert.com/en/grank.aspx?j=57146"})

    def fake_client(cookies):
        return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)

    def fake_login(pool_id=None, entry_id=None):
        state["signed_in"] = True
        return []

    monkeypatch.setattr(poolexpert, "browser_login", fake_login)
    monkeypatch.setattr(PoolExpertClient, "_client", staticmethod(fake_client))
    c = PoolExpertClient(188663, 2289042)
    assert c.my_roster() == [{"pe_id": 1, "name": "Player One"}]
