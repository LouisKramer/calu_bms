"""Network time of the master–slave system and the measurement grid (docs/protocol.md 6.3).

Network time: u32 milliseconds of the master, wraps after 49.7 days. Local time: `time.ticks_ms()`, which wraps
with the MicroPython ticks period (2**30 on the ESP32). All arithmetic is modular.
"""

NET_MOD = 1 << 32
TICKS_PERIOD = 1 << 30


def net_diff(a, b):
    """a − b for network times, as signed ms."""
    return ((a - b + (NET_MOD >> 1)) % NET_MOD) - (NET_MOD >> 1)


def net_add(t, delta):
    return (t + delta) % NET_MOD


def ticks_diff(a, b, period=TICKS_PERIOD):
    return ((a - b + (period >> 1)) % period) - (period >> 1)


def cycle_of(t, period):
    """Measurement cycle number of network time t."""
    return t // period


def next_grid(t, period):
    """First grid point (multiple of period) after network time t; at the 2**32 wrap the grid restarts at 0."""
    g = (t // period + 1) * period
    return g if g < NET_MOD else 0


class TimeBase:
    """Slave estimate of the network time, corrected at every SYNC with the median of recent deviations."""

    def __init__(self, latency_ms=1, depth=5, ticks_period=TICKS_PERIOD):
        self.latency = latency_ms
        self.depth = depth
        self.period = ticks_period
        self._ref_net = None
        self._ref_local = 0
        self._dev = []

    @property
    def valid(self):
        return self._ref_net is not None

    def now(self, local_ms):
        return net_add(self._ref_net, ticks_diff(local_ms, self._ref_local, self.period))

    def on_sync(self, net_time, local_ms):
        """Update with a received SYNC; returns the deviation of the estimate before the update (SWS-024)."""
        target = net_add(net_time, self.latency)
        if self._ref_net is None:
            self._ref_net, self._ref_local = target, local_ms
            return 0
        current = self.now(local_ms)
        dev = net_diff(target, current)
        self._dev.append(dev)
        if len(self._dev) > self.depth:
            self._dev.pop(0)
        corr = sorted(self._dev)[len(self._dev) // 2]
        self._dev = [d - corr for d in self._dev]
        self._ref_net, self._ref_local = net_add(current, corr), local_ms
        return dev

    def reset(self):
        self._ref_net = None
        self._dev = []
