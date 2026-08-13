######### Chi.Bio Operating System V1.0 #########

#Import required python packages
import os
import random
import time
import math
import logging
from flask import Flask, render_template, jsonify, request
from chibio_auth import init_auth
from chibio_experiment import PumpModulation, RegulateOD, Thermostat, Zigzag, runExperiment
from chibio_hardware import (I2CCom, get_i2c_device, measurement_sequence, setPWM,
                             setup_watchdog, start_stall_watchdog)
from chibio_optics import adc_full_scale, get_light, get_spectrum
from chibio_state import sysData, sysDevices, sysItems
import chibio_sim
from threading import Thread
import threading
from datetime import datetime, date
import time
import simplejson
import smbus2 as smbus


application = Flask(__name__)
application.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0 #Try this https://stackoverflow.com/questions/23112316/using-flask-how-do-i-modify-the-cache-control-header-for-all-output/23115561#23115561

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(threadName)s %(message)s'
)
logger = logging.getLogger('chibio')

init_auth(application, logger)

# CHIBIO_MOCK_HW lets `import app` succeed on a dev laptop (no GPIO/I2C) for smoke
# tests, by skipping the two hardware entry points: the watchdog and initialiseAll.
# See the mock GPIO in chibio_hardware.py. Unset (the device default) = real hardware.
# CHIBIO_SIM implies MOCK_HW but goes further: it fakes the bus and then runs the
# real initialiseAll() on top, so the UI works with no reactors attached. Both flags
# live in chibio_sim so app and chibio_hardware can't disagree about them.
MOCK_HW = chibio_sim.MOCK_HW

if not MOCK_HW:
    setup_watchdog()


@application.after_request
def add_no_cache_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


# Backstop against a command burst spawning threads faster than they retire. Each background
# task is slow (a measurement settles in ~1.6 s) and they all contend for one global bus lock,
# so an uncapped spawn turns a fast series of clicks into a pile of blocked threads and an
# unresponsive server. Well above any legitimate burst: 8 reactors x a handful of actions.
_MAX_BACKGROUND_THREADS = 64
_background_count = [0]
_background_count_lock = threading.Lock()


def run_background(target, *args, **kwargs):
    name = getattr(target, '__name__', 'task')
    with _background_count_lock:
        if _background_count[0] >= _MAX_BACKGROUND_THREADS:
            logger.error('Refusing to start background task %s: %d already running. '
                         'Commands are arriving faster than the bus can service them.',
                         name, _background_count[0])
            return None
        _background_count[0] += 1

    def wrapper():
        try:
            target(*args, **kwargs)
        except Exception:
            logger.exception('Background task failed: %s', name)
        finally:
            with _background_count_lock:
                _background_count[0] -= 1

    thread = Thread(target=wrapper)
    thread.setDaemon(True)
    thread.start()
    return thread


# One in-flight slot per (reactor, exact measurement). Keyed on the arguments too, so
# Internal/External/IR temperature are three distinct measurements rather than one.
_measure_inflight = {}
_measure_inflight_lock = threading.Lock()


def _inflight_slot(key):
    with _measure_inflight_lock:
        slot = _measure_inflight.get(key)
        if slot is None:
            slot = threading.Lock()
            _measure_inflight[key] = slot
        return slot


def run_measurement(target, M, *args):
    """Fire-and-forget a manual measurement, dropping it if the SAME one is already in flight.

    Measurement routes are fire-and-forget and settle in ~1.6 s. Firing faster than that used
    to let sibling threads switch the laser off mid-read (raw=0 with valid=1); the per-reactor
    measurement mutex now prevents that, but on its own it would convert a burst of clicks
    into a queue of blocked threads -- the soft-lock. A repeat of a measurement already
    running conveys nothing the first will not, so coalesce it instead of queueing.

    Coalescing is per exact measurement, NOT per reactor: distinct measurements issued
    back-to-back (as the self-test and the UI both do) must all run, and they serialize
    safely on the reactor's measurement mutex. Keying this too broadly silently drops real
    readings and leaves the stale previous value in their place.

    Returns True if a measurement was started, False if that same one was already running.
    """
    M = str(M)
    if M == "0":
        M = sysItems['UIDevice']
    name = getattr(target, '__name__', 'measurement')
    slot = _inflight_slot((M, name) + tuple(str(a) for a in args))
    if not slot.acquire(False):
        logger.info('Dropping %s%s on %s: that measurement is already in flight',
                    name, args if args else '', M)
        return False

    def guarded(*a):
        try:
            target(*a)
        finally:
            slot.release()

    if run_background(guarded, M, *args) is None:
        slot.release()
        return False
    return True


