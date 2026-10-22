import httpx
u = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard'
h = 'https://site.api.espn.com/apis/v2/scoreboard/header?sport=football&league=nfl&lang=en&region=us'
with httpx.Client(timeout=30.0) as c:
    r = c.get(u, headers={'Accept-Encoding': 'identity'})
    print('scoreboard_identity_bytes=' + str(len(r.content)))
    r = c.get(u, headers={'Accept-Encoding': 'gzip'})
    print('scoreboard_gzip_raw_bytes=' + str(r.num_bytes_downloaded) + ' content_encoding=' + r.headers.get('content-encoding', 'absent'))
    print('content_length=' + r.headers.get('content-length', 'absent') + ' transfer_encoding=' + r.headers.get('transfer-encoding', 'absent') + ' http_version=' + r.http_version)
    r = c.get(h)
    d = r.json()
    print('header_uncompressed_bytes=' + str(len(r.content)))
    print('header_top_level_keys=' + ','.join(d.keys()))
    x = d.get('events') or d.get('games') or []
    print('example_event_keys=' + (','.join(x[0].keys()) if x else 'absent'))
