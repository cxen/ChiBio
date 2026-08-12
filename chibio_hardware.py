import os
import sys
import time
import logging
import threading
import traceback
from contextlib import contextmanager
from datetime import datetime
from threading import Thread

# Adafruit_BBIO is a kernel-matched C extension that only builds/imports on the
# BeagleBone. Setting CHIBIO_MOCK_HW (or CHIBIO_SIM, which implies it) swaps in a
# no-op GPIO so `import app` works on a dev laptop for smoke tests. Gate on the env
# var, NOT on ImportError: the device must fail loudly if the real GPIO (and its
# watchdog) is missing, never silently run on a mock. This is a no-op mock, not a
# simulator — CHIBIO_SIM and chibio_sim.py are the simulator.
from chibio_sim import MOCK_HW  # stdlib-only at import time, so no cycle

if MOCK_HW:
    class _MockGPIO:
        OUT = IN = 0
        HIGH = 1
        LOW = 0
        def setup(self, *a, **k): pass
        def output(self, *a, **k): pass
    GPIO = _MockGPIO()
else:
    import Adafruit_BBIO.GPIO as GPIO
import smbus2

from chibio_state import lock, sysData, sysDevices, sysItems

logger = logging.getLogger('chibio')

# One SMBus handle per bus number, shared across all devices on that bus (the
# global `lock` already serializes access). Mirrors how Adafruit_GPIO cached one
# bus per busnum.
_i2c_buses = {}


def _get_bus(busnum):
    bus = _i2c_buses.get(busnum)
    if bus is None:
        bus = smbus2.SMBus(busnum)
        _i2c_buses[busnum] = bus
    return bus


# A single I2CCom is bounded (~1.5 s worst case, then os._exit), so any wait past this is
# queueing behind other threads, not one slow transaction. threading.Lock is not fair, so a
# waiter can be starved under sustained contention -- the leading remaining hypothesis for the
# 2026-08-12 09:30:52 worker timeout, whose two documented suspects were both refuted (see
# TODO.md). Logging the wait is what makes the next occurrence diagnosable instead of a mystery.
_SLOW_LOCK_SECONDS = 10.0
_STALL_REPORT_SECONDS = 30.0


@contextmanager
def measurement_sequence(M):
    """Hold a reactor's measurement mutex across a whole drive-output -> read -> turn-off
    sequence.

    `lock` (in I2CCom) serializes single I2C transactions, which is not enough: two threads
    working the SAME reactor interleave at the sequence level, so a FluorescenceScan can
    switch the laser off between an experiment cycle's switch-on and its read. The read then
    succeeds against a dark sample -- raw=0, od_spread ~1.1, and `valid` stays 1 because
    nothing failed. That is the unflagged corrupt row in INVARIANTS 5, and the same collision
    killed M3's experiment thread on 2026-08-11.

    The guard is an RLock, so nesting (a cycle's measure_od inside the cycle's own guard) is
    safe without any per-thread bookkeeping, and it stays correct if a thread ever needs to
    hold two reactors at once. Absent from `sysDevices` only in the mock-import path, where
    this degrades to a no-op.
    """
    M = str(M)
    guard = sysDevices.get(M, {}).get('measureLock')
    if guard is None:
        yield
        return
    waited = time.monotonic()
    guard.acquire()
    waited = time.monotonic() - waited
    if waited > _SLOW_LOCK_SECONDS:
        logger.warning('measurement mutex on %s waited %.1fs (contended)', M, waited)
    try:
        yield
    finally:
        guard.release()


def _stall_watchdog():
    """Report, with every thread's stack, whenever this thread loses the CPU for too long.

    Gunicorn's sync worker dies if it cannot touch its heartbeat within --timeout (300 s).
    Two suspects for the unexplained 2026-08-12 09:30:52 kill were measured and cleared on
    the device: sysData does not grow (downsample bounds every record at 200) and five
    concurrent config dumps starve a heartbeat by at most 170 ms, ~1800x under the limit.
    Whatever the real cause is, it stalls this loop too -- so capture the evidence in the act
    rather than reasoning backwards from a vanished log.
    """
    last = time.time()
    while True:
        time.sleep(1.0)
        now = time.time()
        gap = now - last
        last = now
        if gap < _STALL_REPORT_SECONDS:
            continue
        logger.error('STALL: watchdog thread lost the CPU for %.1fs (gunicorn --timeout is 300s)', gap)
        frames = sys._current_frames()
        for thread in threading.enumerate():
            stack = frames.get(thread.ident)
            if stack is None:
                continue
            logger.error('STALL: thread %s (%s)\n%s', thread.name, thread.ident,
                         ''.join(traceback.format_stack(stack)))
        try:  # cheap and often decisive: an SD-card write stall shows up as high load, not CPU
            with open('/proc/loadavg') as fh:
                logger.error('STALL: loadavg %s', fh.read().strip())
        except IOError:
            pass