def initialise(M):
    #Function that initialises all parameters / clears stored values for a given device.
    #If you want to record/add values to sysData, recommend adding an initialisation line in here.
    global sysData
    global sysItems
    global sysDevices

    for LED in ['LEDA','LEDB','LEDC','LEDD','LEDE','LEDF','LEDG','LEDH','LEDI','LEDV']:
        sysData[M][LED]['target']=sysData[M][LED]['default']
        sysData[M][LED]['ON']=0

    sysData[M]['UV']['target']=sysData[M]['UV']['default']
    sysData[M]['UV']['ON']=0

    sysData[M]['LASER650']['target']=sysData[M]['LASER650']['default']
    sysData[M]['LASER650']['ON']=0

    FP='FP1'
    sysData[M][FP]['ON']=0
    sysData[M][FP]['LED']="LEDB"
    sysData[M][FP]['Base']=0
    sysData[M][FP]['Emit1']=0
    sysData[M][FP]['Emit2']=0
    sysData[M][FP]['Emit1Raw']=0  #emission counts before the Clear division
    sysData[M][FP]['Emit2Raw']=0
    sysData[M][FP]['BaseBand']="CLEAR"
    sysData[M][FP]['Emit1Band']="nm510"
    sysData[M][FP]['Emit2Band']="nm550"
    sysData[M][FP]['Gain']="x10"
    sysData[M][FP]['BaseRecord']=[]
    sysData[M][FP]['Emit1Record']=[]
    sysData[M][FP]['Emit2Record']=[]
    FP='FP2'
    sysData[M][FP]['ON']=0
    sysData[M][FP]['LED']="LEDD"
    sysData[M][FP]['Base']=0
    sysData[M][FP]['Emit1']=0
    sysData[M][FP]['Emit2']=0
    sysData[M][FP]['Emit1Raw']=0  #emission counts before the Clear division
    sysData[M][FP]['Emit2Raw']=0
    sysData[M][FP]['BaseBand']="CLEAR"
    sysData[M][FP]['Emit1Band']="nm583"
    sysData[M][FP]['Emit2Band']="nm620"
    sysData[M][FP]['BaseRecord']=[]
    sysData[M][FP]['Emit1Record']=[]
    sysData[M][FP]['Emit2Record']=[]
    sysData[M][FP]['Gain']="x10"
    FP='FP3'
    sysData[M][FP]['ON']=0
    sysData[M][FP]['LED']="LEDE"
    sysData[M][FP]['Base']=0
    sysData[M][FP]['Emit1']=0
    sysData[M][FP]['Emit2']=0
    sysData[M][FP]['Emit1Raw']=0  #emission counts before the Clear division
    sysData[M][FP]['Emit2Raw']=0
    sysData[M][FP]['BaseBand']="CLEAR"
    sysData[M][FP]['Emit1Band']="nm620"
    sysData[M][FP]['Emit2Band']="nm670"
    sysData[M][FP]['BaseRecord']=[]
    sysData[M][FP]['Emit1Record']=[]
    sysData[M][FP]['Emit2Record']=[]
    sysData[M][FP]['Gain']="x10"

    for PUMP in ['Pump1','Pump2','Pump3','Pump4']:
        sysData[M][PUMP]['default']=0.0
        sysData[M][PUMP]['target']=sysData[M][PUMP]['default']
        sysData[M][PUMP]['ON']=0
        sysData[M][PUMP]['direction']=1.0
        sysData[M][PUMP]['lastOntimeMs']=0.0  #achieved on-time of the last duty cycle (ms)
        sysDevices[M][PUMP]['threadCount']=0
        sysDevices[M][PUMP]['active']=0
        sysDevices[M][PUMP]['running']=0

    sysData[M]['Heat']['default']=0
    sysData[M]['Heat']['target']=sysData[M]['Heat']['default']
    sysData[M]['Heat']['ON']=0

    sysData[M]['Thermostat']['default']=37.0
    sysData[M]['Thermostat']['target']=sysData[M]['Thermostat']['default']
    sysData[M]['Thermostat']['ON']=0
    sysData[M]['Thermostat']['Integral']=0
    sysData[M]['Thermostat']['last']=-1

    sysData[M]['Stir']['target']=sysData[M]['Stir']['default']
    sysData[M]['Stir']['ON']=0

    sysData[M]['Light']['target']=sysData[M]['Light']['default']
    sysData[M]['Light']['ON']=0
    sysData[M]['Light']['Excite']='LEDD'

    sysData[M]['Custom']['Status']=sysData[M]['Custom']['default']
    sysData[M]['Custom']['ON']=0
    sysData[M]['Custom']['Program']='C1'

    sysData[M]['Custom']['param1']=0.0
    sysData[M]['Custom']['param2']=0.0
    sysData[M]['Custom']['param3']=0.0

    sysData[M]['OD']['current']=0.0
    sysData[M]['OD']['target']=sysData[M]['OD']['default']
    sysData[M]['OD0']['target']=65000.0
    sysData[M]['OD0']['raw']=65000.0
    sysData[M]['OD0']['dark']=0.0          #DARK-channel background measured alongside the OD read.
    sysData[M]['OD0']['rawCorrected']=65000.0  #raw transmission minus dark (kept separate; raw is never overwritten).
    sysData[M]['OD']['device']='LASER650'

    sysData[M]['Volume']['target']=20.0

    clearTerminal(M)
    addTerminal(M,'System Initialised')

    sysData[M]['Experiment']['ON']=0
    sysData[M]['Experiment']['cycles']=0
    sysData[M]['Experiment']['threadCount']=0
    sysData[M]['Experiment']['startTime']=' Waiting '
    sysData[M]['Experiment']['startTimeRaw']=0
    sysData[M]['Experiment']['lastCycleMonotonic']=0.0  #time.monotonic() of the last completed cycle (liveness; NOT a wall clock)
    sysData[M]['Experiment']['stalled']=0         #set by the experiment watchdog when cycles stop advancing
    sysData[M]['OD']['ON']=0
    sysData[M]['OD']['Measuring']=0
    sysData[M]['OD']['Integral']=0.0
    sysData[M]['OD']['Integral2']=0.0
    sysData[M]['Zigzag']['ON']=0
    sysData[M]['Zigzag']['target']=0.0
    sysData[M]['Zigzag']['SwitchPoint']=0
    sysData[M]['GrowthRate']['current']=sysData[M]['GrowthRate']['default']

    sysDevices[M]['Thermostat']['threadCount']=0
    sysDevices[M]['Thermostat']['running']=0

    channels=['nm410','nm440','nm470','nm510','nm550','nm583','nm620', 'nm670','CLEAR','NIR','DARK','ExtGPIO', 'ExtINT' , 'FLICKER']
    for channel in channels:
        sysData[M]['AS7341']['channels'][channel]=0
        sysData[M]['AS7341']['spectrum'][channel]=0
    DACS=['ADC0', 'ADC1', 'ADC2', 'ADC3', 'ADC4', 'ADC5']
    for DAC in DACS:
        sysData[M]['AS7341']['current'][DAC]=0

    # Read-validity flags (see sensor-failure-semantics): default valid; a failed
    # spectrometer read flips these to 0, which makes csvData record NaN for that cycle.
    sysData[M]['AS7341']['current']['valid']=1
    sysData[M]['AS7341']['current']['gain']=0  #Gain actually used on the last read (auto-ranging updates it).
    sysData[M]['AS7341']['current']['saturated']=0     #chip's own ASAT flag (STATUS2), latched with the last read
    sysData[M]['AS7341']['current']['fullScale']=adc_full_scale(255)  #digital ceiling of the last read
    sysData[M]['OD']['valid']=1
    sysData[M]['OD']['spread']=0.0  #max-min of the replicate OD reads (measurement noise).
    sysData[M]['OD']['corrected']=0.0  #dark-corrected OD (display-only; never feeds control).
    for FP in ['FP1','FP2','FP3']:
        sysData[M][FP]['valid']=1
        sysData[M][FP]['GainUsed']=int(sysData[M][FP]['Gain'][1:])  #gain the last FP read landed on
        sysData[M][FP]['spread']=0.0  #max-min of the replicate FP base reads.

    #Timed media/inducer schedule (see chibio_schedule.py). Stages are (hour -> item -> target);
    #RAM-only like the OD blank and the FP reference, so re-set it after a restart.
    sysData[M]['Schedule']={'ON':0, 'stages':[], 'applied':-1, 'status':'', 'threadCount':0}
    sysDevices[M]['scheduleRunning']=0

    #Fluorescence-assist scan result (excitation-emission matrix + recommended FP settings).
    sysData[M]['FluorescenceScan']={'matrix':{}, 'recommendation':None, 'mode':'', 'status':'', 'bands':[], 'referenced':0}
    #A matched NON-fluorescent scan to subtract before recommending. Without one the assist
    #reads biomass: measured 2026-08-13, a sterile tube of medium and three WT cultures all
    #returned the same confident LEDI(550)->nm583 pick, with the reported "signal" tracking
    #turbidity. RAM-only like the OD blank -- re-set it after a restart.
    sysData[M]['FluorescenceReference']={'from':'', 'time':''}
    sysDevices[M]['fluorReferenceMatrix']=None  #the EEM itself: bulk, and the UI never reads it

    sysData[M]['ThermometerInternal']['current']=0.0
    sysData[M]['ThermometerExternal']['current']=0.0
    sysData[M]['ThermometerIR']['current']=0.0

    sysData[M]['time']['record']=[]
    sysData[M]['OD']['record']=[]
    sysData[M]['OD']['targetrecord']=[]
    sysData[M]['OD']['spreadRecord']=[]      #replicate spread per cycle (chart error band)
    sysData[M]['OD']['correctedRecord']=[]   #dark-corrected OD per cycle (chart trace)
    sysData[M]['Pump1']['record']=[]
    sysData[M]['Pump2']['record']=[]
    sysData[M]['Pump3']['record']=[]
    sysData[M]['Pump4']['record']=[]
    sysData[M]['Heat']['record']=[]
    sysData[M]['Light']['record']=[]
    sysData[M]['ThermometerInternal']['record']=[]
    sysData[M]['ThermometerExternal']['record']=[]
    sysData[M]['ThermometerIR']['record']=[]
    sysData[M]['Thermostat']['record']=[]

    sysData[M]['GrowthRate']['record']=[]

    sysDevices[M]['ThermometerInternal']['device']=get_i2c_device(0x18,2) #Get Thermometer on Bus 2!!!
    sysDevices[M]['ThermometerExternal']['device']=get_i2c_device(0x1b,2) #Get Thermometer on Bus 2!!!
    sysDevices[M]['DAC']['device']=get_i2c_device(0x48,2) #Get DAC on Bus 2!!!
    sysDevices[M]['AS7341']['device']=get_i2c_device(0x39,2) #Get OD Chip on Bus 2!!!!!
    sysDevices[M]['Pumps']['device']=get_i2c_device(0x61,2) #Get OD Chip on Bus 2!!!!!
    sysDevices[M]['Pumps']['startup']=0
    sysDevices[M]['Pumps']['frequency']=0x1e #200Hz PWM frequency
    sysDevices[M]['PWM']['device']=get_i2c_device(0x60,2) #Get OD Chip on Bus 2!!!!!
    sysDevices[M]['PWM']['startup']=0
    sysDevices[M]['PWM']['frequency']=0x03 #1526 Hz PWM frequency for fan/LEDs, maximum possible.
    sysDevices[M]['ThermometerIR']['device']=smbus.SMBus(bus=2) #Set up SMBus thermometer
    sysDevices[M]['ThermometerIR']['address']=0x5a

    scan_devices_sync(M)
    if(sysData[M]['present']==1):
        turnEverythingOff(M)

        V1_Present=0
        V2_Present=0
        # This detection runs at ISteps=10, where full scale is 11,000 counts -- NOT 65535.
        # If a bright board pins both Baseline and NewLevel, the ratio test below silently
        # reads "LED absent" and falls through to V1 on a V2 board (wrong excitation panel,
        # no FP3 LEDE->LEDH remap). Saturation is now detectable, so say so loudly rather
        # than returning a confident wrong answer.
        detectCeiling=adc_full_scale(10)
        # Both detections are baseline-then-pulse comparisons, so anything that flashes a
        # light on this reactor in between changes the answer -- and the answer decides which
        # excitation panel the whole board uses. Harmless at boot (no threads yet), but
        # initialise() is also reachable at runtime via /ExperimentReset.
        # Now we will detect LED version First checking for version 2
        with measurement_sequence(M):
            out=get_light(M,['nm583'],10,10) #Measure with maximum gain (10) and for short period.
            Baseline=out[0]
            set_output_on_sync(M,'LEDH',1) #Turn on LEDH at default level - should only be present in version 2
            try:
                out=get_light(M,['nm583'],10,10)
                NewLevel=out[0]
            finally:
                set_output_on_sync(M,'LEDH',0) #Turn off LEDH at default level - should only be present in version 2
        if (Baseline>=detectCeiling or NewLevel>=detectCeiling):
            logger.error('LED version detection on %s saturated at ISteps=10 (baseline %d, '
                         'pulsed %d, full scale %d) - the V2 test is unreliable here',
                         M, Baseline, NewLevel, detectCeiling)
        if (NewLevel>Baseline*3+20):
            V2_Present = 1

        # Now we will detect for Version 1
        with measurement_sequence(M):
            out=get_light(M,['nm583'],10,10) #Measure with maximum gain (10) and for short period.
            Baseline=out[0]
            set_output_on_sync(M,'LEDG',1) #Turn on LEDG at default level - should only be present in version 1
            try:
                out=get_light(M,['nm583'],10,10)
                NewLevel=out[0]
            finally:
                set_output_on_sync(M,'LEDG',0) #Turn off LEDG at default level - should only be present in version 1

        if (NewLevel>Baseline*3+20):
            V1_Present = 1

        if (V1_Present==1 and V2_Present==0):
            sysData[M]['Version']['LED']=1
        elif (V1_Present==0 and V2_Present==1):
            sysData[M]['Version']['LED']=2
        else:
            sysData[M]['Version']['LED']=1 #We have messed up somehow in this case and stuff isn't going to work well
            print(str(datetime.now()) + " ERROR on " + str(M) +', this device has an unknown LED version. Defaulting to version 1.')

        # The FP defaults above are set before the version is known, and FP3's (LEDE, 595nm) is
        # a V1-only channel. Driving an absent LED is a silent no-op, so on V2 this left FP3
        # exciting nothing while still recording the emit/base ratio as a valid reading -- and
        # it rendered the Excite dropdown blank, since the V2 option list has no LEDE. LEDH
        # (600/80) is the V2 analogue: it takes LEDE's slot in the excitation set and keeps the
        # >=20nm Stokes shift to FP3's nm620/nm670 emission bands. FP1 (LEDB) and FP2 (LEDD)
        # exist on both versions and need no remap.
        if sysData[M]['Version']['LED']==2:
            sysData[M]['FP3']['LED']="LEDH"

        print(str(datetime.now()) + " Initialised " + str(M) +', LED Version: ' + str(sysData[M]['Version']['LED']) + ', Device ID: ' + sysData[M]['DeviceID'])


