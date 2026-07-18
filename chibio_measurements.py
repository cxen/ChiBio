import math
import logging

from chibio_hardware import I2CCom
from chibio_optics import get_transmission
from chibio_state import sysData, sysItems

logger = logging.getLogger('chibio')


# ~92% of the 16-bit (65535) ADC ceiling. Above this the CLEAR "base" compresses toward
# clipping, so the emit/base ratio inflates and reads as an artifactual signal change.
# get_light's autorange only retries on an EXACT 65535, so near-ceiling bases slip through
# (measured on a dense culture: 27% of FP cycles > 60000, some pinned at the ceiling).
# ponytail: fixed threshold; retune against a saturating culture if 60000 proves off.
_FP_BASE_NEAR_SATURATION = 60000


def _fp_valid_flag(base, as7341_valid):
    # A near-saturated CLEAR base makes the emit/base ratio untrustworthy, so mark the read
    # invalid — csvData then logs NaN for the cell instead of a silently-corrupted ratio,
    # keeping the same validity/NaN contract as a comms failure (see the
    # sensor-failure-semantics and fluorescence-quantification-untrustworthy memories).
    if as7341_valid == 0:
        return 0
    if base >= _FP_BASE_NEAR_SATURATION:
        return 0
    return 1


def _record_od_dark(M, out):
    #out[0]=CLEAR transmission (raw), out[1]=the DARK background channel measured in the
    #same read. Keep raw untouched (never overwrite it); store the dark value and the
    #dark-corrected transmission separately so analysis can use either. See TODO P5.
    sysData[M]['OD0']['dark']=float(out[1])
    sysData[M]['OD0']['rawCorrected']=float(out[0])-float(out[1])


def _od_from_transmission(M, device, transmission):
    #Calibrated OD from a transmission reading, using the same formula each OD device uses in
    #measure_od. Factored only so the dark-corrected transmission can be turned into a
    #display-only corrected OD trace; the raw OD that feeds control is still computed inline
    #below. DARK is tiny for LASER (~1 count) so corrected usually overlaps raw.
    if device=='LASER650':
        a=sysData[M]['OD0']['LASERa']
        b=sysData[M]['OD0']['LASERb']
        if abs(transmission) > 0.001:
            r=math.log10(sysData[M]['OD0']['target']/transmission)
            return r*b + r*r*a
        return 0
    try:
        return transmission/sysData[M]['OD0']['target']  # LEDF / LEDA: ratio to the blank
    except Exception:
        return 0


def measure_od(M):
    #Measures laser transmission and calculates calibrated OD from this.
    M=str(M)
    if (M=="0"):
        M=sysItems['UIDevice']
    device=sysData[M]['OD']['device']
    if (device=='LASER650'):
        out=get_transmission(M,'LASER650',['CLEAR','DARK'],1,255)
        sysData[M]['OD0']['raw']=float(out[0])
        _record_od_dark(M,out)

        a=sysData[M]['OD0']['LASERa']#Retrieve the calibration factors for OD.
        b=sysData[M]['OD0']['LASERb']
        if abs(sysData[M]['OD0']['raw']) > 0.001: # avoid devision by 0
            raw=math.log10(sysData[M]['OD0']['target']/sysData[M]['OD0']['raw'])
            sysData[M]['OD']['current']=raw*b + raw*raw*a
        else:
            sysData[M]['OD']['current']=0
            print(' OD Measurement close to 0 on ' + str(device))
    elif (device=='LEDF'):
        out=get_transmission(M,'LEDF',['CLEAR','DARK'],7,255)

        sysData[M]['OD0']['raw']=out[0]
        _record_od_dark(M,out)
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
        out=get_transmission(M,'LEDA',['CLEAR','DARK'],7,255)

        sysData[M]['OD0']['raw']=out[0]
        _record_od_dark(M,out)
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

    #Display-only dark-corrected OD (from raw - dark transmission). Never feeds control; the
    #raw OD['current'] above is unchanged. Charted as a second OD trace.
    sysData[M]['OD']['corrected']=_od_from_transmission(M, device, sysData[M]['OD0'].get('rawCorrected', sysData[M]['OD0']['raw']))

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
            #FP is safe to auto-range: base and emit are read in one shot at one gain, so the
            #emit/base ratio is gain-invariant. OD is not (its gain is calibration-locked).
            out=get_transmission(M,sysData[M][FP]['LED'],[sysData[M][FP]['BaseBand'],sysData[M][FP]['Emit1Band'],sysData[M][FP]['Emit2Band']],Gain,255,autorange=True)
            sysData[M][FP]['GainUsed']=sysData[M]['AS7341']['current'].get('gain',Gain)
            sysData[M][FP]['Base']=float(out[0])
            if (sysData[M][FP]['Base']>0):
                sysData[M][FP]['Emit1']=float(out[1])/sysData[M][FP]['Base']
                sysData[M][FP]['Emit2']=float(out[2])/sysData[M][FP]['Base']
            else:#This might happen if you try to measure in CLEAR whilst also having CLEAR as baseband!
                sysData[M][FP]['Emit1']=float(out[1])
                sysData[M][FP]['Emit2']=float(out[2])
            sysData[M][FP]['valid']=_fp_valid_flag(sysData[M][FP]['Base'],sysData[M]['AS7341']['current'].get('valid',1)) #see sensor-failure-semantics + the near-saturation guard above


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
