# logger.py
# MicroPython logger for ESP32 with file rotation, syslog support, and async handling.
# ✅ Print to console happens IMMEDIATELY when info/warn/error is called.
# File + syslog remain fully asynchronous (non-blocking).

import uasyncio as asyncio
import os
import time
import socket
from common.credentials import WIFI_HOST


class Logger:
    _pending = []           # (level, msg) tuples
    _lock = asyncio.Lock()
    _event = asyncio.Event()
    _file = '/logs/app.log'
    _max_size = 10240       # 10 KB default
    _max_files = 3
    _syslog_host = None
    _syslog_port = 514
    _task = None
    _levels = {'info': 6, 'warning': 4, 'error': 3}

    @classmethod
    def init(cls, file='/logs/app.log', max_size=10240, max_files=5,
             syslog_host=None, syslog_port=514):
        cls._file = file
        cls._max_size = max_size
        cls._max_files = max_files
        cls._syslog_host = syslog_host
        cls._syslog_port = syslog_port

        try:
            os.mkdir('/logs')
        except OSError:
            pass

        if not cls._task:
            cls._task = asyncio.create_task(cls._worker())

    @staticmethod
    def _format_line(level: str, msg: str) -> str:
        """Format timestamp + level + message (used for immediate print)"""
        timestamp = time.localtime()
        ts = "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
            timestamp[0], timestamp[1], timestamp[2],
            timestamp[3], timestamp[4], timestamp[5]
        )
        return f"{ts} {level.upper()}: {msg}\n"

    @classmethod
    async def _worker(cls):
        while True:
            await cls._event.wait()
            cls._event.clear()

            async with cls._lock:
                logs = cls._pending
                cls._pending = []

            if not logs:
                continue

            for level, msg in logs:
                # Build the exact same line for file/syslog
                line = cls._format_line(level, msg)

                # Send to syslog if configured
                if cls._syslog_host:
                    pri = cls._levels.get(level, 7)
                    facility = 1
                    priority = (facility * 8) + pri
                    syslog_msg = f"<{priority}>{line.strip()}"   # syslog format
                    try:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        sock.sendto(syslog_msg.encode(), (cls._syslog_host, cls._syslog_port))
                        sock.close()
                    except OSError:
                        pass  # ignore network hiccups

                # Write to file with rotation
                cls._write_to_file(line)

    @classmethod
    def _write_to_file(cls, line):
        try:
            size = os.stat(cls._file)[6]
        except OSError:
            size = 0

        if size > cls._max_size:
            cls._rotate()

        try:
            with open(cls._file, 'a') as f:
                f.write(line)
        except OSError:
            pass

    @classmethod
    def _rotate(cls):
        for i in range(cls._max_files - 1, 0, -1):
            old = f"{cls._file}.{i}"
            new = f"{cls._file}.{i + 1}"
            try:
                os.remove(new)
            except OSError:
                pass
            try:
                os.rename(old, new)
            except OSError:
                pass
        try:
            os.rename(cls._file, f"{cls._file}.1")
        except OSError:
            pass

    # ====================== PUBLIC API ======================
    def _print_now(self, level: str, msg: str):
        """Print to console IMMEDIATELY (synchronous)"""
        line = self._format_line(level, msg)
        print(line, end='')

    async def _log(self, level: str, msg: str):
        """Queue for background file + syslog only"""
        async with self._lock:
            self._pending.append((level, msg))
            self._event.set()

    def info(self, msg):
        self._print_now('info', msg)          # ← immediate print
        asyncio.create_task(self._log('info', msg))

    def warn(self, msg):
        self._print_now('warning', msg)       # ← immediate print
        asyncio.create_task(self._log('warning', msg))

    def error(self, msg):
        self._print_now('error', msg)         # ← immediate print
        asyncio.create_task(self._log('error', msg))

    # helper
    def mac_to_str(self, mac):
        return ':'.join('{:02x}'.format(b) for b in mac)