"""Off-device tests for pump duty-cycle timing and I2C traffic.

Run: CHIBIO_MOCK_HW=1 python3 test_pump_timing.py

Pump on-time sets the delivered volume, which sets the dilution rate, which is what
turbidostat growth rates are computed from -- so a systematic bias here is a quantitative
error in the science, not a cosmetic one.
"""
import os
import threading
import time

os.environ.setdefault('CHIBIO_MOCK_HW', '1')

import chibio_experiment
from chibio_experiment import _wait_pump_ontime
from chibio_state import sysData, sysDevices


def _worst_error(wait, requested, reps=5):
    errors = []
    for _ in range(reps):
        t0 = time.perf_counter()
        wait(requested)
        errors.append(time.perf_counter() - t0 - requested)
    errors.sort()
    return errors[-1], errors[0], errors[len(errors) // 2]


def test_ontime_never_undershoots():
    # A dose must never be SHORTER than asked -- that would under-dilute silently. Overshoot is
    # bounded by the scheduler, not by us (see _wait_pump_ontime), and is recorded per cycle
    # rather than assumed away.
    # No upper bound is asserted: overshoot here is the OS scheduler's, not this code's, and
    # it varies with machine load. Bounding it would test the scheduler and flake. The
    # achieved on-time is logged per cycle (pump_N_ontime_ms) precisely so the real figure is
    # measured on the device rather than assumed by a test.
    for requested in (0.02, 0.05, 0.1, 0.25):
        _, best, _ = _worst_error(_wait_pump_ontime, requested)
        assert best > -0.002, 'on-time %.3fs undershot by %.4fs' % (requested, best)
    print('PASS pump on-times never undershoot the request')


def test_no_busy_wait_regression():
    # Guard against "fixing" this with a spin-wait again. Measured on the BeagleBone under
    # 4-thread load: spin-wait 10-35 ms error vs time.sleep 5-14 ms -- a spinning thread holds
    # the GIL and gets descheduled on a single core. A wait that burns CPU is the regression.
    # Measured, not string-matched: a busy-wait pegs the CPU for the duration, a sleep does not.
    t0 = time.perf_counter()
    c0 = time.process_time()
    _wait_pump_ontime(0.3)
    wall = time.perf_counter() - t0
    cpu = time.process_time() - c0
    assert cpu < wall * 0.5, 'pump wait burned %.3fs CPU over %.3fs wall - busy-waiting' % (cpu, wall)
    print('PASS pump wait sleeps rather than burning CPU (%.0f%% CPU)' % (100 * cpu / wall))


def test_zero_ontime_returns_immediately():
    t0 = time.perf_counter()
    _wait_pump_ontime(0)
    _wait_pump_ontime(-1)
    assert time.perf_counter() - t0 < 0.01
    print('PASS a zero/negative on-time returns immediately')


def test_no_duplicate_off_pairs():
    # Each redundant setPWM takes the global bus lock and switches the multiplexer. The
    # duplicated pairs cost 4 extra transactions per pump per cycle, on exactly the resource
    # whose contention produces "Failed to recover multiplexer".
    calls = []
    original = chibio_experiment.setPWM

    def recorder(M, device, channel, value, offset):
        calls.append((channel.get('ONL'), round(float(value), 3)))

    M = 'M0'
    try:
        chibio_experiment.setPWM = recorder
        sysData[M]['Experiment']['cycleTime'] = 1.0
        sysData[M]['Pump1']['ON'] = 1
        sysData[M]['Pump1']['target'] = 0.05      # 52.5 ms on, then off
        sysDevices[M]['Pump1']['threadCount'] = 0
        sysDevices[M]['Pump1']['active'] = 0
        sysDevices[M]['Pump1']['running'] = 1

        t = threading.Thread(target=chibio_experiment.PumpModulation, args=(M, 'Pump1'))
        t.daemon = True
        t.start()
        time.sleep(0.4)                            # let one duty cycle complete
        sysData[M]['Pump1']['ON'] = 0
        t.join(timeout=5.0)
        assert not t.is_alive(), 'PumpModulation did not exit'
    finally:
        chibio_experiment.setPWM = original
        sysData[M]['Pump1']['ON'] = 0
        sysData[M]['Pump1']['target'] = 0.0

    # One duty cycle: an initial off-pair, an on-pair, a closing off-pair = 6 writes.
    # The duplicated version issued 10 for the same work.
    duty = calls[:6]
    assert len(calls) >= 6, calls
    assert len(duty) == 6, duty
    # No off-pair may appear twice in a row -- that was the exact duplication.
    for i in range(len(duty) - 3):
        window = duty[i:i + 4]
        assert not (window[0] == window[2] and window[1] == window[3] and
                    window[0][1] == 0.0 and window[1][1] == 0.0), \
            'duplicate off-pair still present: %r' % (window,)
    # The achieved on-time must be RECORDED and never shorter than requested. No upper bound:
    # overshoot is the scheduler's and varies with load -- recording it is the point, so that
    # the real dose is a measured number rather than an assumed one.
    achieved = sysData[M]['Pump1'].get('lastOntimeMs', 0.0)
    assert achieved >= 52.0, 'achieved on-time %.1f ms is shorter than the 52.5 ms asked' % achieved
    print('PASS one duty cycle issues 6 setPWM writes (was 10) and records its on-time')


if __name__ == '__main__':
    test_ontime_never_undershoots()
    test_no_busy_wait_regression()
    test_zero_ontime_returns_immediately()
    test_no_duplicate_off_pairs()
    print('\nAll pump timing tests passed.')
