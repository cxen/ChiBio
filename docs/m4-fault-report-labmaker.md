# Fault report — Chi.Bio reactor unit fails I²C, wedges the shared bus

**Date:** 2026-08-12
**Reporter:** ⬜ *(name, institution)*
**Order / invoice ref:** ⬜
**Purchase date:** ⬜

---

## Unit

| | |
|---|---|
| Item | Chi.Bio reactor unit (Turbidostat V3.0), LabMaker-supplied |
| Reported version string | `Turbidostat V3.0`, LED hardware **version 2** |
| Device ID (read from the unit) | **2971060295117957796** |
| Position in our rig | slot 4 of 5 (software `M4`) |
| Controller | 5-reactor Chi.Bio controller on BeagleBone Black, Debian 10.5, Linux 4.19.94-ti-r61 |
| Software | Chi.Bio server, git `8b618792e7cd1dd80d6c11652bb51f7bd2ad4a6a` |
| Other four reactor units | working normally, verified after the fault (see below) |

---

## Summary

**One reactor unit has developed an I²C fault that pulls down the shared bus and prevents the
entire system from starting.** With this unit connected, the server cannot complete hardware
initialisation on *any* reactor. With it disconnected, all four remaining reactors initialise
and pass our full I²C self-test.

We have localised the fault to **the reactor unit itself** — not the cable, not the connector,
not the controller channel, not power. Each of those is excluded by a separate test below.

---

## Symptom

On startup the server initialises reactors in turn. It completes the first four without error,
then fails repeatedly on this unit and exits:

```
2026-08-12 11:52:32,062 ERROR MainThread Multiplexer comms failed on M4
Traceback (most recent call last):
  File "chibio_hardware.py", line 135, in I2CCom
    sysItems['Multiplexer']['device'].write8(int(0x00), int(sysItems['Multiplexer'][M], 2))
  ...
OSError: [Errno 121] Remote I/O error
2026-08-12 11:52:32,xxx ERROR MainThread Failed to recover multiplexer on M4
[ERROR] Worker (pid:951) exited with code 4
[ERROR] Shutting down: Master
[ERROR] Reason: App failed to load.
```

`Errno 121 Remote I/O error` and, on some attempts, `TimeoutError: Errno 110`. The software
attempts the documented multiplexer hard-reset (toggling the mux RESET line) and cannot recover
it. Exit code 4 is our watchdog deliberately halting rather than allowing actuators to run on a
wedged bus.

The kernel reports the bus as unusable at the same time:

```
omap_i2c 4819c000.i2c: timeout waiting for bus ready
```

**Every error names this one unit — 40 of 40 in each attempt, no other reactor ever appears.**

---

## Localisation

One variable changed per test. The system was fully powered down for each physical change.

| # | Configuration | Result | Excludes |
|---|---|---|---|
| 1 | Unit in its own port, as normal | 40 errors, all naming it; no boot | — |
| 2 | Connector reseated firmly, both ends | identical failure | connector seating |
| 3 | **Its cable swapped for a known-good cable** (the matching pump cable) | identical failure | **the cable** |
| 4 | Complete power-down, 10 s, power restored | identical failure | latch-up / power state |
| 5 | Fresh OS reboot before each attempt | identical failure | software/host state |
| 6 | **Unit disconnected entirely** | **clean boot**; remaining four detected; **I²C self-test 16 passed / 0 failed** | the rest of the rig |
| 7 | **Unit moved to a different controller port (position 7)** | **identical failure, now reported against position 7** | **the controller channel** |

**Test 7 is decisive:** the fault moved with the unit to a different controller port. Ports 4
and 7 both behave correctly with other hardware. Therefore the fault is inside the reactor unit.

---

## Prior warning signs

This unit had shown intermittent faults for about four hours before failing outright, during an
otherwise normal 13-hour batch culture run:

- `Failed transmission test on PWM 1 times consecutively on device M4` and
  `... 2 times consecutively ...` (2026-08-11 22:22:28), the only reactor to produce these
- repeated `Spectrometer measurement was saturated on device M4` warnings
- the highest fluorescence-channel invalid-read rate of the five units

The hard failure appeared shortly after routine physical handling (removing and replacing sample
vials). No liquid ingress, damage, or contamination is visible on the unit, its connector or its
cable.

---

## Current state

- The unit is **disconnected and labelled faulty**; it has not been used since.
- The remaining four reactors run normally — presence scan clean, **I²C self-test 16/16**.
- The rig is operating as a four-reactor system.

---

## What we are asking

⬜ *Choose one and delete the rest:*

- Repair or replacement of the reactor unit under warranty
- Diagnosis guidance, if there is a known failure mode for this symptom on V3.0 units
- Whether this is a known issue with the AS7341 board, the PWM driver, or the I²C level
  shifting on this revision — we would rather understand the root cause than swap blind

**Question we would particularly like answered:** is there a protection or isolation option on
these units so that a single failing reactor cannot pull down the shared I²C bus and disable an
entire rig? Losing all five reactors to one unit's fault is a significant operational risk for
long unattended culture runs.

We can supply full server logs, the self-test JSON snapshots (before and after), and the 13-hour
run dataset on request.

---

*Prepared from logs and tests recorded in `labnotes.md` (entry: 2026-08-12 — M4 reactor unit
failed) in our fork of the Chi.Bio software.*
