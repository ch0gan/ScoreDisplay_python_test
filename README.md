# ScoreDisplay_python_test

Service that polls a scores API in the background and serves a self-refreshing web page.

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

