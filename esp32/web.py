import asyncio
import json

import scores

HEAD = "HTTP/1.0 {} \r\nContent-Type: {}\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n"


async def send_json(w, obj):
    w.write(HEAD.format(200, "application/json"))
    w.write(json.dumps(obj))
    await w.drain()


async def handle(r, w):
    try:
        line = await r.readline()
        parts = line.decode().split()
        while (await r.readline()) not in (b"\r\n", b"\n", b""):
            pass
        if len(parts) < 2:
            return
        method, path = parts[0], parts[1].split("?")[0]
        if method == "GET" and path == "/":
            w.write(HEAD.format(200, "text/html; charset=utf-8"))
            with open("page.html", "rb") as f:
                while chunk := f.read(4096):
                    w.write(chunk)
                    await w.drain()
        elif method == "GET" and path == "/api/scores":
            await send_json(w, scores.state)
        elif method == "POST" and path == "/api/refresh":
            target = scores.request_refresh()
            for _ in range(600):  # up to 60 s
                if scores.finished >= target:
                    break
                await asyncio.sleep_ms(100)
            await send_json(w, scores.state)
        else:
            w.write(HEAD.format(404, "text/plain") + "Not found")
            await w.drain()
    except Exception as exc:
        print("request failed:", exc)
    finally:
        w.close()
        await w.wait_closed()


async def serve(port=80):
    return await asyncio.start_server(handle, "0.0.0.0", port)
