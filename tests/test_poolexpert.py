from app.poolexpert import PoolExpertClient

HTML = """
<div class="row"><div><a href="gplayer.aspx?h=101" data-playerid="101" data-date="10012"
  data-poolid="188663">Nathan MacKinnon</a></div><div>COL</div></div>
<div class="row"><div><a href="gplayer.aspx?h=202" data-playerid="202">Cale Makar</a></div></div>
<div class="row"><div><a href="gplayer.aspx?h=101" data-playerid="101">Nathan MacKinnon</a></div></div>
<a href="gplayer.aspx?h=303">No data attribute</a>
"""


def test_player_links_are_parsed_once():
    players = PoolExpertClient._players(HTML)
    assert players == [
        {"pe_id": 101, "name": "Nathan MacKinnon"},
        {"pe_id": 202, "name": "Cale Makar"},
    ]
