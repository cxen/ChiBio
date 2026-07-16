import csv
import math
import os
import time
import io
import sys
from datetime import datetime
from threading import Thread

import numpy as np

from chibio_state import lock, sysData, sysItems


def CustomProgram(M):
    #Runs a custom program, some examples are included. You can remove/edit this function as you see fit.
    #Note that the custom programs (as set up at present) use an external .csv file with input parameters. THis is done to allow these parameters to easily be varied on the fly.
    from app import set_output_on_sync, set_output_target_sync, addTerminal

    M=str(M)
    program=sysData[M]['Custom']['Program']
    #Subsequent few lines reads in external parameters from a file if you are using any.
    fname='InputParameters_' + str(M)+'.csv'

    if sys.version_info[0] < 3:
        params_handle = open(fname, 'rb')
    else:
        params_handle = io.open(fname, 'r', newline='')

    with params_handle as f:
        reader = csv.reader(f)
        listin = list(reader)
    Params=listin[0]
    addTerminal(M,'Running Program = ' + str(program) + ' on device ' + str(M))

    if (program=="C1"): #Optogenetic Integral Control Program
        integral=0.0 #Integral in integral controller
        green=0.0 #Intensity of Green actuation
        red=0.0 #Intensity of red actuation.
        GFPNow=sysData[M]['FP1']['Emit1']
        GFPTarget=sysData[M]['Custom']['Status'] #This is the controller setpoint.
        error=GFPTarget-GFPNow
        if error>0.0075:
            green=1.0
            red=0.0
            sysData[M]['Custom']['param3']=0.0
        elif error<-0.0075:
            green=0.0
            red=1.0
            sysData[M]['Custom']['param3']=0.0
        else:
            red=1.0
            balance=float(Params[0]) #our guess at green light level to get 50% expression.
            KI=float(Params[1])
            KP=float(Params[2])
            integral=sysData[M]['Custom']['param3']+error*KI
            green=balance+KP*error+integral
            sysData[M]['Custom']['param3']=integral

        GreenThread=Thread(target = CustomLEDCycle, args=(M,'LEDD',green))
        GreenThread.setDaemon(True)
        GreenThread.start();
        RedThread=Thread(target = CustomLEDCycle, args=(M,'LEDF',red))
        RedThread.setDaemon(True)
        RedThread.start();
        sysData[M]['Custom']['param1']=green
        sysData[M]['Custom']['param2']=red
        addTerminal(M,'Program = ' + str(program) + ' green= ' + str(green)+ ' red= ' + str(red) + ' integral= ' + str(integral))

    elif (program=="C2"): #UV Integral Control Program
        integral=0.0 #Integral in integral controller
        UV=0.0 #Intensity of Green actuation
        GrowthRate=sysData[M]['GrowthRate']['current']
        GrowthTarget=sysData[M]['Custom']['Status'] #This is the controller setpoint.
        error=GrowthTarget-GrowthRate
        KP=float(Params[0]) #Past data suggest value of ~0.005
        KI=float(Params[1]) #Past data suggest value of ~2e-5
        integral=sysData[M]['Custom']['param2']+error*KI
        if(integral>0):
            integral=0.0
        sysData[M]['Custom']['param2']=integral
        UV=-1.0*(KP*error+integral)
        sysData[M]['Custom']['param1']=UV
        set_output_target_sync(M,'UV',UV)
        set_output_on_sync(M,'UV',1)
        addTerminal(M,'Program = ' + str(program) + ' UV= ' + str(UV)+  ' integral= ' + str(integral))

    elif (program=="C3"): #UV Integral Control Program Mk 2
        integral=sysData[M]['Custom']['param2'] #Integral in integral controller
        integral2=sysData[M]['Custom']['param3'] #Second integral controller
        UV=0.0 #Intensity of UV
        GrowthRate=sysData[M]['GrowthRate']['current']
        GrowthTarget=sysData[M]['Custom']['Status'] #This is the controller setpoint.
        error=GrowthTarget-GrowthRate
        KP=float(Params[0]) #Past data suggest value of ~0.005
        KI=float(Params[1]) #Past data suggest value of ~2e-5
        KI2=float(Params[2])
        integral=sysData[M]['Custom']['param2']+error*KI
        if(integral>0):
            integral=0.0

        if(abs(error)<0.3): #This is a second high-gain integrator which only gets cranking along when we are close to the target.
            integral2=sysData[M]['Custom']['param3']+error*KI2
        if(integral2>0):
            integral2=0.0

        sysData[M]['Custom']['param2']=integral
        sysData[M]['Custom']['param3']=integral2
        UV=-1.0*(KP*error+integral+integral2)
        m=50.0
        UV=(1.0/m)*(math.exp(m*UV)-1.0) #Basically this is to force the UV level to increase exponentially!
        sysData[M]['Custom']['param1']=UV
        set_output_target_sync(M,'UV',UV)
        set_output_on_sync(M,'UV',1)
        addTerminal(M,'Program = ' + str(program) + ' UV= ' + str(UV)+  ' integral= ' + str(integral))
    elif (program=="C4"): #UV Integral Control Program Mk 4
        rategain=float(Params[0])
        timept=sysData[M]['Custom']['Status'] #This is the timestep as we follow in minutes

        UV=0.001*math.exp(timept*rategain) #So we just exponentialy increase UV over time!
        sysData[M]['Custom']['param1']=UV
        set_output_target_sync(M,'UV',UV)
        set_output_on_sync(M,'UV',1)

        timept=timept+1
        sysData[M]['Custom']['Status']=timept

    elif (program=="C5"): #UV Dosing program
        timept=int(sysData[M]['Custom']['Status']) #This is the timestep as we follow in minutes
        sysData[M]['Custom']['Status']=timept+1 #Increment time as we have entered the loop another time!

        Pump2Ontime=sysData[M]['Experiment']['cycleTime']*1.05*abs(sysData[M]['Pump2']['target'])*sysData[M]['Pump2']['ON']+0.5 #The amount of time Pump2 is going to be on for following RegulateOD above.
        time.sleep(Pump2Ontime) #Pause here is to prevent output pumping happening at the same time as stirring.

        timelength=300 #Time between doses in minutes
        if(timept%timelength==2): #So this happens every 5 hours!
            iters=(timept//timelength)
            Dose0=float(Params[0])
            Dose=Dose0*(2.0**float(iters)) #UV Dose, in terms of amount of time UV shoudl be left on at 1.0 intensity.
            print(str(datetime.now()) + ' Gave dose ' + str(Dose) + " at iteration " + str(iters) + " on device " + str(M))

            if (Dose<30.0):
                powerlvl=Dose/30.0
                set_output_target_sync(M,'UV',powerlvl)
                Dose=30.0
            else:
                set_output_target_sync(M,'UV',1.0) #Ensure UV is on at aopropriate intensity

            set_output_on_sync(M,'UV',1) #Activate UV
            time.sleep(Dose) #Wait for dose to be administered
            set_output_on_sync(M,'UV',0) #Deactivate UV

    elif (program=="C6"): #UV Dosing program 2 - constant value!
        timept=int(sysData[M]['Custom']['Status']) #This is the timestep as we follow in minutes
        sysData[M]['Custom']['Status']=timept+1 #Increment time as we have entered the loop another time!

        Pump2Ontime=sysData[M]['Experiment']['cycleTime']*1.05*abs(sysData[M]['Pump2']['target'])*sysData[M]['Pump2']['ON']+0.5 #The amount of time Pump2 is going to be on for following RegulateOD above.
        time.sleep(Pump2Ontime) #Pause here is to prevent output pumping happening at the same time as stirring.

        timelength=300 #Time between doses in minutes
        if(timept%timelength==2): #So this happens every 5 hours!
            iters=(timept//timelength)
            if iters>3:
                iters=3

            Dose0=float(Params[0])
            Dose=Dose0*(2.0**float(iters)) #UV Dose, in terms of amount of time UV shoudl be left on at 1.0 intensity.
            print(str(datetime.now()) + ' Gave dose ' + str(Dose) + " at iteration " + str(iters) + " on device " + str(M))

            if (Dose<30.0):
                powerlvl=Dose/30.0
                set_output_target_sync(M,'UV',powerlvl)
                Dose=30.0
            else:
                set_output_target_sync(M,'UV',1.0) #Ensure UV is on at aopropriate intensity

            set_output_on_sync(M,'UV',1) #Activate UV
            time.sleep(Dose) #Wait for dose to be administered
            set_output_on_sync(M,'UV',0) #Deactivate UV

    return


def CustomLEDCycle(M,LED,Value):
    #This function cycles LEDs for a fraction of 30 seconds during an experiment.
    from app import set_output_on_sync

    M=str(M)
    if (Value>1.0):
        Value=1.0

    if (Value>0.0):
        set_output_on_sync(M,LED,1)
        time.sleep(Value*30.0)#Sleep whatever fraction of 30 seconds we are interested in
        set_output_on_sync(M,LED,0)

    return


def LightActuation(M,toggle):
    #Another optogenetic function, turning LEDs on/off during experiment as appropriate.
    from app import set_output_on_sync

    M=str(M)
    toggle=int(toggle)
    LEDChoice=sysData[M]['Light']['Excite']
    if (toggle==1 and sysData[M]['Light']['ON']==1):
        set_output_on_sync(M,LEDChoice,1)
    else:
        set_output_on_sync(M,LEDChoice,0)
    return 0


# Maps each recorded LED to its CSV column name. The column names encode the
# LED's wavelength/type; the sysData keys (LEDA..LASER650) are hardware channels.
_CSV_LED_COLUMNS = [
    ('LEDA', 'LED_395nm_setpoint'), ('LEDB', 'LED_457nm_setpoint'),
    ('LEDC', 'LED_500nm_setpoint'), ('LEDD', 'LED_523nm_setpoint'),
    ('LEDE', 'LED_595nm_setpoint'), ('LEDF', 'LED_623nm_setpoint'),
    ('LEDG', 'LED_6500K_setpoint'), ('LEDH', 'LED_600nm_setpoint'),
    ('LEDI', 'LED_550nm_setpoint'), ('LEDV', 'LED_White_setpoint'),
    ('LASER650', 'laser_setpoint'),
]


def csvData(M):
    #Used to format current data and write a new row to CSV file output. To record an
    #extra measurement, add ONE `data[...] =` line below: DictWriter keys the value to
    #its column by name, so header and row can no longer drift out of sync (the old
    #parallel fieldnames/row lists could, which silently dropped the header).
    M=str(M)

    data = {
        'exp_time': sysData[M]['time']['record'][-1],
        'od_measured': sysData[M]['OD']['record'][-1],
        'od_setpoint': sysData[M]['OD']['targetrecord'][-1],
        'od_zero_setpoint': sysData[M]['OD0']['target'],
        'thermostat_setpoint': sysData[M]['Thermostat']['record'][-1],
        'heating_rate': sysData[M]['Heat']['target']*float(sysData[M]['Heat']['ON']),
        'internal_air_temp': sysData[M]['ThermometerInternal']['record'][-1],
        'external_air_temp': sysData[M]['ThermometerExternal']['record'][-1],
        'media_temp': sysData[M]['ThermometerIR']['record'][-1],
        'opt_gen_act_int': sysData[M]['Light']['record'][-1],
        'pump_1_rate': sysData[M]['Pump1']['record'][-1],
        'pump_2_rate': sysData[M]['Pump2']['record'][-1],
        'pump_3_rate': sysData[M]['Pump3']['record'][-1],
        'pump_4_rate': sysData[M]['Pump4']['record'][-1],
        'media_vol': sysData[M]['Volume']['target'],
        'stirring_rate': sysData[M]['Stir']['target']*sysData[M]['Stir']['ON'],
    }
    for LED, col in _CSV_LED_COLUMNS:
        data[col] = sysData[M][LED]['target']
    data['LED_UV_int'] = sysData[M]['UV']['target']*sysData[M]['UV']['ON']
    for FP in ['FP1','FP2','FP3']:
        on = sysData[M][FP]['ON']==1
        data[FP+'_base']  = sysData[M][FP]['Base']  if on else 0.0
        data[FP+'_emit1'] = sysData[M][FP]['Emit1'] if on else 0.0
        data[FP+'_emit2'] = sysData[M][FP]['Emit2'] if on else 0.0
    data['custom_prog_param1'] = sysData[M]['Custom']['param1']*float(sysData[M]['Custom']['ON'])
    data['custom_prog_param2'] = sysData[M]['Custom']['param2']*float(sysData[M]['Custom']['ON'])
    data['custom_prog_param3'] = sysData[M]['Custom']['param3']*float(sysData[M]['Custom']['ON'])
    data['custom_prog_status'] = sysData[M]['Custom']['Status']*float(sysData[M]['Custom']['ON'])
    data['zigzag_target'] = sysData[M]['Zigzag']['target']*float(sysData[M]['Zigzag']['ON'])
    data['growth_rate'] = sysData[M]['GrowthRate']['current']*sysData[M]['Zigzag']['ON']

    #Following can be uncommented if you are recording ALL spectra for e.g. biofilm experiments
    #bands=['nm410' ,'nm440','nm470','nm510','nm550','nm583','nm620','nm670','CLEAR','NIR']
    #items= ['LEDA','LEDB','LEDC','LEDD','LEDE','LEDF','LEDG','LASER650']
    #for item in items:
    #   for band in bands:
    #       data[item+'_'+band] = sysData[M]['biofilm'][item][band]

    filename = sysData[M]['Experiment']['startTime'] + '_' + M + '_data' + '.csv'
    filename=filename.replace(":","_")

    def open_csv_append(path):
        if sys.version_info[0] < 3:
            return open(path, 'ab')
        return io.open(path, 'a', newline='')

    lock.acquire() #We are avoiding writing to a file at the same time as we do digital communications, since it might potentially cause the computer to lag and consequently data transfer to fail.
    try:
        new_file = os.path.isfile(filename) is False #Only write the header when starting a fresh file.
        with open_csv_append(filename) as csvFile:
            writer = csv.DictWriter(csvFile, fieldnames=list(data.keys()))
            if new_file:
                writer.writeheader()
            writer.writerow(data)
    finally:
        lock.release()


def downsample(M):
    #In order to prevent the UI getting too laggy, we downsample the stored data every few hours. Note that this doesnt downsample that which has already been written to CSV, so no data is ever lost.
    M=str(M)

    #We now generate a new time vector which is downsampled at half the rate of the previous one
    time=np.asarray(sysData[M]['time']['record'])
    newlength=int(round(len(time)/2,2)-1)
    tnew=np.linspace(time[0],time[-11],newlength)
    tnew=np.concatenate([tnew,time[-10:]])

    #In the following we make a new array, index, which has the indices at which we want to resample our existing data vectors.
    i=0
    index=np.zeros((len(tnew),),dtype=int)
    for timeval in tnew:
        idx = np.searchsorted(time, timeval, side="left")
        if idx > 0 and (idx == len(time) or np.abs(timeval - time[idx-1]) < np.abs(timeval - time[idx])):
            index[i]=idx-1
        else:
            index[i]=idx
        i=i+1

    sysData[M]['time']['record']=downsampleFunc(sysData[M]['time']['record'],index)
    sysData[M]['OD']['record']=downsampleFunc(sysData[M]['OD']['record'],index)
    sysData[M]['OD']['targetrecord']=downsampleFunc(sysData[M]['OD']['targetrecord'],index)
    sysData[M]['Thermostat']['record']=downsampleFunc(sysData[M]['Thermostat']['record'],index)
    sysData[M]['Light']['record']=downsampleFunc(sysData[M]['Light']['record'],index)
    sysData[M]['ThermometerInternal']['record']=downsampleFunc(sysData[M]['ThermometerInternal']['record'],index)
    sysData[M]['ThermometerExternal']['record']=downsampleFunc(sysData[M]['ThermometerExternal']['record'],index)
    sysData[M]['ThermometerIR']['record']=downsampleFunc(sysData[M]['ThermometerIR']['record'],index)
    sysData[M]['Pump1']['record']=downsampleFunc(sysData[M]['Pump1']['record'],index)
    sysData[M]['Pump2']['record']=downsampleFunc(sysData[M]['Pump2']['record'],index)
    sysData[M]['Pump3']['record']=downsampleFunc(sysData[M]['Pump3']['record'],index)
    sysData[M]['Pump4']['record']=downsampleFunc(sysData[M]['Pump4']['record'],index)
    sysData[M]['GrowthRate']['record']=downsampleFunc(sysData[M]['GrowthRate']['record'],index)

    for FP in ['FP1','FP2','FP3']:
        sysData[M][FP]['BaseRecord']=downsampleFunc(sysData[M][FP]['BaseRecord'],index)
        sysData[M][FP]['Emit1Record']=downsampleFunc(sysData[M][FP]['Emit1Record'],index)
        sysData[M][FP]['Emit2Record']=downsampleFunc(sysData[M][FP]['Emit2Record'],index)


def downsampleFunc(datain,index):
    #This function Is used to downsample the arrays, taking the points selected by the index vector.
    datain=list(datain)
    newdata=[]
    newdata=np.zeros((len(index),),dtype=float)

    i=0
    for loc in list(index):
        newdata[i]=datain[int(loc)]

        i=i+1
    return list(newdata)
