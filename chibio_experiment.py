import math
import logging
import time
from datetime import datetime
from threading import Thread

import simplejson

from chibio_hardware import setPWM
from chibio_state import sysData, sysDevices, sysItems

logger = logging.getLogger('chibio')


def PumpModulation(M, item):
    #Responsible for turning pumps on/off with an appropriate duty cycle. They are turned on for a fraction of each ~1minute cycle to achieve low pump rates.
    sysDevices[M][item]['threadCount']=(sysDevices[M][item]['threadCount']+1)%100 #Index of the particular thread running.
    currentThread=sysDevices[M][item]['threadCount']
    try:
        while (sysData[M][item]['ON']==1 and sysDevices[M][item]['threadCount']==currentThread):
            while (sysDevices[M][item]['active']==1): #Idea is we will wait here if a previous thread on this pump is already running. Potentially all this 'active' business could be removed from this fuction.
                time.sleep(0.02)

            if (abs(sysData[M][item]['target']*sysData[M][item]['ON'])!=1 and currentThread==sysDevices[M][item]['threadCount']): #In all cases we turn things off to begin
                sysDevices[M][item]['active']=1
                setPWM(M,'Pumps',sysItems[item]['In1'],0.0*float(sysData[M][item]['ON']),0)
                setPWM(M,'Pumps',sysItems[item]['In2'],0.0*float(sysData[M][item]['ON']),0)
                setPWM(M,'Pumps',sysItems[item]['In1'],0.0*float(sysData[M][item]['ON']),0)
                setPWM(M,'Pumps',sysItems[item]['In2'],0.0*float(sysData[M][item]['ON']),0)
                sysDevices[M][item]['active']=0
            if (sysData[M][item]['ON']==0):
                break

            Time1=datetime.now()
            cycletime=sysData[M]['Experiment']['cycleTime']*1.05 #We make this marginally longer than the experiment cycle time to avoid too much chaos when you come back around to pumping again.

            Ontime=cycletime*abs(sysData[M][item]['target'])

            # Decided to remove the below section in order to prevent media buildup in the device if you are pumping in very rapidly. This check means that media is removed, then added. Removing this code means these happen simultaneously.
            #if (item=="Pump1" and abs(sysData[M][item]['target'])<0.3): #Ensuring we run Pump1 after Pump2.
            #    waittime=cycletime*abs(sysData[M]['Pump2']['target']) #We want to wait until the output pump has stopped, otherwise you are very inefficient with your media since it will be pumping out the fresh media fromthe top of the test tube right when it enters.
            #    time.sleep(waittime+1.0)

            if (sysData[M][item]['target']>0 and currentThread==sysDevices[M][item]['threadCount']): #Turning on pumps in forward direction
                sysDevices[M][item]['active']=1
                setPWM(M,'Pumps',sysItems[item]['In1'],1.0*float(sysData[M][item]['ON']),0)
                setPWM(M,'Pumps',sysItems[item]['In2'],0.0*float(sysData[M][item]['ON']),0)
                sysDevices[M][item]['active']=0
            elif (sysData[M][item]['target']<0 and currentThread==sysDevices[M][item]['threadCount']): #Or backward direction.
                sysDevices[M][item]['active']=1
                setPWM(M,'Pumps',sysItems[item]['In1'],0.0*float(sysData[M][item]['ON']),0)
                setPWM(M,'Pumps',sysItems[item]['In2'],1.0*float(sysData[M][item]['ON']),0)
                sysDevices[M][item]['active']=0

            time.sleep(Ontime)

            if(abs(sysData[M][item]['target'])!=1 and currentThread==sysDevices[M][item]['threadCount']): #Turning off pumps at appropriate time.
                sysDevices[M][item]['active']=1
                setPWM(M,'Pumps',sysItems[item]['In1'],0.0*float(sysData[M][item]['ON']),0)
                setPWM(M,'Pumps',sysItems[item]['In2'],0.0*float(sysData[M][item]['ON']),0)
                setPWM(M,'Pumps',sysItems[item]['In1'],0.0*float(sysData[M][item]['ON']),0)
                setPWM(M,'Pumps',sysItems[item]['In2'],0.0*float(sysData[M][item]['ON']),0)
                sysDevices[M][item]['active']=0

            Time2=datetime.now()
            elapsedTime=Time2-Time1
            elapsedTimeSeconds=round(elapsedTime.total_seconds(),2)
            Offtime=cycletime-elapsedTimeSeconds
            if (Offtime>0.0):
                time.sleep(Offtime)
    finally:
        sysDevices[M][item]['running']=0
        if (sysData[M][item]['ON']==0):
            sysDevices[M][item]['active']=0
            setPWM(M,'Pumps',sysItems[item]['In1'],0.0,0)
            setPWM(M,'Pumps',sysItems[item]['In2'],0.0,0)


