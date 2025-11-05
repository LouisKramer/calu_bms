# slave.py
import network, espnow, time, binascii
import json
import asyncio
from machine import RTC
from common.common import *


# -------------------------------------------------
# 1. Configuration
# -------------------------------------------------
MASTER_MAC = b'\x24\x0a\xc4\xAA\xBB\xCC'   # <-- replace
SYNC_TIMEOUT = 10_000_000                 # 10 s without sync → drift warning

# -------------------------------------------------
# 2. Init
# -------------------------------------------------
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.config(channel=1)

e = espnow.ESPNow()
e.active(True)
e.add_peer(MASTER_MAC)

rtc = RTC()
rtc.datetime((2025, 1, 1, 3, 0, 0, 0, 0))   # arbitrary start

# Offset storage (microseconds)
offset_us = 0
last_sync = utime.ticks_us()
print("Slave ready – MAC:", ubinascii.hexlify(wlan.config('mac'), ':'))

# -------------------------------------------------
# 3. Helper: apply offset to RTC
# -------------------------------------------------
def apply_offset():
    """Add offset_us to the RTC (sub-second only)."""
    dt = list(rtc.datetime())
    # subsec is in µs (0-999999)
    subsec = dt[7] + offset_us
    seconds_carry = subsec // 1_000_000
    dt[7] = subsec % 1_000_000
    # carry over seconds → minutes → etc.
    secs = dt[6] + seconds_carry
    mins_carry = secs // 60
    dt[6] = secs % 60
    hrs_carry = (dt[5] + mins_carry) // 60
    dt[5] = (dt[5] + mins_carry) % 60
    # (ignore day/month/year carry for simplicity – offset is tiny)
    rtc.datetime(tuple(dt))

# ========================================
# Listen to master
# ========================================
def listener(e):
    while True:
        mac, msg = e.irecv(0)
        if mac is None:
            return
        if msg:
            # Deserialize JSON
            dict = json.loads(msg)
            # Check message type
            msg_type = dict.get("type")
            # Handle Welcom message
            if msg_type == WELCOME_MSG:
                # TODO: if state == DISCOVER change state to SYNC_WAIT
                pass
            
            # Handle Sync request message
            if msg_type == SYNC_REQ_MSG:
                T1 = unpack_sync_req(msg)
                T2 = time.ticks_us()
                e.send(MASTER_MAC, pack_sync_ack(T1, T2))
                # TODO: change state to SYNC_ACK

            
            # Handle Sync ref message
            if msg_type == SYNC_REF_MSG:
                pass


# -------------------------------------------------
# Main
# -------------------------------------------------
async def main():
    e.irq(listener)
    state = "INIT"
    if state == "INIT":
        pass
    elif state == "DISCOVER":
        e.send()


    T1 = T2 = T3 = T4 = None
    while True:
        host, msg = e.recv(100)                 # 100 ms timeout
        now = time.ticks_us()

        # ---- 1. Sync Request (T1) ----
        if state == "WAIT_SYNC" and msg and len(msg) == struct.calcsize(SYNC_REQ_FMT):
            seq, T1 = unpack_sync_req(msg)
            T2 = now
            # send ACK immediately
            e.send(MASTER_MAC, pack_ack(T1, T2))
            state = "WAIT_REF"
            print(f"SyncReq seq={seq} T1={T1} T2={T2}")

        # ---- 2. Reference (T1,T2,T3) ----
        elif state == "WAIT_REF" and msg and len(msg) == struct.calcsize(REF_FMT):
            T1_rcv, T2_rcv, T3 = unpack_ref(msg)
            if T1_rcv == T1 and T2_rcv == T2:      # sanity check
                T4 = now
                # ---- NTP calculation ----
                rtt = time.ticks_diff(T4, T1) - time.ticks_diff(T3, T2)
                offset = (time.ticks_diff(T2, T1) + time.ticks_diff(T3, T4)) // 2
                # store
                offset_us = offset
                apply_offset()
                last_sync = now
                print(f"NTP sync: offset={offset_us}µs  RTT={rtt}µs")
                state = "WAIT_SYNC"
            else:
                print("REF mismatch – discard")
                state = "WAIT_SYNC"

        # ---- watchdog – warn if no sync for a while ----
        if time.ticks_diff(now, last_sync) > SYNC_TIMEOUT:
            print("WARNING: no sync for >10 s")
            last_sync = now   # avoid spamming



# Run the async loop
asyncio.run(main())