def start_stall_watchdog():
    watcher = Thread(target=_stall_watchdog)
    watcher.setDaemon(True)
    watcher.start()
    return watcher


class _I2CDevice:
    """Drop-in replacement for Adafruit_GPIO.I2C.Device over smbus2, exposing only
    the methods ChiBio actually calls. Behaviour is byte-identical to Adafruit_GPIO
    on purpose — every method maps to the same underlying SMBus call it used, so
    readings must not change. In particular readU16's second arg is `little_endian`
    (NOT a register): the code relies on little_endian=False to byte-swap the
    big-endian MCP9808 thermometers, so this must be preserved exactly.
    """

    def __init__(self, address, busnum):
        self._addr = address
        self._bus = _get_bus(busnum)

    def write8(self, register, value):
        self._bus.write_byte_data(self._addr, register, value & 0xFF)

    def write16(self, register, value):
        self._bus.write_word_data(self._addr, register, value & 0xFFFF)

    def readU8(self, register):
        return self._bus.read_byte_data(self._addr, register) & 0xFF

    def readU16(self, register, little_endian=True):
        result = self._bus.read_word_data(self._addr, register) & 0xFFFF
        if not little_endian:
            result = ((result << 8) & 0xFF00) + (result >> 8)
        return result

    def readRaw8(self):
        return self._bus.read_byte(self._addr) & 0xFF


def get_i2c_device(address, busnum):
    # Signature-compatible with Adafruit_GPIO.I2C.get_i2c_device so call sites are
    # unchanged apart from dropping the `I2C.` prefix.
    return _I2CDevice(address, busnum)


def runWatchdog():
    # Watchdog timing function which continually runs in a thread.
    while (sysItems['Watchdog']['ON'] == 1):
        toggleWatchdog()
        time.sleep(0.15)


def toggleWatchdog():
    # Toggle the watchdog
    GPIO.output(sysItems['Watchdog']['pin'], GPIO.HIGH)
    time.sleep(0.05)
    GPIO.output(sysItems['Watchdog']['pin'], GPIO.LOW)


def setup_watchdog():
    GPIO.setup(sysItems['Watchdog']['pin'], GPIO.OUT)
    print(str(datetime.now()) + ' Starting watchdog')
    sysItems['Watchdog']['thread'] = Thread(target=runWatchdog, args=())
    sysItems['Watchdog']['thread'].setDaemon(True)
    sysItems['Watchdog']['thread'].start()
    GPIO.setup('P8_15', GPIO.OUT) #This output connects to the RESET pin on the I2C Multiplexer.
    GPIO.output('P8_15', GPIO.HIGH)
    GPIO.setup('P8_17', GPIO.OUT) #This output connects to D input of the D-Latch
    GPIO.output('P8_17', GPIO.HIGH)