def Thermostat(M, item):
    #Function that implements thermostat temperature control using MPC algorithm.
    from app import SetOutput
    from chibio_measurements import measure_temp

    sysDevices[M][item]['threadCount']=(sysDevices[M][item]['threadCount']+1)%100
    currentThread=sysDevices[M][item]['threadCount']
    try:
        while (sysData[M][item]['ON']==1 and sysDevices[M][item]['threadCount']==currentThread):
            measure_temp(M,'IR') #Measures temperature - note that this may be happening DURING stirring.

            CurrentTemp=sysData[M]['ThermometerIR']['current']
            TargetTemp=sysData[M]['Thermostat']['target']
            LastTemp=sysData[M]['Thermostat']['last']

            #MPC Controller Component
            MediaTemp=sysData[M]['ThermometerExternal']['current']
            MPC=0
            if (MediaTemp>0.0):
                Tdiff=CurrentTemp-MediaTemp
                Pumping=sysData[M]['Pump1']['target']*float(sysData[M]['Pump1']['ON'])*float(sysData[M]['OD']['ON'])
                Gain=2.5
                MPC=Gain*Tdiff*Pumping

            #PI Controller Component
            e=TargetTemp-CurrentTemp
            dt=sysData[M]['Thermostat']['cycleTime']
            I=sysData[M]['Thermostat']['Integral']
            if (abs(e)<2.0):
                I=I+0.0005*dt*e
                P=0.25*e
            else:
                P=0.5*e;

            if (abs(TargetTemp-LastTemp)>2.0): #This resets integrator if we make a big jump in set point.
                I=0.0
            elif(I<0.0):
                I=0.0
            elif (I>1.0):
                I=1.0

            sysData[M]['Thermostat']['Integral']=I

            U=P+I+MPC

            if(U>1.0):
                U=1.0
                sysData[M]['Heat']['target']=U
                sysData[M]['Heat']['ON']=1
            elif(U<0):
                U=0
                sysData[M]['Heat']['target']=U
                sysData[M]['Heat']['ON']=0
            else:
                sysData[M]['Heat']['target']=U
                sysData[M]['Heat']['ON']=1

            sysData[M]['Thermostat']['last']=sysData[M]['Thermostat']['target']

            SetOutput(M,'Heat')

            time.sleep(dt)
    finally:
        sysData[M]['Heat']['ON']=0
        sysData[M]['Heat']['target']=0
        SetOutput(M,'Heat')
        sysDevices[M][item]['running']=0


