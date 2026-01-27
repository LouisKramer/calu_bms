# logger.py
# MicroPython logger for ESP32 with file rotation, syslog support, and async handling without queues.

import uasyncio as asyncio
import os
import time
import socket
from common.credentials import WIFI_HOST
class Logger:
    _pending = []
    _lock = asyncio.Lock()
    _event = asyncio.Event()
    _file = '/logs/app.log'
    _max_size = 10240  # 10 KB default
    _max_files = 3
    _syslog_host = None
    _syslog_port = 514
    _task = None
    _levels = {'info': 6, 'warning': 4, 'error': 3}  # Syslog priorities (informational, warning, error)

    @classmethod
    def init(cls, file='/logs/app.log', max_size=10240, max_files=5, syslog_host=None, syslog_port=514):
        """
        Initialize the logger with configuration.
        - file: Path to the log file (e.g., '/logs/app.log')
        - max_size: Maximum size of the log file in bytes
        - max_files: Maximum number of rotated files to keep
        - syslog_host: IP address or hostname of the syslog server (optional)
        - syslog_port: Port for syslog (default 514)
        """
        cls._file = file
        cls._max_size = max_size
        cls._max_files = max_files
        cls._syslog_host = syslog_host
        cls._syslog_port = syslog_port
        
        # Create logs directory if it doesn't exist
        try:
            os.mkdir('/logs')
        except OSError:
            pass  # Directory already exists or error (ignore)
        
        # Start the worker task if not already running
        if not cls._task:
            cls._task = asyncio.create_task(cls._worker())

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
                timestamp = time.localtime()
                ts = "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
                    timestamp[0], timestamp[1], timestamp[2],
                    timestamp[3], timestamp[4], timestamp[5]
                )
                line = "{} {}: {}\n".format(ts, level.upper(), msg)
                
                # Print to console
                print(line, end='')
                
                # Send to syslog if configured
                if cls._syslog_host:
                    pri = cls._levels.get(level, 7)  # Default to debug if unknown
                    facility = 1  # User-level messages
                    priority = (facility * 8) + pri
                    syslog_msg = "<{}>{}: {} {}: {}".format(priority, ts, WIFI_HOST, level.upper(), msg)
                    try:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        sock.sendto(syslog_msg.encode(), (cls._syslog_host, cls._syslog_port))
                        sock.close()
                    except OSError:
                        pass  # Ignore syslog send errors
                
                # Write to file (with rotation check)
                cls._write_to_file(line)

    @classmethod
    def _write_to_file(cls, line):
        # Check file size and rotate if necessary
        try:
            size = os.stat(cls._file)[6]
        except OSError:
            size = 0
        
        if size > cls._max_size:
            cls._rotate()
        
        # Append to file
        try:
            with open(cls._file, 'a') as f:
                f.write(line)
        except OSError:
            pass  # Ignore write errors

    @classmethod
    def _rotate(cls):
        # Rotate files: app.log -> app.log.1, app.log.1 -> app.log.2, etc.
        # Delete the oldest if exceeding max_files
        for i in range(cls._max_files - 1, 0, -1):
            old = "{}.{}".format(cls._file, i)
            new = "{}.{}".format(cls._file, i + 1)
            try:
                os.remove(new)
            except OSError:
                pass
            try:
                os.rename(old, new)
            except OSError:
                pass
        
        try:
            os.rename(cls._file, "{}.1".format(cls._file))
        except OSError:
            pass

    def __init__(self):
        pass  # No instance-specific state; all shared via class

    async def _log(self, level, msg):
        async with self._lock:
            self._pending.append((level, msg))
            self._event.set()

    def info(self, msg):
        asyncio.create_task(self._log('info', msg))

    def warn(self, msg):
        asyncio.create_task(self._log('warning', msg))

    def error(self, msg):
        asyncio.create_task(self._log('error', msg))
    
    #helpers
    def mac_to_str(self,mac):
        return ':'.join('{:02x}'.format(b) for b in mac)