def I2CCom(M, device, rw, hl, data1, data2, SMBUSFLAG):
    # Function used to manage I2C bus communications for ALL devices.
    M = str(M) #Turbidostat to write to
    device = str(device) #Name of device to be written to
    rw = int(rw) #1 if read, 0 if write
    hl = int(hl) #8 or 16
    SMBUSFLAG = int(SMBUSFLAG) # If this flag is set to 1 it means we are communuicating with an SMBUs device.
    data1 = int(data1) #First data/register
    if hl < 20:
        data2 = int(data2) #First data/register

    if(sysData[M]['present'] == 0): #Something stupid has happened in software if this is the case!
        print(str(datetime.now()) + ' Trying to communicate with absent device - bug in software!. Disabling hardware and software!')
        sysItems['Watchdog']['ON'] = 0 #Basically this will crash all the electronics and the software.
        out = 0
        tries = -1
        os._exit(4)

    #cID=str(M)+str(device)+'d'+str(data1)+'d'+str(data2)  # This is an ID string for the communication that we are trying to send - not used at present
    #Any time a thread gets to this point it will wait until the lock is free. Then, only one thread at a time will advance.
    #Timed so a starved waiter leaves a trace: one I2CCom is bounded, so a long wait here means
    #queueing behind other threads. threading.Lock is unfair, so sustained contention can starve
    #a waiter indefinitely -- a candidate for the unexplained worker timeout (see TODO.md).
    _waitStart = time.monotonic()
    lock.acquire()
    _waited = time.monotonic() - _waitStart
    if _waited > _SLOW_LOCK_SECONDS:
        logger.warning('I2C bus lock wait %.1fs for %s on %s (contended)', _waited, device, M)
    try:
        #We now connect the multiplexer to the appropriate device to allow digital communications.
        tries = 0
        while(tries != -1):
            try:
                sysItems['Multiplexer']['device'].write8(int(0x00), int(sysItems['Multiplexer'][M], 2)) #We have established connection to correct device.
                check = (sysItems['Multiplexer']['device'].readRaw8()) #We check that the Multiplexer is indeed connected to the correct channel.
                if(check == int(sysItems['Multiplexer'][M], 2)):
                    tries = -1
                else:
                    tries = tries + 1
                    time.sleep(0.02)
                    print(str(datetime.now()) + ' Multiplexer didnt switch ' + str(tries) + " times on " + str(M))
            except Exception: #If there is an error in the above.
                tries = tries + 1
                time.sleep(0.02)
                print(str(datetime.now()) + ' Failed Multiplexer Comms ' + str(tries) + " times")
                logger.exception('Multiplexer comms failed on %s', M)
                if (tries > 2):
                    try:
                        sysItems['Multiplexer']['device'].write8(int(0x00), int(0x00)) #Disconnect multiplexer.
                        print(str(datetime.now()) + 'Disconnected multiplexer on ' + str(M) + ', trying to connect again.')
                    except Exception:
                        print(str(datetime.now()) + 'Failed to recover multiplexer on device ' + str(M))
                        logger.exception('Failed to recover multiplexer on %s', M)
                if (tries == 5 or tries == 10 or tries == 15):
                    toggleWatchdog()  #Flip the watchdog pin to ensure it is working.
                    GPIO.output('P8_15', GPIO.LOW) #Flip the Multiplexer RESET pin. Note this reset function works on Control Board V1.2 and later.
                    time.sleep(0.1)
                    GPIO.output('P8_15', GPIO.HIGH)
                    time.sleep(0.1)
                    print(str(datetime.now()) + 'Did multiplexer hard-reset on ' + str(M))

            if tries > 20: #If it has failed a number of times then likely something is seriously wrong, so we crash the software.
                sysItems['Watchdog']['ON'] = 0 #Basically this will crash all the electronics and the software.
                out = 0
                print(str(datetime.now()) + 'Failed to communicate to Multiplexer 20 times. Disabling hardware and software!')
                tries = -1
                os._exit(4)

        time.sleep(0.0005)
        out = 0
        tries = 0

        while(tries != -1): #We now do appropriate read/write on the bus.
            try:
                if SMBUSFLAG == 0:
                    if rw == 1:
                        if hl == 8:
                            out = int(sysDevices[M][device]['device'].readU8(data1))
                        elif(hl == 16):
                            out = int(sysDevices[M][device]['device'].readU16(data1, data2))
                    else:
                        if hl == 8:
                            sysDevices[M][device]['device'].write8(data1, data2)
                            out = 1
                        elif(hl == 16):
                            sysDevices[M][device]['device'].write16(data1, data2)
                            out = 1

                elif SMBUSFLAG == 1:
                    out = sysDevices[M][device]['device'].read_word_data(sysDevices[M][device]['address'], data1)
                tries = -1
            except Exception: #If the above fails then we can try again (a limited number of times)
                tries = tries + 1

                if (device != "ThermometerInternal"):
                    print(str(datetime.now()) + ' Failed ' + str(device) + ' comms ' + str(tries) + " times on device " + str(M) )
                    logger.exception('I2CCom failed for %s on %s', device, M)
                    time.sleep(0.02)
                if (device == 'AS7341'):
                    print(str(datetime.now()) + ' Failed  AS7341 in I2CCom while trying to send ' + str(data1)  + " and " + str(data2))
                    out = -1
                    tries = -1

            if (tries > 2 and device == "ThermometerInternal"): #We don't allow the internal thermometer to fail, since this is what we are using to see if devices are plugged in at all.
                out = 0
                sysData[M]['present'] = 0
                tries = -1
            if tries > 10: #In this case something else has gone wrong, so we panic.
                sysItems['Watchdog']['ON'] = 0 #Basically this will crash all the electronics and the software.
                out = 0
                sysData[M]['present'] = 0
                print(str(datetime.now()) + 'Failed to communicate to a device 10 times. Disabling hardware and software!')
                tries = -1
                os._exit(4)

        time.sleep(0.0005)

        try:
            sysItems['Multiplexer']['device'].write8(int(0x00), int(0x00)) #Disconnect multiplexer with each iteration.
        except Exception:
            print(str(datetime.now()) + 'Failed to disconnect multiplexer on device ' + str(M))
            logger.exception('Failed to disconnect multiplexer on %s', M)

        return(out)
    finally:
        lock.release() #Bus lock is released so next command can occur.


