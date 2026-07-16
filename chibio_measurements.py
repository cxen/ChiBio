import math
import logging

from chibio_hardware import I2CCom
from chibio_optics import get_transmission
from chibio_state import sysData, sysItems

logger = logging.getLogger('chibio')


def measure_od(M):
    #Measures laser transmission and calculates calibrated OD from this.
    M=str(M)
    if (M=="0"):
        M=sysItems['UIDevice']
    device=sysData[M]['OD']['device']
    if (device=='LASER650'):
        out=get_transmission(M,'LASER650',['CLEAR'],1,255)
        sysData[M]['OD0']['raw']=float(out[0])

        a=sysData[M]['OD0']['LASERa']#Retrieve the calibration factors for OD.
        b=sysData[M]['OD0']['LASERb']
        if abs(sysData[M]['OD0']['raw']) > 0.001: # avoid devision by 0
            raw=math.log10(sysData[M]['OD0']['target']/sysData[M]['OD0']['raw'])
            sysData[M]['OD']['current']=raw*b + raw*raw*a
        else:
            sysData[M]['OD']['current']=0
            print(' OD Measurement close to 0 on ' + str(device))
    elif (device=='LEDF'):
        out=get_transmission(M,'LEDF',['CLEAR'],7,255)

        sysData[M]['OD0']['raw']=out[0]
        a=sysData[M]['OD0']['LEDFa']#Retrieve the calibration factors for OD.
        try:
            if (M=='M0'):
                CF=1299.0
            elif (M=='M1'):
                CF=1206.0
            elif (M=='M2'):
                CF=1660.0
            elif (M=='M3'):
                CF=1494.0
            #raw=out[0]/CF - sysData[M]['OD0']['target']/CF
            raw=out[0]/sysData[M]['OD0']['target']
            sysData[M]['OD']['current']=raw
        except Exception:
            sysData[M]['OD']['current']=0
            print(' OD Measurement exception on ' + str(device))
            logger.exception('OD measurement failed on %s', device)

    elif (device=='LEDA'):
        out=get_transmission(M,'LEDA',['CLEAR'],7,255)

        sysData[M]['OD0']['raw']=out[0]
        a=sysData[M]['OD0']['LEDAa']#Retrieve the calibration factors for OD.
        try:
            if (M=='M0'):
                CF=422.0
            elif (M=='M1'):
                CF=379.0
            elif (M=='M2'):
                CF=574.0
            elif (M=='M3'):
                CF=522.0
            #raw=out[0]/CF - sysData[M]['OD0']['target']/CF
            raw=out[0]/sysData[M]['OD0']['target']
            #sysData[M]['OD']['current']=raw*a
            sysData[M]['OD']['current']=raw
        except Exception:
            sysData[M]['OD']['current']=0
            print(' OD Measurement exception on ' + str(device))
            logger.exception('OD measurement failed on %s', device)

    #Propagate the spectrometer read validity to the OD measurement. sysData keeps a
    #numeric (last-known) OD so the UI JSON and RegulateOD never see NaN; csvData records
    #NaN for this cycle when invalid. See the sensor-failure-semantics decision.
    sysData[M]['OD']['valid']=sysData[M]['AS7341']['current'].get('valid',1)


def measure_fp(M):
    #Responsible for measuring each of the active Fluorescent proteins.
    M=str(M)
    if (M=="0"):
        M=sysItems['UIDevice']
    for FP in ['FP1','FP2','FP3']:
        if sysData[M][FP]['ON']==1:
            Gain=int(sysData[M][FP]['Gain'][1:])
            out=get_transmission(M,sysData[M][FP]['LED'],[sysData[M][FP]['BaseBand'],sysData[M][FP]['Emit1Band'],sysData[M][FP]['Emit2Band']],Gain,255)
            sysData[M][FP]['Base']=float(out[0])
            if (sysData[M][FP]['Base']>0):
                sysData[M][FP]['Emit1']=float(out[1])/sysData[M][FP]['Base']
                sysData[M][FP]['Emit2']=float(out[2])/sysData[M][FP]['Base']
            else:#This might happen if you try to measure in CLEAR whilst also having CLEAR as baseband!
                sysData[M][FP]['Emit1']=float(out[1])
                sysData[M][FP]['Emit2']=float(out[2])
            sysData[M][FP]['valid']=sysData[M]['AS7341']['current'].get('valid',1) #see sensor-failure-semantics


def measure_temp(M, which):
    #Used to measure temperature from each thermometer.
    if (M=="0"):
        M=sysItems['UIDevice']
    M=str(M)
    which='Thermometer' + str(which)
    if (which=='ThermometerInternal' or which=='ThermometerExternal'):
        getData=I2CCom(M,which,1,16,0x05,0,0)
        getDataBinary=bin(getData)
        tempData=getDataBinary[6:]
        temperature=float(int(tempData,2))/16.0
    elif(which=='ThermometerIR'):
        getData=I2CCom(M,which,1,0,0x07,0,1)
        temperature = (getData*0.02) - 273.15

    if sysData[M]['present']==0:
        temperature=0.0
    if temperature>100.0:#It seems sometimes the IR thermometer returns a value of 1000 due to an error. This prevents that.
        temperature=sysData[M][which]['current']
    sysData[M][which]['current']=temperature