def RegulateOD(M):
    #Function responsible for turbidostat functionality (OD control)
    from app import set_output_on_sync, addTerminal

    M=str(M)

    if (sysData[M]['Zigzag']['ON']==1):
        TargetOD=sysData[M]['OD']['target']
        Zigzag(M) #Function that calculates new target pump rates, and sets pumps to desired rates.

    Pump1Current=abs(sysData[M]['Pump1']['target'])
    Pump2Current=abs(sysData[M]['Pump2']['target'])
    Pump1Direction=sysData[M]['Pump1']['direction']
    Pump2Direction=sysData[M]['Pump2']['direction']

    ODNow=sysData[M]['OD']['current']
    ODTarget=sysData[M]['OD']['target']
    if (ODTarget<=0): #There could be an error on the log operationif ODTarget is 0!
        ODTarget=0.000001

    errorTerm=ODTarget-ODNow
    Volume=sysData[M]['Volume']['target']

    PercentPerMin=4*60/Volume #Gain parameter to convert from pump rate to rate of OD reduction.

    if sysData[M]['Experiment']['cycles']<3:
        Pump1=0 #In first few cycles we do precisely no pumping.
    elif len(sysData[M]['time']['record']) < 2:
        Pump1=0 #In first few cycles we do precisely no pumping.
        addTerminal(M, "Warning: Tried to calculate time elapsed with fewer than two " +\
                        "timepoints recorded. If you see this message a lot, there may be " +\
                        "a more serious problem.")
    else:
        ODPast=sysData[M]['OD']['record'][-1]
        timeElapsed=((sysData[M]['time']['record'][-1])-(sysData[M]['time']['record'][-2]))/60.0 #Amount of time betwix measurements in minutes
        if (ODNow>0):
            try:
                NewGrowth = math.log((ODTarget)/(ODNow))/timeElapsed
            except Exception:
                NewGrowth=0.0
                logger.exception('OD growth rate calculation failed on %s', M)
        else:
            NewGrowth=0.0

        Pump1=-1.0*NewGrowth/PercentPerMin

        #Next Section is Integral Control
        ODerror=ODNow-ODTarget
        # Integrator 1 - resoponsible for short-term integration to overcome troubles if an input pump makes a poor seal.
        ODIntegral=sysData[M]['OD']['Integral']
        if ODerror<0.01:
            ODIntegral=0
        elif (abs(ODNow-ODPast)<0.05 and ODerror>0.025): #preventing massive accidental jumps causing trouble with this integral term.
            ODIntegral=ODIntegral+0.1*ODerror
        sysData[M]['OD']['Integral']=ODIntegral
        # Integrator 2
        ODIntegral2=sysData[M]['OD']['Integral2']
        if (abs(ODerror)>0.1 and abs(ODNow-ODPast)<0.05):
            ODIntegral2=0
        elif (abs(ODNow-ODPast)<0.1):
            ODIntegral2=ODIntegral2+0.01*ODerror
            Pump1=Pump1*0.7 #This is essentially enforcing a smaller Proportional gain when we are near to OD setpoint.
        sysData[M]['OD']['Integral2']=ODIntegral2

        Pump1=Pump1+ODIntegral+ODIntegral2

        if (ODNow-ODPast)>0.04: #This is to counteract noisy jumps in OD measurements from causing mayhem in the regulation algorithm.
            Pump1=0.0

    #Make sure values are in appropriate range. We want to limit the maximum size of pump1 to prevent it from overflowing.
    if(Pump1>0.02):
        Pump1=0.02
    elif(Pump1<0):
        Pump1=0.0

    if(sysData[M]['Chemostat']['ON']==1):
        Pump1=float(sysData[M]['Chemostat']['p1'])

    #Set new Pump targets
    sysData[M]['Pump1']['target']=Pump1*Pump1Direction
    sysData[M]['Pump2']['target']=(Pump1*4+0.07)*Pump2Direction

    if(sysData[M]['Experiment']['cycles']%5==1): #Every so often we do a big output pump to make sure tubes are clear.
        sysData[M]['Pump2']['target']=0.25*sysData[M]['Pump2']['direction']

    if (sysData[M]['Experiment']['cycles']>15):
        #This section is to check if we have added any liquid recently, if not, then we dont run pump 2 since it won't be needed.
        pastpumping=abs(sysData[M]['Pump1']['target'])
        for pv in range(-10,-1):
            pastpumping=pastpumping+abs(sysData[M]['Pump1']['record'][pv])

        if pastpumping==0.0:
            sysData[M]['Pump2']['target']=0.0
            sysData[M]['Pump1']['target']=0.0 #This should be equal to 0 anyway.

    set_output_on_sync(M,'Pump1',1)
    set_output_on_sync(M,'Pump2',1)

    if (sysData[M]['Zigzag']['ON']==1): #If the zigzag growth estimation is running then we change OD setpoint appropriately.
        try:
            sysData[M]['OD']['target']=TargetOD
        except Exception:
            print('Somehow you managed to activate Zigzag at a sub-optimal time')
            logger.exception('Failed to restore Zigzag target on %s', M)
            #Do nothing

    return


