import asyncio
import network
import ntptime
import config

sta = network.WLAN(network.STA_IF)


async def connect(timeout=20):
    sta.active(True)
    sta.config(txpower=20)  # dBm; the driver clamps to the chip maximum
    if sta.isconnected():
        return True
    sta.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
    for _ in range(timeout * 10):
        if sta.isconnected():
            print("wifi up:", sta.ifconfig()[0])
            return True
        await asyncio.sleep_ms(100)
    sta.disconnect()
    return False


def sync_time():
    # Sets the RTC to UTC; time.time() is then seconds since 2000-01-01 UTC.
    try:
        ntptime.settime()
        return True
    except OSError as exc:
        print("ntp failed:", exc)
        return False


async def keep_alive():
    while True:
        if not sta.isconnected():
            print("wifi lost, reconnecting")
            await connect()
        await asyncio.sleep(10)