def initialiseAll():
    # Initialisation function which runs at when software is started for the first time.
    sysItems['Multiplexer']['device']=get_i2c_device(0x74,2)
    sysItems['FailCount']=0
    time.sleep(2.0) #This wait is to allow the watchdog circuit to boot.
    print(str(datetime.now()) + ' Initialising devices')

    for M in ['M0','M1','M2','M3','M4','M5','M6','M7']:
        initialise(M)
    scan_devices_sync("all")


def turnEverythingOff(M):
    # Function which turns off all actuation/hardware.
    for LED in ['LEDA','LEDB','LEDC','LEDD','LEDE','LEDF','LEDG','LEDH','LEDI','LEDV']:
        sysData[M][LED]['ON']=0

    sysData[M]['LASER650']['ON']=0
    sysData[M]['Pump1']['ON']=0
    sysData[M]['Pump2']['ON']=0
    sysData[M]['Pump3']['ON']=0
    sysData[M]['Pump4']['ON']=0
    sysData[M]['Stir']['ON']=0
    sysData[M]['Heat']['ON']=0
    sysData[M]['UV']['ON']=0

    I2CCom(M,'DAC',0,8,int('00000000',2),int('00000000',2),0)#Sets all DAC Channels to zero!!!
    setPWM(M,'PWM',sysItems['All'],0,0)
    setPWM(M,'Pumps',sysItems['All'],0,0)

    set_output_on_sync(M,'Stir',0)
    set_output_on_sync(M,'Thermostat',0)
    set_output_on_sync(M,'Heat',0)
    set_output_on_sync(M,'UV',0)
    set_output_on_sync(M,'Pump1',0)
    set_output_on_sync(M,'Pump2',0)
    set_output_on_sync(M,'Pump3',0)
    set_output_on_sync(M,'Pump4',0)