def Zigzag(M):
    #This function dithers OD in a "zigzag" pattern, and estimates growthrate. This function is only called when ZigZag mode is active.
    M=str(M)
    centre=sysData[M]['OD']['target']
    current=sysData[M]['OD']['current']
    zig=sysData[M]['Zigzag']['Zig']
    iteration=sysData[M]['Experiment']['cycles']

    try:
        last=sysData[M]['OD']['record'][-1]
    except: #This will happen if you activate Zigzag in first control iteration!
        last=current

    if (current<centre-zig and last<centre):
        if(sysData[M]['Zigzag']['target']!=5.0):
            sysData[M]['Zigzag']['SwitchPoint']=iteration
        sysData[M]['Zigzag']['target']=5.0 #an excessively high OD value.
    elif (current>centre+zig and last>centre+zig):
        sysData[M]['Zigzag']['target']=centre-zig*1.5
        sysData[M]['Zigzag']['SwitchPoint']=iteration

    sysData[M]['OD']['target']=sysData[M]['Zigzag']['target']

    #Subsequent section is for growth estimation.

    TimeSinceSwitch=iteration-sysData[M]['Zigzag']['SwitchPoint']
    if (iteration>6 and TimeSinceSwitch>5 and current > 0 and last > 0 and sysData[M]['Zigzag']['target']==5.0): #The reason we wait a few minutes after starting growth is that new media may still be introduced, it takes a while for the growth to get going.
        dGrowthRate=(math.log(current)-math.log(last))*60.0 #Converting to units of 1/hour
        sysData[M]['GrowthRate']['current']=sysData[M]['GrowthRate']['current']*0.95 + dGrowthRate*0.05 #We are essentially implementing an online growth rate estimator with learning rate 0.05

    return


