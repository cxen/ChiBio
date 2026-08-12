# Email draft — M4 reactor fault, to LabMaker

**To:** ⬜ (LabMaker support)
**Subject:** Faulty Chi.Bio reactor unit (Turbidostat V3.0, ID 2971060295117957796) — pulls down shared I²C bus, disables whole rig

---

Dear LabMaker team,

We have a five-reactor Chi.Bio system and one of the reactor units has developed an I²C fault
that disables the entire rig. I would like to arrange a repair or replacement, and if possible
understand the failure mode.

**Unit:** Chi.Bio reactor, Turbidostat V3.0, LED hardware version 2, device ID
**2971060295117957796**. Purchased ⬜ (date), order/invoice ⬜.

**Symptom.** With this unit connected, the server cannot complete hardware initialisation. It
initialises the other four reactors normally, then fails repeatedly on this one with
`OSError: [Errno 121] Remote I/O error` on the multiplexer, cannot recover the multiplexer via
the reset line, and exits. The kernel reports `omap_i2c: timeout waiting for bus ready` at the
same moment. Every error names this one unit — 40 out of 40 in each attempt, with no other
reactor ever appearing.

**With the unit disconnected, everything else works**: the remaining four reactors are detected
and pass our full I²C self-test, 16 checks, 0 failures.

**We have localised the fault to the reactor unit itself.** Changing one variable at a time, with
the system fully powered down for each change:

- reseating the connector at both ends — identical failure, so not connector seating
- swapping its cable for a known-good one — identical failure, so not the cable
- a complete 10-second power-down — identical failure, so not a latch-up
- disconnecting the unit — clean boot, four reactors, self-test 16/16
- **moving the unit to a different controller port — identical failure, now reported against that
  new port**

The last test is the decisive one: the fault travels with the unit, and both controller ports
work correctly with other hardware.

**Prior warning signs.** The unit showed intermittent faults for roughly four hours before
failing outright, during an otherwise normal 13-hour culture run: repeated
`Failed transmission test on PWM ... on device M4` messages (this unit only), repeated
spectrometer saturation warnings, and the highest invalid-read rate of the five units. The hard
failure appeared shortly after routine handling of sample vials. There is no visible damage,
liquid ingress or contamination on the unit, its connector or its cable.

**What we are asking:**

1. Repair or replacement of the unit ⬜ *(under warranty, if applicable)*.
2. If you recognise this symptom on V3.0 units, any guidance on the root cause — we would rather
   understand it than swap blind. Is this a known failure of the AS7341 board, the PWM driver, or
   the I²C level shifting on this revision?
3. A question about design: **is there any isolation option so that a single failing reactor
   cannot pull down the shared I²C bus and disable an entire rig?** Losing all five reactors to
   one unit's fault is a significant operational risk for long unattended culture runs, and we
   would like to know whether it can be mitigated.

I can supply the full server logs, the self-test JSON snapshots from before and after the fault,
and the 13-hour run dataset — just say what would be useful.

Many thanks,

⬜ *(name)*
⬜ *(institution, address)*
⬜ *(phone, if useful for shipping arrangements)*