@application.route('/')
def index():
    #Function responsible for sending appropriate device's data to user interface.
    global sysData
    global sysItems

    outputdata=sysData[sysItems['UIDevice']]
    for M in ['M0','M1','M2','M3','M4','M5','M6','M7']:
            if sysData[M]['present']==1:
                outputdata['presentDevices'][M]=1
            else:
                outputdata['presentDevices'][M]=0
    return render_template('index.html',**outputdata)


@application.route('/getSysdata/')
def getSysdata():
    #Similar to function above, packages data to be sent to UI.
    global sysData
    global sysItems
    outputdata=sysData[sysItems['UIDevice']]
    for M in ['M0','M1','M2','M3','M4','M5','M6','M7']:
            if sysData[M]['present']==1:
                outputdata['presentDevices'][M]=1
            else:
                outputdata['presentDevices'][M]=0
    return jsonify(outputdata)


@application.route('/changeDevice/<M>',methods=['POST'])
def changeDevice(M):
    #Function responsible for changin which device is selected in the UI.
    global sysData
    global sysItems
    M=str(M)
    if sysData[M]['present']==1:
        for Mb in ['M0','M1','M2','M3','M4','M5','M6','M7']:
            sysData[Mb]['UIDevice']=M

        sysItems['UIDevice']=M

    return ('', 204)


@application.route('/scanDevices/<which>',methods=['POST'])
def scanDevices(which):
    run_background(scan_devices_sync, which)
    return ('', 204)


def scan_devices_sync(which):
    #Scans to decide which devices are plugged in/on. Does this by trying to communicate with their internal thermometers.
    global sysData
    which=str(which)

    if which=="all":
        for M in ['M0','M1','M2','M3','M4','M5','M6','M7']:
            sysData[M]['present']=1
            I2CCom(M,'ThermometerInternal',1,16,0x05,0,0) #We arbitrarily poll the thermometer to see if anything is plugged in!
            sysData[M]['DeviceID']=GetID(M)
    else:

        sysData[which]['present']=1
        I2CCom(which,'ThermometerInternal',1,16,0x05,0,0)
        sysData[which]['DeviceID']=GetID(which)


def GetID(M):
    #Gets the CHi.Bio reactor's ID, which is basically just the unique ID of the infrared thermometer.
    global sysData
    M=str(M)
    ID=''
    if sysData[M]['present']==1:
        pt1=str(I2CCom(M,'ThermometerIR',1,0,0x3C,0,1))
        pt2=str(I2CCom(M,'ThermometerIR',1,0,0x3D,0,1))
        pt3=str(I2CCom(M,'ThermometerIR',1,0,0x3E,0,1))
        pt4=str(I2CCom(M,'ThermometerIR',1,0,0x3F,0,1))
        ID = pt1+pt2+pt3+pt4

    return ID


def addTerminal(M,strIn):
    #Responsible for adding a new line to the terminal in the UI.
    global sysData
    now=datetime.now()
    timeString=now.strftime("%Y-%m-%d %H:%M:%S ")
    sysData[M]['Terminal']['text']=timeString + ' - ' +  str(strIn) + '</br>' + sysData[M]['Terminal']['text']


@application.route("/ClearTerminal/<M>",methods=['POST'])
def clearTerminal(M):
    #Deletes everything from the terminal.
    global sysData
    M=str(M)
    if (M=="0"):
        M=sysItems['UIDevice']

    sysData[M]['Terminal']['text']=''
    addTerminal(M,'Terminal Cleared')
    return ('', 204)


@application.route("/SetFPMeasurement/<item>/<Excite>/<Base>/<Emit1>/<Emit2>/<Gain>",methods=['POST'])
def SetFPMeasurement(item,Excite,Base,Emit1,Emit2,Gain):
    #Sets up the fluorescent protein measurement in terms of gain, and which LED / measurement bands to use.
    FP=str(item)
    Excite=str(Excite)
    Base=str(Base)
    Emit1=str(Emit1)
    Emit2=str(Emit2)
    Gain=str(Gain)
    M=sysItems['UIDevice']

    from chibio_control_helpers import logEvent
    if sysData[M][FP]['ON']==1:
        sysData[M][FP]['ON']=0
        logEvent(M, 'fp_config', {'slot': FP, 'on': 0})  #self-describe the mid-run change (no-op if not running)
        return ('', 204)
    else:
        sysData[M][FP]['ON']=1
        sysData[M][FP]['LED']=Excite
        sysData[M][FP]['BaseBand']=Base
        sysData[M][FP]['Emit1Band']=Emit1
        sysData[M][FP]['Emit2Band']=Emit2
        sysData[M][FP]['Gain']=Gain
        logEvent(M, 'fp_config', {'slot': FP, 'on': 1, 'led': Excite, 'base': Base,
                                  'emit1': Emit1, 'emit2': Emit2, 'gain': Gain})
        return ('', 204)


@application.route("/FluorescenceScan/<M>/<mode>",methods=['POST'])
def FluorescenceScan(M,mode):
    #Scan the sample across excitation LEDs, build an EEM and recommend FP settings.
    #mode: 'quick' (one power/LED) or 'full' (power sweep). See chibio_fluorescence.
    from chibio_fluorescence import fluorescence_scan
    run_background(fluorescence_scan, M, str(mode))
    return ('', 204)


@application.route("/SetFluorescenceReference/<M>/<source>",methods=['POST'])
def SetFluorescenceReference(M,source):
    #Adopt <source>'s last completed scan as M's matched non-fluorescent reference, so the
    #assist recommends on the residual instead of on raw counts dominated by scatter.
    #<source>: a device ('M2'), 'self', or 'clear'. Synchronous -- it is pure state, no bus.
    from chibio_fluorescence import set_fluorescence_reference
    ok = set_fluorescence_reference(M, source)
    return ('', 204) if ok else ('no completed scan on that device', 409)


# ponytail: cross-request ordering race. SetOutputTarget/SetOutputOn run as
# separate background threads, so two rapid UI actions can execute out of order —
# `lock` serializes the bus, not intent. Self-heals: RegulateOD re-asserts state
# each cycle. Upgrade path: a per-device command queue if ordering ever matters.
@application.route("/SetSchedule/<M>",methods=['POST'])
def SetSchedule(M):
    #Store a timed media/inducer schedule. Body is JSON: {"stages": [{"at_h":0,"item":"Pump3",
    #"target":0.0}, {"at_h":12,"item":"Pump3","target":0.02,"ramp":1}, ...]}.
    #Synchronous and pure state -- validation must reject a bad schedule while the operator is
    #still looking at it, not in a control thread an hour later.
    from chibio_schedule import set_schedule
    body = request.get_json(force=True, silent=True) or {}
    ok, err = set_schedule(M, body.get('stages', []))
    return ('', 204) if ok else (err, 400)


@application.route("/ScheduleOnOff/<value>/<M>",methods=['POST'])
def ScheduleOnOff(M,value):
    from chibio_schedule import schedule_on_off
    ok, err = schedule_on_off(M, value)
    return ('', 204) if ok else (err, 409)


