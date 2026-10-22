import _thread
import deflate
import gc
import io
import json
import time

import requests

import config

state = {"games": [], "updated": None, "error": None}
refresh_flag = False
started = 0
finished = 0


def parse(data):
    games = []
    for event in data.get("events", []):
        comp = event["competitions"][0]
        status = event.get("status", {})
        stype = status.get("type", {})
        situation = comp.get("situation") or {}
        game = {
            "id": event["id"],
            "date": event.get("date", ""),
            "state": stype.get("state", "pre"),  # pre | in | post
            "detail": stype.get("shortDetail", ""),
            "period": status.get("period", 0),
            "clock": status.get("displayClock", ""),
            "down": situation.get("shortDownDistanceText", ""),
            "possession": situation.get("possession", ""),
        }
        for t in comp["competitors"]:
            side = t["homeAway"]
            team = t["team"]
            game[side] = {
                "id": team["id"],
                "abbr": team.get("abbreviation", ""),
                "name": team.get("displayName", ""),
                "logo": team.get("logo", ""),
                "score": t.get("score", "0"),
                "timeouts": situation.get(side + "Timeouts"),
            }
        if "home" in game and "away" in game:
            game["ball_pct"] = ball_position(situation.get("possessionText", ""), game)
            game["ball_text"] = situation.get("possessionText", "")
            games.append(game)
    return games


def ball_position(text, game):
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


def parse_iso(s):
    """'2025-09-07T17:00Z' -> seconds since 2000-01-01 UTC, or None."""
    try:
        return time.mktime((int(s[0:4]), int(s[5:7]), int(s[8:10]), int(s[11:13]), int(s[14:16]), 0, 0, 0))
    except (ValueError, IndexError):
        return None


def get_json(url):
    gc.collect()
    t0 = time.ticks_ms()
    r = requests.get(url, headers={"Accept-Encoding": "gzip"})
    t1 = time.ticks_ms()
    try:
        if r.status_code != 200:
            raise OSError("HTTP %d" % r.status_code)
        raw = r.content
    finally:
        r.close()
    t2 = time.ticks_ms()
    if raw[:2] == b"\x1f\x8b":
        with deflate.DeflateIO(io.BytesIO(raw), deflate.GZIP) as d:
            data = json.load(d)
    else:
        data = json.loads(raw)
    print("connect+headers %d ms, body %d ms (%d bytes), parse %d ms" % (
        time.ticks_diff(t1, t0), time.ticks_diff(t2, t1), len(raw), time.ticks_diff(time.ticks_ms(), t2)))
    return data


def fetch_games():
    data = get_json(config.API_URL)
    games = parse(data)
    nxt_week = None
    if games and all(g["state"] == "post" for g in games):
        nxt_week = (data["week"]["number"] + 1, data["season"]["type"])
    del data
    gc.collect()
    if nxt_week:
        # Week is finished: also load the next week's games.
        try:
            url = "%s?week=%d&seasontype=%s" % (config.API_URL, nxt_week[0], nxt_week[1])
            nd = get_json(url)
            games += parse(nd)
            del nd
        except Exception as exc:
            print("next week fetch failed:", exc)
        gc.collect()
    return games


def next_delay(games):
    """Fast while games are live or about to start; otherwise sleep until just before the next kickoff."""
    now = time.time()
    delay = config.IDLE_INTERVAL
    for g in games:
        if g["state"] == "in":
            return config.POLL_INTERVAL
        if g["state"] != "pre":
            continue
        start = parse_iso(g["date"])
        if start is None:
            continue
        until_wake = start - now - config.KICKOFF_LEAD
        if until_wake <= 0:
            return config.POLL_INTERVAL
        delay = min(delay, until_wake)
    return max(delay, config.POLL_INTERVAL)


def poll_once():
    """Fetch from the API, update state, and return the delay before the next scheduled poll."""
    try:
        state["games"] = fetch_games()
        # Unix epoch for the browser (device epoch is 2000-01-01).
        state["updated"] = time.time() + 946684800
        state["error"] = None
        return next_delay(state["games"])
    except Exception as exc:  # keep the service alive on any failure
        print("poll failed:", exc)
        state["error"] = str(exc)
        return config.POLL_INTERVAL


def request_refresh():
    """Ask the worker for a fresh fetch; returns the counter value `finished` must reach."""
    global refresh_flag
    refresh_flag = True
    return started + 1


def _worker():
    global refresh_flag, started, finished
    deadline = 0
    while True:
        if refresh_flag or time.time() >= deadline:
            refresh_flag = False
            started += 1
            deadline = time.time() + poll_once()
            finished = started
        else:
            time.sleep_ms(200)


def start():
    # TLS needs more stack than the default thread size.
    _thread.stack_size(24 * 1024)
    _thread.start_new_thread(_worker, ())
