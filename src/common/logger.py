# logger.py
import time
import ujson as json
import os
import usocket as socket
from micropython import const
from machine import RTC, reset

# ----------------------------------------------------------------------
#  Log levels
# ----------------------------------------------------------------------
class LogLevel:
    INFO     = const(0)   # 6
    WARN     = const(1)   # 4
    ERROR    = const(2)   # 3
    CRITICAL = const(3)   # 2

    _NAMES = {INFO: "INFO", WARN: "WARN", ERROR: "ERROR", CRITICAL: "CRITICAL"}
    _PREFIX = {INFO: "[I]", WARN: "[W]", ERROR: "[E]", CRITICAL: "[C]"}
    _SYSLOG_SEV = {INFO: 6, WARN: 4, ERROR: 3, CRITICAL: 2}

    @staticmethod
    def name(level: int) -> str:
        return LogLevel._NAMES.get(level, "???")

    @staticmethod
    def prefix(level: int) -> str:
        return LogLevel._PREFIX.get(level, "[?]")

    @staticmethod
    def syslog_severity(level: int) -> int:
        return LogLevel._SYSLOG_SEV.get(level, 5)


# ----------------------------------------------------------------------
#  Logger class
# ----------------------------------------------------------------------
class Logger:
    def __init__(
        self,
        name: str = "main",
        level: int = LogLevel.INFO,
        max_buffer: int = 30,
        flash_path: str | None = None,
        max_file_size: int = 10 * 1024,
        max_files: int = 5,
        rotate_on_boot: bool = True,
        syslog_host: str | None = None,
        syslog_port: int = 514,
        hostname: str = "bms-node",
        app_name: str | None = None
    ):
        self.name = name
        self.level = level
        self.max_buffer = max_buffer
        self.flash_path = flash_path
        self.max_file_size = max_file_size
        self.max_files = max_files
        self._buffer: list[dict] = []

        self.syslog_host = syslog_host
        self.syslog_port = syslog_port
        self.hostname = hostname
        self.app_name = app_name or name

        self._syslog_sock = None

        if flash_path and rotate_on_boot:
            self._rotate_if_needed()

    # ------------------------------------------------------------------
    #  RTC Timestamp (ISO 8601)
    # ------------------------------------------------------------------
    def _iso_timestamp(self) -> str:
        try:
            tm = RTC().rtc.datetime()
            # tm = (year, month, day, weekday, hour, minute, second, subsecond)
            return f"{tm[0]:04d}-{tm[1]:02d}-{tm[2]:02d}T{tm[4]:02d}:{tm[5]:02d}:{tm[6]:02d}.{time.ticks_ms()%1000:03d}Z"
        except:
            # Fallback: uptime
            secs = time.ticks_ms() // 1000
            ms = time.ticks_ms() % 1000
            return f"1970-01-01T00:00:{secs:05d}.{ms:03d}Z"

    # ------------------------------------------------------------------
    #  Core logging
    # ------------------------------------------------------------------
    def _log(self, level: int, msg: str, ctx: str = "main"):
        if level < self.level:
            return

        try:
            entry = {
                "t": self._iso_timestamp(),
                "lvl": level,
                "ctx": f"{self.name}.{ctx}"[:32],
                "msg": str(msg)[:120]
            }
            self._buffer.append(entry)
            if len(self._buffer) > self.max_buffer:
                self._buffer.pop(0)

            # Console
            print(f"{LogLevel.prefix(level)} {entry['ctx']:>20} | {entry['msg']}")

            # Flash
            if self.flash_path:
                self._write_to_flash(entry)

            # Syslog
            if self.syslog_host:
                self._send_syslog(entry)

        except Exception as e:
            print(f"[LOGFAIL] {LogLevel.name(level)} {ctx} | {e}")

    # ------------------------------------------------------------------
    #  Syslog
    # ------------------------------------------------------------------
    def _get_syslog_socket(self):
        if not self.syslog_host:
            return None
        if self._syslog_sock is None:
            try:
                self._syslog_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self._syslog_sock.setblocking(False)
            except:
                self._syslog_sock = None
        return self._syslog_sock

    def _send_syslog(self, entry: dict):
        sock = self._get_syslog_socket()
        if not sock:
            return
        try:
            pri = 13 * 8 + LogLevel.syslog_severity(entry["lvl"])
            structured = f'[meta@12345 ctx="{entry["ctx"]}"]'
            msg = f"<{pri}>1 {entry['t']} {self.hostname} {self.app_name} - - {structured} {entry['msg']}"
            sock.sendto(msg.encode('utf-8'), (self.syslog_host, self.syslog_port))
        except:
            if self._syslog_sock:
                try: self._syslog_sock.close()
                except: pass
                self._syslog_sock = None

    # ------------------------------------------------------------------
    #  Flash rotation
    # ------------------------------------------------------------------
    def _write_to_flash(self, entry: dict):
        try:
            path = self.flash_path
            if not path.endswith(".txt"):
                path = path.rstrip("/") + ".txt"

            if self._file_needs_rotation(path):
                self._rotate_files(path)

            line = f"{entry['t']},{LogLevel.name(entry['lvl'])},{entry['ctx']},{entry['msg']}\n"
            with open(path, "a") as f:
                f.write(line)
        except Exception as e:
            print(f"[LOGROT] {e}")

    def _file_needs_rotation(self, path: str) -> bool:
        try:
            return os.stat(path)[6] >= self.max_file_size
        except OSError:
            return False

    def _rotate_files(self, base_path: str):
        try:
            oldest = f"{base_path}.{self.max_files - 1}.txt"
            try: os.remove(oldest)
            except: pass
            for i in range(self.max_files - 2, -1, -1):
                src = f"{base_path}.{i}.txt" if i > 0 else base_path
                dst = f"{base_path}.{i + 1}.txt"
                try: os.rename(src, dst)
                except: pass
            try: os.rename(base_path, f"{base_path}.0.txt")
            except: pass
        except Exception as e:
            print(f"[LOGROT] rotate failed: {e}")

    def _rotate_if_needed(self):
        try:
            if self.flash_path and os.stat(self.flash_path)[6] > 0:
                self._rotate_files(self.flash_path)
        except: pass

    # ------------------------------------------------------------------
    #  Public API
    # ------------------------------------------------------------------
    def info(self, msg: str, ctx: str = "main"):
        self._log(LogLevel.INFO, msg, ctx)

    def warn(self, msg: str, ctx: str = "main"):
        self._log(LogLevel.WARN, msg, ctx)

    def error(self, e: Exception | str, ctx: str = "main"):
        msg = f"{e.__class__.__name__}: {e}" if isinstance(e, Exception) else str(e)
        self._log(LogLevel.ERROR, msg, ctx)

    def critical(self, msg: str, ctx: str = "main", reset: bool = True):
        self._log(LogLevel.CRITICAL, msg, ctx)
        if reset:
            print("[FATAL] Reset in 3s...")
            time.sleep(3)
            reset()

    # ------------------------------------------------------------------
    #  Utils
    # ------------------------------------------------------------------
    def get_buffer(self): return self._buffer[:]
    def clear(self): self._buffer.clear()
    def set_level(self, level: int): self.level = level
    def summary(self):
        counts = {LogLevel.INFO: 0, LogLevel.WARN: 0, LogLevel.ERROR: 0, LogLevel.CRITICAL: 0}
        for e in self._buffer:
            counts[e["lvl"]] += 1
        return {"total": len(self._buffer), "counts": {LogLevel.name(k): v for k, v in counts.items()}}


# ----------------------------------------------------------------------
#  Factory Function
# ----------------------------------------------------------------------
def create_logger(
    name: str,
    level=LogLevel.INFO,
    flash: bool = True,
    syslog: bool = True,
    max_buffer: int = 30,
    host: str = "192.168.1.100"
) -> Logger:
    """
    Create a logger with sensible defaults.

    Args:
        name: Logger name (used in ctx and app_name)
        level: LogLevel.INFO / WARN / etc.
        flash: Save to flash with rotation?
        syslog: Send to remote syslog?
        max_buffer: In-memory entries

    Returns:
        Configured Logger instance
    """
    flash_path = f"/log_{name}.txt" if flash else None
    syslog_host = host if syslog else None

    return Logger(
        name=name,
        level=level,
        max_buffer=max_buffer,
        flash_path=flash_path,
        max_file_size=8 * 1024,
        max_files=3,
        syslog_host=syslog_host,
        hostname="bms-01",
        app_name=f"BMS-{name.capitalize()}"
    )