@application.route("/SetOutputTarget/<item>/<M>/<value>",methods=['POST'])
def SetOutputTarget(M,item, value):
    run_background(set_output_target_sync, M, item, value)
    return ('', 204)


@application.route("/SetOutputOn/<item>/<force>/<M>",methods=['POST'])
def SetOutputOn(M,item,force):
    run_background(set_output_on_sync, M, item, force)
    return ('', 204)


def set_output_target_sync(M, item, value):
    #General function used to set the output level of a particular item, ensuring it is within an acceptable range.
    global sysData
    item = str(item)
    value = float(value)
    M=str(M)
    if (M=="0"):
        M=sysItems['UIDevice']
    print(str(datetime.now()) + " Set item: " + str(item) + " to value " + str(value) + " on " + str(M))
    if (value<sysData[M][item]['min']):
        value=sysData[M][item]['min']
    if (value>sysData[M][item]['max']):
        value=sysData[M][item]['max']

    sysData[M][item]['target']=value

    # ponytail: pump-restart TOCTOU. The old modulation loop can exit (running->0)
    # between this off and on, leaving ON==1 with no loop. Self-heals: worst case is
    # one missed pump cycle, restarted next minute. Upgrade path: hold `lock` across
    # the off/on pair if a missed cycle ever matters.
    if(sysData[M][item]['ON']==1 and not(item=='OD' or item=='Thermostat')):
        set_output_on_sync(M,item,0)
        set_output_on_sync(M,item,1)


def set_output_on_sync(M, item, force):
    #General function used to switch an output on or off.
    global sysData
    item = str(item)

    force = int(force)
    M=str(M)
    if (M=="0"):
        M=sysItems['UIDevice']
    if (force==1):
        sysData[M][item]['ON']=1
        SetOutput(M,item)
        return

    elif(force==0):
        sysData[M][item]['ON']=0
        SetOutput(M,item)
        return

    if (sysData[M][item]['ON']==0):
        sysData[M][item]['ON']=1
        SetOutput(M,item)
        return

    sysData[M][item]['ON']=0
    SetOutput(M,item)


def SetOutput(M,item):
    #Here we actually do the digital communications required to set a given output. This function is called by SetOutputOn above as required.
    global sysData
    global sysItems
    global sysDevices
    M=str(M)
    if(item=='Stir'):
        if (sysData[M][item]['target']*float(sysData[M][item]['ON'])>0):
            setPWM(M,'PWM',sysItems[item],1.0*float(sysData[M][item]['ON']),0)
            time.sleep(1.5)

            if (sysData[M][item]['target']>0.4 and sysData[M][item]['ON']==1):
                setPWM(M,'PWM',sysItems[item],0.5*float(sysData[M][item]['ON']),0)
                time.sleep(0.75)

            if (sysData[M][item]['target']>0.8 and sysData[M][item]['ON']==1):
                setPWM(M,'PWM',sysItems[item],0.7*float(sysData[M][item]['ON']),0)
                time.sleep(0.75)

        setPWM(M,'PWM',sysItems[item],sysData[M][item]['target']*float(sysData[M][item]['ON']),0)

    elif(item=='Heat'):
        setPWM(M,'PWM',sysItems[item],sysData[M][item]['target']*float(sysData[M][item]['ON']),0)
    elif(item=='UV'):
        setPWM(M,'PWM',sysItems[item],sysData[M][item]['target']*float(sysData[M][item]['ON']),0)
    elif (item=='Thermostat'):
        if sysDevices[M][item].get('running', 0) == 0:
            sysDevices[M][item]['running']=1
            sysDevices[M][item]['thread']=Thread(target = Thermostat, args=(M,item))
            sysDevices[M][item]['thread'].setDaemon(True)
            sysDevices[M][item]['thread'].start()

    elif (item=='Pump1' or item=='Pump2' or item=='Pump3' or item=='Pump4'):
        if (sysData[M][item]['target']==0):
            sysData[M][item]['ON']=0
        if sysDevices[M][item].get('running', 0) == 0:
            sysDevices[M][item]['running']=1
            sysDevices[M][item]['thread']=Thread(target = PumpModulation, args=(M,item))
            sysDevices[M][item]['thread'].setDaemon(True)
            sysDevices[M][item]['thread'].start()

    elif (item=='OD'):
        set_output_on_sync(M,'Pump1',0)
        set_output_on_sync(M,'Pump2',0)
    elif (item=='Zigzag'):
        sysData[M]['Zigzag']['target']=5.0
        sysData[M]['Zigzag']['SwitchPoint']=sysData[M]['Experiment']['cycles']

    elif (item=='LEDA' or item=='LEDC' or item=='LEDD' or item=='LEDE' or item=='LEDF' or item=='LEDG' or item == 'LEDH'):
        setPWM(M,'PWM',sysItems[item],sysData[M][item]['target']*float(sysData[M][item]['ON']),0)
    elif (item=='LEDB' or item == 'LEDI'):
        if (sysData[M]['LEDV']['target']*float(sysData[M]['LEDV']['ON'])>0):
            if (item=='LEDB'):
                LEDV_Intensity = sysData[M]['LEDV']['target']*sysData[M]['LEDV']['ScaleFactor']
            elif (item == 'LEDI'):
                LEDV_Intensity = sysData[M]['LEDV']['target']

            NewIntensity = sysData[M][item]['target']*float(sysData[M][item]['ON']) + LEDV_Intensity
            if (NewIntensity>1.0):
                NewIntensity=1.0

            setPWM(M,'PWM',sysItems[item],NewIntensity,0)

        else:
            setPWM(M,'PWM',sysItems[item],sysData[M][item]['target']*float(sysData[M][item]['ON']),0)
    elif (item=='LEDV'):
        LEDB_Intensity = sysData[M]['LEDV']['target']*float(sysData[M]['LEDV']['ON'])*sysData[M]['LEDV']['ScaleFactor']
        LEDB_Intensity = LEDB_Intensity + sysData[M]['LEDB']['target']*float(sysData[M]['LEDB']['ON'])

        LEDI_Intensity = sysData[M]['LEDV']['target']*float(sysData[M]['LEDV']['ON'])
        LEDI_Intensity = LEDI_Intensity + sysData[M]['LEDI']['target']*float(sysData[M]['LEDI']['ON'])

        if (LEDB_Intensity>1.0):
            LEDB_Intensity=1.0
        if (LEDI_Intensity>1.0):
            LEDI_Intensity=1.0

        setPWM(M,'PWM',sysItems['LEDB'],LEDB_Intensity,0)
        setPWM(M,'PWM',sysItems['LEDI'],LEDI_Intensity,0)

    elif(item == 'LASER650'):
        value=sysData[M][item]['target']*float(sysData[M][item]['ON'])
        if (value==0):
            value=0
        else:
            value=(value+0.00)/1.00
            sf=0.303
            value=value*sf
        binaryValue=bin(int(value*4095.9))
        toWrite=str(binaryValue[2:].zfill(16))
        toWrite1=int(toWrite[0:8],2)
        toWrite2=int(toWrite[8:16],2)
        I2CCom(M,'DAC',0,8,toWrite1,toWrite2,0)
        
        
    
    
    
    
        