def _median_and_spread(vals):
    #Median (robust central value, resists a single outlier flash) and spread (max - min)
    #of a short list of replicate reads. No numpy needed for these tiny lists.
    s=sorted(vals)
    n=len(s)
    median=s[n//2] if n%2 else (s[n//2-1]+s[n//2])/2.0
    return median, (s[-1]-s[0])


def runExperiment(M, placeholder):
    #Primary function for running an automated experiment.
    from app import (
        set_output_on_sync,
        addTerminal,
        clearTerminal,
        turnEverythingOff,
    )
    from chibio_control_helpers import CustomProgram, LightActuation, csvData, downsample
    from chibio_measurements import measure_fp, measure_od, measure_temp

    M=str(M)

    sysData[M]['Experiment']['threadCount']=(sysData[M]['Experiment']['threadCount']+1)%100
    currentThread=sysData[M]['Experiment']['threadCount']
    try:
        while (sysData[M]['Experiment']['ON'] and sysData[M]['Experiment']['threadCount']==currentThread):
            # Get time running in seconds
            now=datetime.now()
            elapsedTime=now-sysData[M]['Experiment']['startTimeRaw']
            elapsedTimeSeconds=round(elapsedTime.total_seconds(),2)
            sysData[M]['Experiment']['cycles']=sysData[M]['Experiment']['cycles']+1
            addTerminal(M,'Cycle ' + str(sysData[M]['Experiment']['cycles']) + ' Started')
            CycleTime=sysData[M]['Experiment']['cycleTime']

            set_output_on_sync(M,'Stir',0) #Turning stirring off
            time.sleep(5.0) #Wait for liquid to settle.
            if (sysData[M]['Experiment']['ON']==0):
                turnEverythingOff(M)
                sysData[M]['Experiment']['cycles']=sysData[M]['Experiment']['cycles']-1 # Cycle didn't finish, don't count it.
                addTerminal(M,'Experiment Stopped')
                return

            sysData[M]['OD']['Measuring']=1 #Begin measuring - this flag is just to indicate that a measurement is currently being taken.

            #Measure OD 3 times and take the MEDIAN (robust to the occasional outlier read)
            #plus the spread, instead of a plain mean, so measurement noise is recorded rather
            #than averaged away. The median feeds RegulateOD and the CSV. Invalid if any read failed.
            ODreadings=[]
            ODcorr=[]
            od_valid=1
            for i in [0, 1, 2]:
                measure_od(M)
                ODreadings.append(sysData[M]['OD']['current'])
                ODcorr.append(sysData[M]['OD'].get('corrected', sysData[M]['OD']['current']))
                od_valid=od_valid and sysData[M]['OD'].get('valid',1)
                time.sleep(0.25)
            sysData[M]['OD']['current'], sysData[M]['OD']['spread']=_median_and_spread(ODreadings)
            sysData[M]['OD']['corrected'], _=_median_and_spread(ODcorr)
            sysData[M]['OD']['valid']=od_valid

            measure_temp(M,'Internal') #Measuring all temperatures
            measure_temp(M,'External')
            measure_temp(M,'IR')

            #Replicate FP the same way: 3 flashes per active FP, record the median of each
            #channel and the spread (from the base signal). measure_fp handles all active FPs
            #per call; when none are on it's a cheap no-op so we keep the single-call path.
            fp_series={FP:{'Base':[],'Emit1':[],'Emit2':[]} for FP in ['FP1','FP2','FP3'] if sysData[M][FP]['ON']==1}
            if fp_series:
                fp_valid={FP:1 for FP in fp_series}
                for i in [0, 1, 2]:
                    measure_fp(M)
                    for FP in fp_series:
                        for key in ('Base','Emit1','Emit2'):
                            fp_series[FP][key].append(sysData[M][FP][key])
                        fp_valid[FP]=fp_valid[FP] and sysData[M][FP].get('valid',1)
                for FP in fp_series:
                    for key in ('Base','Emit1','Emit2'):
                        sysData[M][FP][key], _=_median_and_spread(fp_series[FP][key])
                    _, sysData[M][FP]['spread']=_median_and_spread(fp_series[FP]['Base'])
                    sysData[M][FP]['valid']=fp_valid[FP]
            else:
                measure_fp(M) #And now fluorescent protein concentrations.

            if (sysData[M]['Experiment']['ON']==0): #We do another check post-measurement to see whether we need to end the experiment.
                turnEverythingOff(M)
                sysData[M]['Experiment']['cycles']=sysData[M]['Experiment']['cycles']-1 # Cycle didn't finish, don't count it.
                addTerminal(M,'Experiment Stopped')
                return
            #Temporary Biofilm Section - the below makes the device all spectral data for all LEDs each cycle.

            # bands=['nm410' ,'nm440','nm470','nm510','nm550','nm583','nm620','nm670','CLEAR','NIR']
            # items= ['LEDA','LEDB','LEDC','LEDD','LEDE','LEDF','LEDG','LASER650']
            # gains=['x10','x10','x10','x10','x10','x10','x10','x1']
            # gi=-1
            # for item in items:
            #     gi=gi+1
            #     SetOutputOn(M,item,1)
            #     GetSpectrum(M,gains[gi])
            #     SetOutputOn(M,item,0)
            #     for band in bands:
            #         sysData[M]['biofilm'][item][band]=int(sysData[M]['AS7341']['spectrum'][band])

            sysData[M]['OD']['Measuring']=0
            if (sysData[M]['OD']['ON']==1):
                RegulateOD(M) #Function that calculates new target pump rates, and sets pumps to desired rates.

            LightActuation(M,1)

            if (sysData[M]['Custom']['ON']==1): #Check if we have enabled custom programs
                CustomThread=Thread(target = CustomProgram, args=(M,)) #We run this in a thread in case we are doing something slow, we dont want to hang up the main l00p. The comma after M is to cast the args as a tuple to prevent it iterating over the thread M
                CustomThread.setDaemon(True)
                CustomThread.start();

            Pump2Ontime=sysData[M]['Experiment']['cycleTime']*1.05*abs(sysData[M]['Pump2']['target'])*sysData[M]['Pump2']['ON']+0.5 #The amount of time Pump2 is going to be on for following RegulateOD above.
            time.sleep(Pump2Ontime) #Pause here is to prevent output pumping happening at the same time as stirring.

            set_output_on_sync(M,'Stir',1) #Start stirring again.

            if(sysData[M]['Experiment']['cycles']%10==9): #Dont want terminal getting unruly, so clear it each 10 rotations.
                clearTerminal(M)

            #######Below stores all the results for plotting later
            sysData[M]['time']['record'].append(elapsedTimeSeconds)
            sysData[M]['OD']['record'].append(sysData[M]['OD']['current'])
            sysData[M]['OD']['targetrecord'].append( sysData[M]['OD']['target']*sysData[M]['OD']['ON'])
            sysData[M]['OD']['spreadRecord'].append(sysData[M]['OD']['spread'])          #for the chart error band
            sysData[M]['OD']['correctedRecord'].append(sysData[M]['OD']['corrected'])    #dark-corrected OD trace
            sysData[M]['Thermostat']['record'].append(sysData[M]['Thermostat']['target']*float(sysData[M]['Thermostat']['ON']))
            sysData[M]['Light']['record'].append(float(sysData[M]['Light']['ON']))
            sysData[M]['ThermometerInternal']['record'].append(sysData[M]['ThermometerInternal']['current'])
            sysData[M]['ThermometerExternal']['record'].append(sysData[M]['ThermometerExternal']['current'])
            sysData[M]['ThermometerIR']['record'].append(sysData[M]['ThermometerIR']['current'])
            sysData[M]['Pump1']['record'].append(sysData[M]['Pump1']['target']*float(sysData[M]['Pump1']['ON']))
            sysData[M]['Pump2']['record'].append(sysData[M]['Pump2']['target']*float(sysData[M]['Pump2']['ON']))
            sysData[M]['Pump3']['record'].append(sysData[M]['Pump3']['target']*float(sysData[M]['Pump3']['ON']))
            sysData[M]['Pump4']['record'].append(sysData[M]['Pump4']['target']*float(sysData[M]['Pump4']['ON']))
            sysData[M]['GrowthRate']['record'].append(sysData[M]['GrowthRate']['current']*float(sysData[M]['Zigzag']['ON']))
            for FP in ['FP1','FP2','FP3']:
                if sysData[M][FP]['ON']==1:
                    sysData[M][FP]['BaseRecord'].append(sysData[M][FP]['Base'])
                    sysData[M][FP]['Emit1Record'].append(sysData[M][FP]['Emit1'])
                    if (sysData[M][FP]['Emit2Band']!= "OFF"):
                        sysData[M][FP]['Emit2Record'].append(sysData[M][FP]['Emit2'])
                    else:
                        sysData[M][FP]['Emit2Record'].append(0.0)
                else:
                    sysData[M][FP]['BaseRecord'].append(0.0)
                    sysData[M][FP]['Emit1Record'].append(0.0)
                    sysData[M][FP]['Emit2Record'].append(0.0)

            #We  downsample our records such that the size of the data vectors being plot in the web interface does not get unruly.
            if (len(sysData[M]['time']['record'])>200):
                downsample(M)

            #### Writing Results to data files
            csvData(M) #This command writes system data to a CSV file for future keeping.
            #And intermittently write the setup parameters to a data file.
            if(sysData[M]['Experiment']['cycles']%10==1): #We only write whole configuration file each 10 cycles since it is not really that important.
                TempStartTime=sysData[M]['Experiment']['startTimeRaw']
                sysData[M]['Experiment']['startTimeRaw']=0 #We had to set this to zero during the write operation since the system does not like writing data in such a format.

                filename = sysData[M]['Experiment']['startTime'] + '_' + M + '.txt'
                filename=filename.replace(":","_")
                try:
                    with open(filename,'w') as output_file:
                        simplejson.dump(sysData[M],output_file)
                finally:
                    sysData[M]['Experiment']['startTimeRaw']=TempStartTime
            ##### Written

            if (sysData[M]['Experiment']['ON']==0):
                turnEverythingOff(M)
                addTerminal(M,'Experiment Stopped')
                return

            nowend=datetime.now()
            elapsedTime2=nowend-now
            elapsedTimeSeconds2=round(elapsedTime2.total_seconds(),2)
            sleeptime=CycleTime-elapsedTimeSeconds2
            if (sleeptime<0):
                sleeptime=0
                addTerminal(M,'Experiment Cycle Time is too short!!!')

            time.sleep(sleeptime)
            LightActuation(M,0) #Turn light actuation off if it is running.
            addTerminal(M,'Cycle ' + str(sysData[M]['Experiment']['cycles']) + ' Complete')
    finally:
        sysDevices[M]['Experiment']['running']=0
        if (sysData[M]['Experiment']['ON']==0):
            turnEverythingOff(M)
            addTerminal(M,'Experiment Stopped')