def setPWM(M, device, channels, fraction, ConsecutiveFails):
    # Sets up the PWM chip (either the one in the reactor or on the pump board)
    if sysDevices[M][device]['startup'] == 0: #The following boots up the respective PWM device to the correct frequency. Potentially there is a bug here; if the device loses power after this code is run for the first time it may revert to default PWM frequency.
        I2CCom(M, device, 0, 8, 0x00, 0x10, 0) #Turns off device. Also disables all-call functionality at bit 0 so it won't respond to address 0x70
        I2CCom(M, device, 0, 8, 0x04, 0xe6, 0) #Sets SubADDR3 of the PWM chips to be 0x73 instead of 0x74 to avoid any potential collision with the multiplexer @ 0x74
        I2CCom(M, device, 0, 8, 0xfe, sysDevices[M][device]['frequency'], 0) #Sets frequency of PWM oscillator.
        sysDevices[M][device]['startup'] = 1

    I2CCom(M, device, 0, 8, 0x00, 0x00, 0) #Turns device on

    timeOn = int(fraction * 4095.99)
    I2CCom(M, device, 0, 8, channels['ONL'], 0x00, 0)
    I2CCom(M, device, 0, 8, channels['ONH'], 0x00, 0)

    OffVals = bin(timeOn)[2:].zfill(12)
    HighVals = '0000' + OffVals[0:4]
    LowVals = OffVals[4:12]

    I2CCom(M, device, 0, 8, channels['OFFL'], int(LowVals, 2), 0)
    I2CCom(M, device, 0, 8, channels['OFFH'], int(HighVals, 2), 0)

    if (device == 'Pumps'):
        I2CCom(M, device, 0, 8, channels['ONL'], 0x00, 0)
        I2CCom(M, device, 0, 8, channels['ONH'], 0x00, 0)
        I2CCom(M, device, 0, 8, channels['OFFL'], int(LowVals, 2), 0)
        I2CCom(M, device, 0, 8, channels['OFFH'], int(HighVals, 2), 0)
    else:
        CheckLow = I2CCom(M, device, 1, 8, channels['OFFL'], -1, 0)
        CheckHigh = I2CCom(M, device, 1, 8, channels['OFFH'], -1, 0)
        CheckLowON = I2CCom(M, device, 1, 8, channels['ONL'], -1, 0)
        CheckHighON = I2CCom(M, device, 1, 8, channels['ONH'], -1, 0)

        if(CheckLow != (int(LowVals, 2)) or CheckHigh != (int(HighVals, 2)) or CheckHighON != int(0x00) or CheckLowON != int(0x00)): #We check to make sure it has been set to appropriate values.
            ConsecutiveFails = ConsecutiveFails + 1
            print(str(datetime.now()) + ' Failed transmission test on ' + str(device) + ' ' + str(ConsecutiveFails) + ' times consecutively on device '  + str(M) )
            if ConsecutiveFails > 10:
                sysItems['Watchdog']['ON'] = 0 #Basically this will crash all the electronics and the software.
                print(str(datetime.now()) + 'Failed to communicate to PWM 10 times. Disabling hardware and software!')
                os._exit(4)
            else:
                time.sleep(0.1)
                sysItems['FailCount'] = sysItems['FailCount'] + 1
                setPWM(M, device, channels, fraction, ConsecutiveFails)