@application.route("/Direction/<item>/<M>",methods=['POST'])
def direction(M,item):
    #Flips direction of a pump.
    global sysData
    M=str(M)
    if (M=="0"):
        M=sysItems['UIDevice']
    sysData[M][item]['target']=-1.0*sysData[M][item]['target']
    if (sysData[M]['OD']['ON']==1):
            sysData[M][item]['direction']=-1.0*sysData[M][item]['direction']

    return ('', 204)  
    

    
@application.route("/GetSpectrum/<Gain>/<M>",methods=['POST'])
def GetSpectrum(M,Gain):
    run_background(get_spectrum, M, Gain)
    return ('', 204)




@application.route("/SetCustom/<Program>/<Status>",methods=['POST'])
def SetCustom(Program,Status):
    #Turns a custom program on/off.
	
    global sysData
    M=sysItems['UIDevice']
    item="Custom"
    if sysData[M][item]['ON']==1:
        sysData[M][item]['ON']=0
    else:
        sysData[M][item]['Program']=str(Program)
        sysData[M][item]['Status']=float(Status)
        sysData[M][item]['ON']=1
        sysData[M][item]['param1']=0.0 #Thus parameters get reset each time you restart your program.
        sysData[M][item]['param2']=0.0
        sysData[M][item]['param3']=0.0
    return('',204)
		
        
@application.route("/SetLightActuation/<Excite>",methods=['POST'])
def SetLightActuation(Excite):
    #Basic function used to set which LED is used for optogenetics.
    global sysData
    M=sysItems['UIDevice']
    item="Light"
    if sysData[M][item]['ON']==1:
        sysData[M][item]['ON']=0
        set_output_on_sync(M,sysData[M][item]['Excite'],0) #In case the current LED is on we need to make sure it turns off
        return ('', 204)
    else:
        sysData[M][item]['Excite']=str(Excite)
        sysData[M][item]['ON']=1
        return('',204)


@application.route("/CharacteriseDevice/<M>/<Program>",methods=['POST'])     
def CharacteriseDevice(M,Program): 
    # THis umbrella function is used to run the actual characteriseation function in a thread to prevent GUnicorn worker timeout.
    Program=str(Program)
    M=str(M)
    if (M=="0"):
        M=sysItems['UIDevice']
    # Refuse while an experiment is running on this reactor. The sweep drives LASER650 across
    # its whole power range, including 0, so no OD reading taken during it means anything --
    # measured 2026-08-12, a concurrent cycle logged OD 9.99 while the sweep sat near zero
    # power. The per-reactor mutex makes each read atomic but cannot make a shared power
    # target hold still between them. This is a calibration routine; it needs the reactor.
    if (sysData[M]['Experiment']['ON']==1):
        logger.error('Refusing to characterise %s: an experiment is running. The power sweep '
                     'would corrupt its OD readings.', M)
        addTerminal(M,'Characterisation refused - stop the experiment first')
        return('',409)
    if (Program=='C1'):
        cthread=Thread(target = CharacteriseDevice2, args=(M,))
        cthread.setDaemon(True)
        cthread.start()

    return('',204)
        
        
        
def CharacteriseDevice2(M):
    global sysData
    global sysItems
    print('In1')
    M=str(M)
    if (M=="0"):
        M=sysItems['UIDevice']
        
    result= { 'LEDA' : {'nm410' : [],'nm440' : [],'nm470' : [],'nm510' : [],'nm550' : [],'nm583' : [],'nm620' : [],'nm670' : [],'CLEAR' : []},
        'LEDB' : {'nm410' : [],'nm440' : [],'nm470' : [],'nm510' : [],'nm550' : [],'nm583' : [],'nm620' : [],'nm670' : [],'CLEAR' : []},
        'LEDC' : {'nm410' : [],'nm440' : [],'nm470' : [],'nm510' : [],'nm550' : [],'nm583' : [],'nm620' : [],'nm670' : [],'CLEAR' : []},
        'LEDD' : {'nm410' : [],'nm440' : [],'nm470' : [],'nm510' : [],'nm550' : [],'nm583' : [],'nm620' : [],'nm670' : [],'CLEAR' : []},
        'LEDE' : {'nm410' : [],'nm440' : [],'nm470' : [],'nm510' : [],'nm550' : [],'nm583' : [],'nm620' : [],'nm670' : [],'CLEAR' : []},
        'LEDF' : {'nm410' : [],'nm440' : [],'nm470' : [],'nm510' : [],'nm550' : [],'nm583' : [],'nm620' : [],'nm670' : [],'CLEAR' : []},
        'LEDG' : {'nm410' : [],'nm440' : [],'nm470' : [],'nm510' : [],'nm550' : [],'nm583' : [],'nm620' : [],'nm670' : [],'CLEAR' : []},
        'LASER650' : {'nm410' : [],'nm440' : [],'nm470' : [],'nm510' : [],'nm550' : [],'nm583' : [],'nm620' : [],'nm670' : [],'CLEAR' : []},
        }
        
        
    print('Got in!')   
    bands=['nm410' ,'nm440','nm470','nm510','nm550','nm583','nm620','nm670','CLEAR']    
    powerlevels=[0,0.01,0.02,0.03,0.04,0.05,0.06,0.07,0.08,0.09,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0]
    items= ['LEDA','LEDB','LEDC','LEDD','LEDE','LEDF','LEDG','LASER650']
    gains=['x4','x4','x4','x4','x4','x4','x4','x1']
    # Remember every power target the sweep is about to overwrite. Without this the routine
    # leaves all of them at 1.0 (the last level swept), which silently rescales OD: the blank
    # was taken at LASER650=0.5, so the reactor keeps reporting against a laser at twice that
    # power until someone re-blanks or restarts. Measured 2026-08-12: M0 read OD 3.17 before
    # characterisation and 2.60 after, with nothing to indicate why.
    savedTargets={item: sysData[M][item]['target'] for item in items}
    try:
        gi=-1
        for item in items:
            gi=gi+1
            for power in powerlevels:
                # Same collision class as the FluorescenceScan: a drive-output -> read -> off
                # sequence on one reactor. Without the mutex, a concurrent experiment cycle
                # switches this LED off between the switch-on and the read (and vice versa),
                # which is unflagged in both directions. 160 sequences per reactor makes this the
                # heaviest such loop in the codebase, so it is the last place to leave unguarded.
                with measurement_sequence(M):
                    set_output_target_sync(M,item,power)
                    set_output_on_sync(M,item,1)
                    try:
                        get_spectrum(M,gains[gi])
                    finally:
                        set_output_on_sync(M,item,0)
                print(item + ' ' + str(power))
                for band in bands:
                    result[item][band].append(int(sysData[M]['AS7341']['spectrum'][band]))
                addTerminal(M,'Measured Item = ' + str(item) + ' at power ' + str(power))
                time.sleep(0.05)
    finally:
        # Restore unconditionally: a characterisation that dies partway must not leave the
        # reactor's OD laser at an arbitrary swept power.
        for item in items:
            set_output_on_sync(M,item,0)
            set_output_target_sync(M,item,savedTargets[item])
        addTerminal(M,'Output power levels restored after characterisation')
                
    
    filename = 'characterisation_data_' + M + '.txt'
    f = open(filename,'w')
    simplejson.dump(result,f)
    f.close()
    return

  
        
        

