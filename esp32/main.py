import asyncio

import scores
import web
import wifi


async def main():
    while not await wifi.connect():
        print("wifi connect failed, retrying")
    wifi.sync_time()
    await web.serve()
    print("http://%s/" % wifi.sta.ifconfig()[0])
    scores.start()
    await wifi.keep_alive()


asyncio.run(main())
