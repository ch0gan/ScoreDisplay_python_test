# ESP32-S3 port (MicroPython)

Phase 1: WiFi, NTP, web page, and score polling. The HUB75 display (Seengreat adapter v2.2, 128x64) comes later.

## Requirements

- ESP32-S3 with PSRAM (the ESPN scoreboard JSON is far larger than internal RAM). Flash a MicroPython build with SPIRAM, e.g. `ESP32_GENERIC_S3` `SPIRAM_OCT` (octal PSRAM, N16R8 boards) or the plain SPIRAM build (quad PSRAM).
- `mpremote` (`pip install mpremote`).

## Deploy

1. Copy `esp32/secrets.example.py` to `esp32/secrets.py` and fill in the WiFi credentials (git-ignored).
2. Install the HTTP client on the board: `mpremote mip install requests`
3. Copy files:
   ```
   cd esp32
   mpremote cp secrets.py config.py wifi.py scores.py web.py page.html main.py :
   ```
4. `mpremote reset` (or `mpremote run main.py` to see logs). The IP is printed on boot; open `http://<ip>/`.

## Notes

- Same endpoints as the desktop version: `/`, `GET /api/scores`, `POST /api/refresh`.
- HTTPS certificates are not verified by `requests` on MicroPython.
- The fetch is blocking, so the web server pauses for the duration of a poll.
- Time comes from NTP (UTC); `state["updated"]` is converted to the Unix epoch for the page.