@application.route("/CalibrateOD/<item>/<M>/<value>/<value2>",methods=['POST'])
def CalibrateOD(M,item,value,value2):
    #Used to calculate calibration value for OD measurements.
    global sysData
    item = str(item)
    ODRaw = float(value)
    ODActual = float(value2)
    M=str(M)
    if (M=="0"):
        M=sysItems['UIDevice']
        
    device=sysData[M]['OD']['device']
    if (device=='LASER650'):
        a=sysData[M]['OD0']['LASERa']#Retrieve the calibration factors for OD.
        b=sysData[M]['OD0']['LASERb'] 
        if (ODActual<0):
            ODActual=0
            print(str(datetime.now()) + "You put a negative OD into calibration! Setting it to 0")
        
        raw=((ODActual/a +  (b/(2*a))**2)**0.5) - (b/(2*a)) #THis is performing the inverse function of the quadratic OD calibration.
        OD0=(10.0**raw)*ODRaw
        if (OD0<sysData[M][item]['min']):
            OD0=sysData[M][item]['min']
            print(str(datetime.now()) + 'OD calibration value seems too low?!')

        if (OD0>sysData[M][item]['max']):
            OD0=sysData[M][item]['max']
            print(str(datetime.now()) + 'OD calibration value seems too high?!')

    
        sysData[M][item]['target']=OD0
        print(str(datetime.now()) + "Calibrated OD")
    elif (device=='LEDF'):
        a=sysData[M]['OD0']['LEDFa']#Retrieve the calibration factors for OD.
        
        if (ODActual<0):
            ODActual=0
            print("You put a negative OD into calibration! Setting it to 0")
        if (M=='M0'):
            CF=1299.0
        elif (M=='M1'):
            CF=1206.0
        elif (M=='M2'):
            CF=1660.0
        elif (M=='M3'):
            CF=1494.0
            
        #raw=(ODActual)/a  #THis is performing the inverse function of the linear OD calibration.
        #OD0=ODRaw - raw*CF
        OD0=ODRaw/ODActual
        print(OD0)
    
        if (OD0<sysData[M][item]['min']):
            OD0=sysData[M][item]['min']
            print('OD calibration value seems too low?!')
        if (OD0>sysData[M][item]['max']):
            OD0=sysData[M][item]['max']
            print('OD calibration value seems too high?!')
    
        sysData[M][item]['target']=OD0
        print("Calibrated OD")
    elif (device=='LEDA'):
        a=sysData[M]['OD0']['LEDAa']#Retrieve the calibration factors for OD.
        
        if (ODActual<0):
            ODActual=0
            print("You put a negative OD into calibration! Setting it to 0")
        if (M=='M0'):
            CF=422
        elif (M=='M1'):
            CF=379
        elif (M=='M2'):
            CF=574
        elif (M=='M3'):
            CF=522
            
        #raw=(ODActual)/a  #THis is performing the inverse function of the linear OD calibration.
        #OD0=ODRaw - raw*CF
        OD0=ODRaw/ODActual
        print(OD0)
    
        if (OD0<sysData[M][item]['min']):
            OD0=sysData[M][item]['min']
            print('OD calibration value seems too low?!')
        if (OD0>sysData[M][item]['max']):
            OD0=sysData[M][item]['max']
            print('OD calibration value seems too high?!')
    
        sysData[M][item]['target']=OD0
        print("Calibrated OD")

    #Self-describe a mid-run re-blank/calibration -- a change to the OD zero shifts every
    #subsequent absolute OD, and was previously unlogged (no-op if no experiment is running).
    from chibio_control_helpers import logEvent
    logEvent(M, 'od_calibration', {'item': item, 'device': device,
                                   'target': sysData[M][item]['target'], 'raw': ODRaw, 'known_od': ODActual})
    return ('', 204)
    
    
        
@application.route("/MeasureOD/<M>",methods=['POST'])
def MeasureOD(M):
    from chibio_measurements import measure_od
    run_measurement(measure_od, M)  #dropped if one is already in flight on this reactor
    return ('', 204)


@application.route("/MeasureFP/<M>",methods=['POST'])
def MeasureFP(M):
    from chibio_measurements import measure_fp
    run_measurement(measure_fp, M)
    return ('', 204)




@application.route("/MeasureTemp/<which>/<M>",methods=['POST'])
def MeasureTemp(M,which):
    from chibio_measurements import measure_temp
    run_measurement(measure_temp, M, which)
    return ('', 204)
    


    
@application.route("/ExperimentReset",methods=['POST'])
def ExperimentReset():
    #Resets parameters/values of a given experiment.
    initialise(sysItems['UIDevice'])
    return ('', 204)

@application.route("/Experiment/<value>/<M>",methods=['POST'])
def ExperimentStartStop(M,value):
    #Stops or starts an experiment.
    global sysData
    global sysDevices
    global sysItems
    M=str(M)
    if (M=="0"):
        M=sysItems['UIDevice']

    value=int(value)
    #Turning it on involves keeping current pump directions,
    if (value and (sysData[M]['Experiment']['ON']==0)):

        sysData[M]['Experiment']['ON']=1
        addTerminal(M,'Experiment Started')

        if (sysData[M]['Experiment']['cycles']==0):
            now=datetime.now()
            timeString=now.strftime("%Y-%m-%d %H:%M:%S")
            sysData[M]['Experiment']['startTime']=timeString
            sysData[M]['Experiment']['startTimeRaw']=now
            # Write the self-describing metadata sidecar once, next to the CSV. Only on a
            # fresh start (cycles==0), not on resume — matches when a new CSV is created.
            from chibio_control_helpers import writeExperimentMetadata
            writeExperimentMetadata(M)

        sysData[M]['Pump1']['direction']=1.0 #Sets pumps to go forward.
        sysData[M]['Pump2']['direction']=1.0

        turnEverythingOff(M)

        set_output_on_sync(M,'Thermostat',1)
        if (sysData[M]['Experiment']['cycles']>0):
            # Resuming after a stalled/dead thread. turnEverythingOff above leaves the stirrer
            # off, and the loop only turns it on at the END of its first cycle -- so without
            # this the culture stays unstirred for a further cycle. Re-asserting Thermostat but
            # not Stir is exactly what made the manual 2026-08-11 recovery need a stir toggle.
            set_output_on_sync(M,'Stir',1)
        if sysDevices[M]['Experiment'].get('running', 0) == 0:
            sysDevices[M]['Experiment']['running']=1
            sysDevices[M]['Experiment']['thread']=Thread(target = runExperiment, args=(M,'placeholder'))
            sysDevices[M]['Experiment']['thread'].setDaemon(True)
            sysDevices[M]['Experiment']['thread'].start();

    else:
        sysData[M]['Experiment']['ON']=0
        sysData[M]['OD']['ON']=0
        addTerminal(M,'Experiment Stopping at end of cycle')
        set_output_on_sync(M,'Pump1',0)
        set_output_on_sync(M,'Pump2',0)
        set_output_on_sync(M,'Stir',0)
        set_output_on_sync(M,'Thermostat',0)

    return ('', 204)


# How many cycle-times of silence before an experiment thread counts as dead. Generous: a
# cycle that overruns is benign, a false restart costs a measurement.
_EXPERIMENT_STALL_CYCLES = 3.0
_EXPERIMENT_WATCHDOG_PERIOD = 20.0


