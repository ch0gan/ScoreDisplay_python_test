# ScoreDisplay_python_test

Service that polls a scores API in the background and serves a self-refreshing web page.

## Score display API

The service polls an upstream scoreboard API and exposes the latest normalized
data as JSON. The default upstream is ESPN's NFL scoreboard endpoint:

```text
https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard
```

The display service listens on port `8000` in the run command below. The API
does not require authentication and currently accepts no query parameters.

### Read the current scores

```http
GET /api/scores
```

Example using curl:

```sh
curl http://localhost:8000/api/scores
```

The response is JSON with a top-level `games` array, an `updated` timestamp,
and an `error` field:

```json
{
	"games": [
		{
			"id": "401547404",
			"date": "2025-09-07T17:00Z",
			"state": "in",
			"detail": "2nd",
			"period": 2,
			"clock": "08:42",
			"down": "3rd & 4",
			"possession": "12",
			"away": {
				"id": "12",
				"abbr": "KC",
				"name": "Kansas City Chiefs",
				"logo": "https://example.com/kc.png",
				"score": "14",
				"timeouts": 2
			},
			"home": {
				"id": "7",
				"abbr": "BUF",
				"name": "Buffalo Bills",
				"logo": "https://example.com/buf.png",
				"score": "10",
				"timeouts": 3
			},
			"ball_pct": 38.0,
			"ball_text": "KC 38"
		}
	],
	"updated": 1757264400.0,
	"error": null
}
```

This is a representative live-game response; values and available game data
depend on the upstream provider. Fields are:

| Field | Meaning |
| --- | --- |
| `games` | Games currently included in the upstream scoreboard response. It can be empty. |
| `updated` | Unix timestamp in seconds for the last successful data fetch, or `null` before one succeeds. |
| `error` | `null` when the last fetch succeeded; otherwise an error string. A fetch failure does not necessarily clear previously fetched games. |
| `id` | Upstream event ID. |
| `date` | Scheduled game date/time as an ISO-8601 string. |
| `state` | `pre` (not started), `in` (live), or `post` (final). |
| `detail` | Upstream short status text, such as quarter or final status. |
| `period`, `clock` | Period number and display clock; values may be `0` or empty when not applicable. |
| `down` | Short down-and-distance text; often empty outside live play. |
| `possession` | ID of the team with possession, or an empty/missing value when unavailable. Compare with `home.id` and `away.id`. |
| `home`, `away` | Team objects containing upstream `id`, abbreviation (`abbr`), display `name`, logo URL, score, and `timeouts`. Scores are strings; `timeouts` can be `null`. |
| `ball_pct` | Approximate field position from 0 to 100, oriented from the away end zone to the home end zone; `null` when it cannot be determined. |
| `ball_text` | Upstream field-position text, such as `KC 38`; may be empty. |

Clients should treat optional or unavailable values as missing, `null`, or
empty strings as applicable, rather than assuming every game is live or has
complete situational data.

### Request a fresh fetch

```http
POST /api/refresh
```

No request body is required. The service triggers an upstream fetch and returns
the same JSON structure as `GET /api/scores`:

```sh
curl -X POST http://localhost:8000/api/refresh
```

The desktop service performs the fetch before replying. On the ESP32, refresh
is queued for its polling worker and the request waits for completion (up to
about 60 seconds). The response currently uses HTTP 200 even when the upstream
fetch failed; check the JSON `error` field to determine whether the latest
fetch succeeded.

### Call it from a client

For example, Python can read the snapshot and use each game's normalized
fields without parsing the upstream provider's original response:

```python
import requests

base_url = "http://localhost:8000"
response = requests.get(f"{base_url}/api/scores", timeout=10)
response.raise_for_status()
snapshot = response.json()

if snapshot["error"]:
		print("Last fetch failed:", snapshot["error"])

for game in snapshot["games"]:
		print(
				game["away"]["abbr"], game["away"]["score"], "at",
				game["home"]["abbr"], game["home"]["score"], game["state"],
		)
```

To refresh before reading, send `POST /api/refresh` instead of `GET /api/scores`.
For a client on another device, replace `localhost` with the host running the
service, for example `http://192.168.1.20:8000`. The server must be reachable
on the network; the run command binds it to `0.0.0.0`.

### Build the same pattern for another scoreboard

1. Find the upstream provider's scoreboard URL and inspect its JSON response.
2. Set `SCORE_API_URL` to that URL and update `parse()` in
	 [`scoredisplay/main.py`](scoredisplay/main.py) to map provider fields into
	 the documented game shape.
3. Keep the API response stable for clients: return `games`, `updated`, and
	 `error`, and use `home`/`away` team objects and `pre`/`in`/`post` game states.
4. Call `GET /api/scores` to read the most recently fetched snapshot. Use
	 `POST /api/refresh` only when a client needs to request an immediate fetch;
	 otherwise the service polls on its own schedule.

The browser page uses these same two endpoints. The ESP32 implementation
provides the same paths and response shape; its server listens on port 80, so
use `http://<device-ip>/api/scores` or `http://<device-ip>/api/refresh` there.

## Run

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn scoredisplay.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000.

## Configuration (environment variables)

- `SCORE_API_URL`: API to poll (default: ESPN NFL scoreboard). Adapt `parse()` in `scoredisplay/main.py` for other response formats.
- `POLL_INTERVAL_SECONDS`: poll period (default 15).

