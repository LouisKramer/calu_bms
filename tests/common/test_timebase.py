"""Time base and measurement grid test T09 (docs/protocol.md 6.3)."""

import random

from common.timebase import NET_MOD, TICKS_PERIOD, TimeBase, cycle_of, net_add, net_diff, next_grid


def test_modular_helpers():
    assert net_diff(5, NET_MOD - 5) == 10
    assert net_add(NET_MOD - 1, 2) == 1
    assert next_grid(999, 1000) == 1000
    assert next_grid(1000, 1000) == 2000
    assert next_grid(NET_MOD - 1, 1000) == 0
    assert cycle_of(123456, 1000) == 123


def test_ten_slaves_follow_the_master_through_jitter_loss_and_wraps():
    rng = random.Random(1)
    start = NET_MOD - 30_000  # network time wraps during the test
    slaves = []
    for _ in range(10):
        local0 = rng.randrange(TICKS_PERIOD - 20_000, TICKS_PERIOD)  # local ticks wrap too
        drift = rng.uniform(-20e-6, 20e-6)
        slaves.append((TimeBase(latency_ms=1), local0, drift))

    for k in range(120):  # 2 min of SYNC at 1 s
        t_true = k * 1000 + 3
        for tb, local0, drift in slaves:
            local = (local0 + round(t_true * (1 + drift))) % TICKS_PERIOD
            if rng.random() < 0.2 and tb.valid:
                continue  # SYNC lost
            sent = net_add(start, t_true - 1 + round(rng.uniform(-2, 2)))  # 1 ms latency ± 2 ms jitter
            tb.on_sync(sent, local)
        if k >= 5:
            probe = t_true + 500
            estimates = []
            for tb, local0, drift in slaves:
                local = (local0 + round(probe * (1 + drift))) % TICKS_PERIOD
                estimates.append(tb.now(local))
            truth = net_add(start, probe)
            assert all(abs(net_diff(e, truth)) <= 5 for e in estimates)
            assert len({next_grid(e, 1000) for e in estimates}) == 1  # all slaves start the same cycle