def _restart_stalled_experiment(M, silent_for):
    # Only ever replace a thread that is GONE. A stalled thread is not necessarily a dead one
    # -- the leading suspect for these stalls is lock starvation, and a starved thread is very
    # much alive. `threadCount` supersession does not help here: it is only honoured when the
    # old loop next re-checks its while condition, so a thread blocked mid-cycle wakes up and
    # finishes that cycle regardless -- driving RegulateOD (pumps) and appending a CSV row
    # while the replacement does the same. Two dilution decisions per cycle on a live culture
    # is worse than the stall it was meant to fix.
    old = sysDevices[M]['Experiment'].get('thread')
    if old is not None and getattr(old, 'is_alive', lambda: False)():
        logger.error('Experiment on %s has not completed a cycle for %.0fs, but its thread is '
                     'still alive - refusing to start a second loop. It is blocked, not dead: '
                     'check the bus lock and the stall report.', M, silent_for)
        addTerminal(M, 'Experiment thread stalled (still alive) - see log')
        return
    logger.error('Experiment thread on %s died (no cycle for %.0fs) - restarting', M, silent_for)
    addTerminal(M, 'Experiment thread died - restarting')
    # The dead thread's `finally` normally clears this, but do not depend on it: if `running`
    # is left at 1, ExperimentStartStop would silently refuse to ever start a new loop.
    sysDevices[M]['Experiment']['running'] = 0
    # runExperiment turns the stirrer OFF to measure and only turns it back on at the end of
    # the cycle, so a thread that dies mid-measurement leaves the culture unstirred
    # indefinitely -- M3 sat that way for ~30 min. ExperimentStartStop re-asserts Thermostat
    # but never Stir, which is why the manual recovery needed an explicit stir toggle.
    try:
        set_output_on_sync(M, 'Stir', 1)
    except Exception:
        logger.exception('Could not re-assert stir on %s during restart', M)
    sysData[M]['Experiment']['lastCycleMonotonic'] = liveness_now()  # grace period before re-judging
    sysDevices[M]['Experiment']['running'] = 1
    sysDevices[M]['Experiment']['thread'] = Thread(target=runExperiment, args=(M, 'placeholder'))
    sysDevices[M]['Experiment']['thread'].setDaemon(True)
    sysDevices[M]['Experiment']['thread'].start()


def liveness_now():
    """The clock the liveness stamps are taken on.

    MUST be the same clock runExperiment stamps `lastCycleMonotonic` with. Keeping it in one
    named place is not ceremony: mixing time.time() here with time.monotonic() there yielded
    an age of 1,786,529,500 s (their offset), which flagged every reactor stalled forever.
    """
    return time.monotonic()


def stamp_cycle_complete(M):
    """Record that a cycle finished. The ONLY place a liveness stamp is written.

    Paired with classify_experiment_liveness(liveness_now()) so the stamp and the comparison
    cannot end up on different clocks -- which is exactly what went wrong once.
    """
    sysData[M]['Experiment']['lastCycleMonotonic'] = liveness_now()
    sysData[M]['Experiment']['stalled'] = 0


def classify_experiment_liveness(now):
    """Split the running reactors into (running, stalled) at `now`, a liveness_now() reading.

    Pure and side-effect free so the rule can be tested off-device; the caller owns the
    policy of what to do with the split.
    """
    running = []
    stalled = []
    for M in ['M0', 'M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7']:
        exp = sysData[M]['Experiment']
        if sysData[M]['present'] != 1 or exp['ON'] != 1 or exp['cycles'] < 1:
            continue
        last = exp.get('lastCycleMonotonic', 0.0)
        if not last:
            continue  # no completed cycle yet to measure silence from
        running.append(M)
        if (now - last) > max(60.0, exp['cycleTime']) * _EXPERIMENT_STALL_CYCLES:
            stalled.append(M)
    return running, stalled


def _experiment_watchdog():
    """Detect an experiment thread that died mid-run, and restart it.

    A dead thread is otherwise invisible. `OD['current']` holds its last computed value and
    reads as live, plausible, stable data with a low `od_spread` and `valid=1` -- on
    2026-08-11 a frozen 1.681 went on to drive a supervisor's dosing decisions for 90
    minutes (INVARIANTS 2). Cycles advancing is the only reliable liveness signal.

    Restarting is exactly the recovery the operator performed by hand: with cycles != 0 the
    loop resumes, `startTime` is preserved and it appends to the same CSV.

    Deliberately conservative. If EVERY running reactor is stalled at once, that is a bus- or
    worker-level fault rather than one dead thread, so it alerts and refuses to act -- the
    distinction INVARIANTS 5 demands after auto-recovery once restarted all five reactors
    into fresh, unblanked CSVs.
    """
    while True:
        time.sleep(_EXPERIMENT_WATCHDOG_PERIOD)
        try:
            now = liveness_now()
            running, stalled = classify_experiment_liveness(now)
            if not stalled:
                for M in running:
                    sysData[M]['Experiment']['stalled'] = 0
                continue
            for M in stalled:
                sysData[M]['Experiment']['stalled'] = 1
            # "Every reactor at once" means a bus- or worker-level fault, not a dead thread, and
            # auto-recovery once restarted all five into fresh unblanked CSVs by missing that
            # (INVARIANTS 5). Judge it by whether the THREADS died, not by counting stalls:
            # with a single reactor running, every stall is trivially "all of them", which
            # would silently disable recovery for the commonest bench configuration.
            dead = [M for M in stalled
                    if not getattr(sysDevices[M]['Experiment'].get('thread'), 'is_alive', lambda: False)()]
            if dead and len(dead) == len(running) and len(running) > 1:
                logger.error('ALL %d running reactors died at once (%s) - not one dead thread. '
                             'Refusing to auto-restart; check the bus and restore the blanks.',
                             len(dead), ','.join(dead))
                continue
            for M in stalled:
                _restart_stalled_experiment(M, now - sysData[M]['Experiment']['lastCycleMonotonic'])
        except Exception:
            logger.exception('Experiment watchdog iteration failed')


def start_experiment_watchdog():
    watcher = Thread(target=_experiment_watchdog)
    watcher.setDaemon(True)
    watcher.start()
    return watcher


def _boot():
    # Three ways in. CHIBIO_SIM: patch the bus + optics, then run the REAL
    # initialiseAll() on top of the fake hardware (see chibio_sim). CHIBIO_MOCK_HW
    # alone: skip initialisation entirely, it is only an import shim for the tests.
    # Neither (the device default): real hardware.
    if chibio_sim.SIM:
        chibio_sim.install()
    elif not MOCK_HW:
        initialiseAll()
    if chibio_sim.SIM or not MOCK_HW:
        # Catches the next unexplained worker kill in the act (see TODO.md): reports every
        # thread's stack if this loop ever loses the CPU for 30 s. Not started under the bare
        # import shim, which runs no threads for it to report on.
        start_stall_watchdog()
        start_experiment_watchdog()


if __name__ == '__main__':
    _boot()
    application.run(debug=True,threaded=True,host='0.0.0.0',port=5000)
else:
    _boot()

print(str(datetime.now()) + ' Start Up Complete')
