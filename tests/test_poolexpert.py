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
