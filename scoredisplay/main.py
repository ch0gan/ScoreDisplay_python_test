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
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL_SECONDS", "5"))

log = logging.getLogger("scoredisplay")

state: dict = {"games": [], "updated": None, "error": None}


def parse(data: dict) -> list[dict]:
    games = []
    for event in data.get("events", []):
        comp = event["competitions"][0]
        status = event.get("status", {})
        situation = comp.get("situation") or {}
        game = {
            "id": event["id"],
            "date": event.get("date", ""),
            "state": status.get("type", {}).get("state", "pre"),  # pre | in | post
            "detail": status.get("type", {}).get("shortDetail", ""),
            "period": status.get("period", 0),
            "clock": status.get("displayClock", ""),
            "down": situation.get("shortDownDistanceText", ""),
            "possession": situation.get("possession", ""),
        }
        for t in comp["competitors"]:
            side = t["homeAway"]
            game[side] = {
                "id": t["team"]["id"],
                "abbr": t["team"].get("abbreviation", ""),
                "name": t["team"].get("displayName", ""),
                "logo": t["team"].get("logo", ""),
                "score": t.get("score", "0"),
                "timeouts": situation.get(f"{side}Timeouts"),
            }
        if "home" in game and "away" in game:
            game["ball_pct"] = ball_position(situation.get("possessionText", ""), game)
            game["ball_text"] = situation.get("possessionText", "")
            games.append(game)
    return games


def ball_position(text: str, game: dict) -> float | None:
    """Map text like 'DEN 35' to 0-100 from the away end zone to the home end zone."""
    parts = text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        return None
    abbr, yard = parts[0], int(parts[1])
    if abbr == game["away"]["abbr"]:
        return float(yard)
    if abbr == game["home"]["abbr"]:
        return float(100 - yard)
    return 50.0 if yard == 50 else None


async def fetch_games(client: httpx.AsyncClient) -> list[dict]:
    resp = await client.get(API_URL)
    resp.raise_for_status()
    data = resp.json()
    games = parse(data)
    if games and all(g["state"] == "post" for g in games):
        # Week is finished: also load the next week's games.
        params = {
            "week": data["week"]["number"] + 1,
            "seasontype": data["season"]["type"],
        }
        try:
            nxt = await client.get(API_URL, params=params)
            nxt.raise_for_status()
            games += parse(nxt.json())
        except Exception as exc:
            log.warning("next week fetch failed: %s", exc)
    return games


async def poll_forever() -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        while True:
            try:
                state["games"] = await fetch_games(client)
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
h2{margin:1.5rem 0 .5rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:1rem}
.game{background:#1c1c1c;border:1px solid #444;border-radius:10px;padding:.6rem}
.game.live{border-color:#3c3}
.teams{display:flex;align-items:stretch;justify-content:space-between;gap:.5rem}
.team{width:5.5rem;text-align:center}
.team img{width:64px;height:64px;object-fit:contain}
.abbr{font-weight:bold}
.to{letter-spacing:.2rem;color:#fc3;min-height:1.2rem}
.mid{flex:1;text-align:center;display:flex;flex-direction:column}
.mid .field{margin-top:auto}
.scores{display:flex;justify-content:center;gap:.8rem;font-size:2.2rem;font-weight:bold;align-items:center}
.scores span.poss{color:#fc3}
.down{color:#fc3;min-height:1.2rem}
.clock{color:#9ab;margin-top:.1rem}
.ball{color:#9ab;font-size:.8rem;margin-bottom:.4rem}
.has-ball .abbr::after{content:" \\1F3C8"}
.field{position:relative;height:14px;margin-top:.3rem;border-radius:4px;border:1px solid #2a5;
  background:linear-gradient(90deg,#363 0,#363 10%,#2a6a2a 10%,#2a6a2a 90%,#363 90%)}
.field .mark{position:absolute;top:-3px;font-size:14px;transform:translateX(-50%);line-height:1;white-space:nowrap;color:#fc3}
.fieldtxt{text-align:center;font-size:.8rem;color:#9ab}
#meta{color:#888}
</style></head>
<body><h1>Scores</h1><div id="meta"></div><div id="games"></div>
<script>
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const ORD = ['', '1st', '2nd', '3rd', '4th'];
function team(t, hasBall) {
  const to = t.timeouts == null ? '' : '\u25CF'.repeat(t.timeouts);
  return `<div class="team ${hasBall ? 'has-ball' : ''}"><img src="${esc(t.logo)}" alt=""><div class="abbr">${esc(t.abbr)}</div><div class="to">${to}</div></div>`;
}
function field(g) {
  if (g.state !== 'in' || g.ball_pct == null) return '';
  const pct = 10 + g.ball_pct * 0.8;
  const right = g.possession === g.away.id;
  const ball = '\\u{1F3C8}';
  const mark = right ? ball + '\u25B6' : '\u25C0' + ball;
  return `<div class="field"><span class="mark" style="left:${pct}%">${mark}</span></div>`;
}
function tile(g) {
  let down = '', clock;
  if (g.state === 'in') {
    down = g.down;
    clock = g.period > 4 ? `OT ${g.clock}` : `${ORD[g.period] || ''} ${g.clock}`;
  } else if (g.state === 'pre') {
    clock = new Date(g.date).toLocaleString([], {weekday:'short', hour:'numeric', minute:'2-digit'});
  } else {
    clock = g.detail;
  }
  const show = g.state !== 'pre';
  const live = g.state === 'in';
  return `<div class="game ${g.state === 'in' ? 'live' : ''}">` +
    `<div class="teams">${team(g.away, live && g.possession === g.away.id)}<div class="mid">` +
    `<div class="scores"><span>${show ? esc(g.away.score) : ''}</span><span>${show ? '-' : '@'}</span><span>${show ? esc(g.home.score) : ''}</span></div>` +
    `<div class="down">${esc(down)}</div><div class="clock">${esc(clock)}</div>${g.state === 'in' && g.ball_text ? `<div class="ball">Ball on ${esc(g.ball_text)}</div>` : ''}${field(g)}</div>${team(g.home, live && g.possession === g.home.id)}</div></div>`;
}
async function refresh(){
  try{
    const d = await (await fetch('/api/scores')).json();
    const byDate = (a, b) => a.date.localeCompare(b.date);
    const sections = [
      ['Live', d.games.filter(g => g.state === 'in').sort(byDate)],
      ['Upcoming', d.games.filter(g => g.state === 'pre').sort(byDate)],
      ['Final', d.games.filter(g => g.state === 'post').sort(byDate)],
    ];
    document.getElementById('games').innerHTML = sections.filter(s => s[1].length)
      .map(([title, gs]) => `<h2>${title}</h2><div class="grid">${gs.map(tile).join('')}</div>`).join('');
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
