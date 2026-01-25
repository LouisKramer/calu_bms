import time, socket, struct
import asyncio
from common.logger import *
from machine import RTC

ntp_log = Logger()
class ntp_sync:
    def __init__(self, host, port, timeout, interval):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.interval = interval
        self.rtc = RTC()
    async def sync_with_ntp(self):
        ntp_log.info("Syncing with NTP server...")
        ntp_packet = bytearray(48)
        ntp_packet[0] = 0x1B  # LI=0, VN=3, Mode=3 (client)

        addr = socket.getaddrinfo(self.host, self.port)[0][-1]
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(self.timeout)
        try:
            s.sendto(ntp_packet, addr)
            # Use asyncio.sleep to allow other tasks to run while waiting
            await asyncio.sleep(0.1)
            msg, _ = s.recvfrom(48)
            # NTP timestamp is at offset 40 (seconds since 1900)
            ntp_time = struct.unpack("!I", msg[40:44])[0]
            # Convert to Unix epoch 
            epoch = ntp_time - 3155673600  # NTP (1900) → MicroPython epoch (2000)
            # Set RTC
            tm = time.gmtime(epoch)
            # MicroPython RTC expects weekday in range 1-7 (Monday=1), utime.gmtime gives 0-6 (Monday=0)
            self.rtc .datetime((tm[0], tm[1], tm[2], tm[6] + 1, tm[3], tm[4], tm[5], 0))
            ntp_log.info(f"RTC set to UTC:{self.rtc.datetime()}")
        except Exception as ex:
            ntp_log.warn(f"NTP sync failed: using default fallback (2024-01-01) {ex}")
            fallback_epoch = 1704067200
            tm = time.gmtime(fallback_epoch)
            self.rtc.datetime((tm[0], tm[1], tm[2], tm[6] + 1, tm[3], tm[4], tm[5], 0))
            ntp_log.info(f"RTC set to fallback UTC:{self.rtc .datetime()}")
            return False
        finally:
            s.close()

    async def ntp_task(self):
        while True:
            await self.sync_with_ntp()
            await asyncio.sleep(self.interval)