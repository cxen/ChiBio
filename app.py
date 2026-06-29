######### Chi.Bio Operating System V1.0 #########

#Import required python packages
import os
import random
import time
import math
import logging
from flask import Flask, render_template, jsonify
from chibio_auth import init_auth
from chibio_experiment import PumpModulation, RegulateOD, Thermostat, Zigzag, runExperiment
from chibio_hardware import I2CCom, setPWM, setup_watchdog
from chibio_optics import get_light, get_spectrum
from chibio_state import sysData, sysDevices, sysItems
from threading import Thread
import threading
from datetime import datetime, date
import Adafruit_GPIO.I2C as I2C
import time
import serial
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
setup_watchdog()


@application.after_request
def add_no_cache_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


def run_background(target, *args, **kwargs):
    def wrapper():
        try:
            target(*args, **kwargs)
        except Exception:
            logger.exception(
                'Background task failed: %s',
                getattr(target, '__name__', 'task')
            )

    thread = Thread(target=wrapper)
    thread.setDaemon(True)
    thread.start()
    return thread


def resolve_device_id(M):
    M = str(M)
    if (M == "0"):
        return sysItems['UIDevice']
    return M


def get_device_item(M, item):
    if M not in sysData:
        return None, jsonify({'error': 'Unknown device'}), 404
    if item not in sysData[M]:
        return None, jsonify({'error': 'Unknown item'}), 404
    return sysData[M][item], None, None
   


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
    sysData[M]['OD']['device']='LASER650'

    sysData[M]['Volume']['target']=20.0

    clearTerminal(M)
    addTerminal(M,'System Initialised')

    sysData[M]['Experiment']['ON']=0
    sysData[M]['Experiment']['cycles']=0
    sysData[M]['Experiment']['threadCount']=0
    sysData[M]['Experiment']['startTime']=' Waiting '
    sysData[M]['Experiment']['startTimeRaw']=0
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

    sysData[M]['ThermometerInternal']['current']=0.0
    sysData[M]['ThermometerExternal']['current']=0.0
    sysData[M]['ThermometerIR']['current']=0.0

    sysData[M]['time']['record']=[]
    sysData[M]['OD']['record']=[]
    sysData[M]['OD']['targetrecord']=[]
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

    sysDevices[M]['ThermometerInternal']['device']=I2C.get_i2c_device(0x18,2) #Get Thermometer on Bus 2!!!
    sysDevices[M]['ThermometerExternal']['device']=I2C.get_i2c_device(0x1b,2) #Get Thermometer on Bus 2!!!
    sysDevices[M]['DAC']['device']=I2C.get_i2c_device(0x48,2) #Get DAC on Bus 2!!!
    sysDevices[M]['AS7341']['device']=I2C.get_i2c_device(0x39,2) #Get OD Chip on Bus 2!!!!!
    sysDevices[M]['Pumps']['device']=I2C.get_i2c_device(0x61,2) #Get OD Chip on Bus 2!!!!!
    sysDevices[M]['Pumps']['startup']=0
    sysDevices[M]['Pumps']['frequency']=0x1e #200Hz PWM frequency
    sysDevices[M]['PWM']['device']=I2C.get_i2c_device(0x60,2) #Get OD Chip on Bus 2!!!!!
    sysDevices[M]['PWM']['startup']=0
    sysDevices[M]['PWM']['frequency']=0x03 #1526 Hz PWM frequency for fan/LEDs, maximum possible.
    sysDevices[M]['ThermometerIR']['device']=smbus.SMBus(bus=2) #Set up SMBus thermometer
    sysDevices[M]['ThermometerIR']['address']=0x5a

    scan_devices_sync(M)
    if(sysData[M]['present']==1):
        turnEverythingOff(M)

        V1_Present=0
        V2_Present=0
        # Now we will detect LED version First checking for version 2
        out=get_light(M,['nm583'],10,10) #Measure with maximum gain (10) and for short period.
        Baseline=out[0]
        set_output_on_sync(M,'LEDH',1) #Turn on LEDH at default level - should only be present in version 2
        out=get_light(M,['nm583'],10,10)
        NewLevel=out[0]
        set_output_on_sync(M,'LEDH',0) #Turn off LEDH at default level - should only be present in version 2
        if (NewLevel>Baseline*3+20):
            V2_Present = 1

        # Now we will detect for Version 1
        out=get_light(M,['nm583'],10,10) #Measure with maximum gain (10) and for short period.
        Baseline=out[0]
        set_output_on_sync(M,'LEDG',1) #Turn on LEDG at default level - should only be present in version 1
        out=get_light(M,['nm583'],10,10)
        NewLevel=out[0]
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

        print(str(datetime.now()) + " Initialised " + str(M) +', LED Version: ' + str(sysData[M]['Version']['LED']) + ', Device ID: ' + sysData[M]['DeviceID'])


def initialiseAll():
    # Initialisation function which runs at when software is started for the first time.
    sysItems['Multiplexer']['device']=I2C.get_i2c_device(0x74,2)
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

    if sysData[M][FP]['ON']==1:
        sysData[M][FP]['ON']=0
        return ('', 204)
    else:
        sysData[M][FP]['ON']=1
        sysData[M][FP]['LED']=Excite
        sysData[M][FP]['BaseBand']=Base
        sysData[M][FP]['Emit1Band']=Emit1
        sysData[M][FP]['Emit2Band']=Emit2
        sysData[M][FP]['Gain']=Gain
        return ('', 204)


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
    if (Program=='C1'):
        cthread=Thread(target = CharacteriseDevice2, args=(M))
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
    gi=-1
    for item in items:
        gi=gi+1
        for power in powerlevels:
            set_output_target_sync(M,item,power)
            set_output_on_sync(M,item,1)
            get_spectrum(M,gains[gi])
            set_output_on_sync(M,item,0)
            print(item + ' ' + str(power))
            for band in bands:
                result[item][band].append(int(sysData[M]['AS7341']['spectrum'][band]))
            addTerminal(M,'Measured Item = ' + str(item) + ' at power ' + str(power))
            time.sleep(0.05)
                
    
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
        
    return ('', 204)    
    
    
        
@application.route("/MeasureOD/<M>",methods=['POST'])
def MeasureOD(M):
    from chibio_measurements import measure_od
    run_background(measure_od, M)
    return ('', 204)  
    

@application.route("/MeasureFP/<M>",methods=['POST'])    
def MeasureFP(M):
    from chibio_measurements import measure_fp
    run_background(measure_fp, M)
    return ('', 204)      
    

    
    
@application.route("/MeasureTemp/<which>/<M>",methods=['POST'])
def MeasureTemp(M,which): 
    from chibio_measurements import measure_temp
    run_background(measure_temp, M, which)
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

        sysData[M]['Pump1']['direction']=1.0 #Sets pumps to go forward.
        sysData[M]['Pump2']['direction']=1.0

        turnEverythingOff(M)

        set_output_on_sync(M,'Thermostat',1)
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


if __name__ == '__main__':
    initialiseAll()
    application.run(debug=True,threaded=True,host='0.0.0.0',port=5000)
else:
    initialiseAll()

print(str(datetime.now()) + ' Start Up Complete')
