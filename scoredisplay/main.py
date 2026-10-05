import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

API_URL = os.getenv(
    "SCORE_API_URL",
    "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
)
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL_SECONDS", "15"))

log = logging.getLogger("scoredisplay")

state: dict = {"games": [], "updated": None, "error": None}


def parse(data: dict) -> list[dict]:
    games = []
    for event in data.get("events", []):
        comp = event["competitions"][0]
        teams = comp["competitors"]
        games.append(
            {
                "name": event.get("shortName", event.get("name", "")),
                "status": event.get("status", {}).get("type", {}).get("detail", ""),
                "teams": [
                    {"name": t["team"]["displayName"], "score": t.get("score", "")}
                    for t in teams
                ],
            }
        )
    return games


async def poll_forever() -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        while True:
            try:
                resp = await client.get(API_URL)
                resp.raise_for_status()
                state["games"] = parse(resp.json())
                state["updated"] = time.time()
                state["error"] = None
            except Exception as exc:  # keep the service alive on any failure
                log.warning("poll failed: %s", exc)
                state["error"] = str(exc)
            await asyncio.sleep(POLL_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(poll_forever())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Scores</title>
<style>
body{font-family:sans-serif;background:#111;color:#eee;margin:2rem}
.game{border:1px solid #444;border-radius:8px;padding:1rem;margin:.5rem 0}
.row{display:flex;justify-content:space-between;font-size:1.3rem}
.status{color:#9ab;font-size:.9rem}
#meta{color:#888}
</style></head>
<body><h1>Scores</h1><div id="meta"></div><div id="games"></div>
<script>
async function refresh(){
  try{
    const d = await (await fetch('/api/scores')).json();
    document.getElementById('games').innerHTML = d.games.map(g =>
      `<div class="game"><div class="status">${g.status}</div>` +
      g.teams.map(t => `<div class="row"><span>${t.name}</span><b>${t.score}</b></div>`).join('') +
      `</div>`).join('');
    document.getElementById('meta').textContent = (d.error ? 'Error: ' + d.error + ' | ' : '') +
      (d.updated ? 'Updated ' + new Date(d.updated*1000).toLocaleTimeString() : 'Waiting for data...');
  }catch(e){document.getElementById('meta').textContent='Connection lost';}
}
refresh(); setInterval(refresh, 5000);
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return PAGE


@app.get("/api/scores")
async def scores() -> dict:
    return state
