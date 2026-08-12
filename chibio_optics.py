import time
import logging
from datetime import datetime

from chibio_hardware import I2CCom, measurement_sequence
from chibio_state import sysData, sysItems

logger = logging.getLogger('chibio')

# Auto-ranging bounds. Gain is an AS7341 index 0..10 (0.5x .. 512x). Drop it when any
# requested channel runs out of headroom; raise it when the brightest requested channel is
# very weak. ponytail: simple thresholds + a small retry cap; tune _AUTORANGE_WEAK if a
# sample class sits awkwardly between two gain steps.
_ADC_MAX = 65535
_AUTORANGE_WEAK = 1000
_AUTORANGE_MAX_TRIES = 4

# ASTEP, written explicitly rather than left at its reset value. 999 IS that reset value, so
# readings are unchanged -- the point is that full scale stops being an unstated assumption.
# Step time is (ASTEP+1) x 2.78 us = 2.78 ms, which is what the ISteps comments already claim.
_ASTEP = 999

# Fraction of full scale past which a reading has lost its headroom. Set so that at the 65535
# full scale of a 255-step read it is the 60000 counts the FP guard already used (~92%); as a
# fraction it stays meaningful at any integration time. Used for BOTH the auto-range step-down
# and the FP validity guard, so a hot base now gets a lower gain instead of being discarded:
# auto-range previously only retried on an EXACT 65535, losing the whole 60000-65534 band
# (49% of M4's FP1 rows and 57% of M0's FP2 in Run 0 -- INVARIANTS 7).
NEAR_SATURATION_FRACTION = 60000.0 / 65535.0


def adc_full_scale(ISteps):
    """Digital full scale of one read: min(65535, (ATIME+1) x (ASTEP+1)) -- ams DS000504 Eq. 2.

    It is NOT always 65535. At the ISteps=10 used by the LED V1/V2 auto-detection full scale
    is 11,000, so a saturated detection read compared against a hardcoded 65535 looked
    perfectly healthy; if a bright board pinned both the baseline and the pulsed reading, the
    "LED present" test silently concluded absent and fell back to V1 on a V2 board.
    """
    ISteps = int(ISteps)
    ISteps = 255 if ISteps > 255 else (0 if ISteps < 0 else ISteps)
    return min(_ADC_MAX, (ISteps + 1) * (_ASTEP + 1))


def as7341_read(M, Gain, ISteps, reset):
    #Responsible for reading data from the spectrometer.
    reset=int(reset)
    ISteps=int(ISteps)
    if ISteps>255:
        ISteps=255 #255 steps is approx 0.71 seconds.
    elif (ISteps<0):
        ISteps=0
    if Gain>10:
        Gain=10 #512x
    elif (Gain<0):
        Gain=0 #0.5x

    I2CCom(M,'AS7341',0,8,int(0xA9),int(0x04),0) #This sets us into BANK mode 0, for accesing registers 0x80+. The 4 means we have WTIMEx16
    if (reset==1):
        I2CCom(M,'AS7341',0,8,int(0x80),int(0x00),0) #Turns power down
        time.sleep(0.01)
        I2CCom(M,'AS7341',0,8,int(0x80),int(0x01),0) #Turns power on with spectral measurement disabled
    else:
        I2CCom(M,'AS7341',0,8,int(0x80),int(0x01),0)  #Turns power on with spectral measurement disabled

    I2CCom(M,'AS7341',0,8,int(0xAF),int(0x10),0) #Tells it we are going to now write SMUX configuration to RAM

    #I2CCom(M,'AS7341',0,100,int(0x00),int(0x00),0) #Forces AS7341SMUX to run since length is 100.
    as7341_smux(M,'AS7341',0,0)

    I2CCom(M,'AS7341',0,8,int(0x80),int(0x11),0)  #Runs SMUX command (i.e. cofigures SMUX with data from ram)
    time.sleep(0.001)
    I2CCom(M,'AS7341',0,8,int(0x81),ISteps,0)  #Sets number of integration steps of length 2.78ms Max ISteps is 255
    #Write ASTEP explicitly (0xCA/0xCB) instead of relying on its reset default. Same value,
    #so integration time and every reading are unchanged -- but full scale is now a property we
    #set rather than one we assume, which is what makes adc_full_scale() trustworthy.
    I2CCom(M,'AS7341',0,8,int(0xCA),_ASTEP & 0xFF,0)
    I2CCom(M,'AS7341',0,8,int(0xCB),(_ASTEP >> 8) & 0xFF,0)
    I2CCom(M,'AS7341',0,8,int(0x83),0xFF,0)  #Sets maxinum wait time of 0.7mS (multiplex by 16 due to WLONG)
    I2CCom(M,'AS7341',0,8,int(0xAA),Gain,0)  #Sets gain on ADCs. Maximum value of Gain is 10 and can take values from 0 to 10.
    #I2CCom(M,'AS7341',0,8,int(0xA9),int(0x14),0) #This sets us into BANK mode 1, for accessing 0x60 to 0x74. The 4 means we have WTIMEx16
    #I2CCom(M,'AS7341',0,8,int(0x70),int(0x00),0)  #Sets integration mode SPM (normal mode)
    #Above is default of 0x70!
    I2CCom(M,'AS7341',0,8,int(0x80),int(0x0B),0)  #Starts spectral measurement, with WEN (wait between measurements feature) enabled.
    time.sleep((ISteps+1)*0.0028 + 0.2) #Wait whilst integration is done and results are processed.

    ASTATUS=int(I2CCom(M,'AS7341',1,8,0x94,0x00,0)) #Get measurement status, including saturation details.
    #STATUS2 (0xA3) carries ASAT_ANALOG (bit 3) and ASAT_DIGITAL (bit 4). Read here, while the
    #result is still latched, rather than after the measurement is stopped below.
    STATUS2=int(I2CCom(M,'AS7341',1,8,0xA3,0x00,0))
    C0_L=int(I2CCom(M,'AS7341',1,8,0x95,0x00,0))
    C0_H=int(I2CCom(M,'AS7341',1,8,0x96,0x00,0))
    C1_L=int(I2CCom(M,'AS7341',1,8,0x97,0x00,0))
    C1_H=int(I2CCom(M,'AS7341',1,8,0x98,0x00,0))
    C2_L=int(I2CCom(M,'AS7341',1,8,0x99,0x00,0))
    C2_H=int(I2CCom(M,'AS7341',1,8,0x9A,0x00,0))
    C3_L=int(I2CCom(M,'AS7341',1,8,0x9B,0x00,0))
    C3_H=int(I2CCom(M,'AS7341',1,8,0x9C,0x00,0))
    C4_L=int(I2CCom(M,'AS7341',1,8,0x9D,0x00,0))
    C4_H=int(I2CCom(M,'AS7341',1,8,0x9E,0x00,0))
    C5_L=int(I2CCom(M,'AS7341',1,8,0x9F,0x00,0))
    C5_H=int(I2CCom(M,'AS7341',1,8,0xA0,0x00,0))

    I2CCom(M,'AS7341',0,8,int(0x80),int(0x01),0)  #Stops spectral measurement, leaves power on.

    #The chip's own saturation verdict, which upstream read and threw away. It matters because
    #ASAT_ANALOG fires BEFORE the digital counter fills, so no threshold on the returned counts
    #-- including the FP near-saturation guard -- can see analog saturation, and that is exactly
    #the regime a 90-degree scatter geometry with a bright LED at high gain lives in. Belt and
    #braces: the count threshold catches a compressing ratio, this catches a pinned front end.
    #
    #Use STATUS2 (0xA3), NOT ASTATUS (0x94). Measured on this rig 2026-08-12 by driving the
    #laser into the ADC ceiling: ASTATUS reads 0x00 at every gain -- both its ASAT_STATUS bit
    #and its AGAIN_STATUS nibble are inert here -- while STATUS2 goes 0x40 -> 0x58 exactly as
    #the ADC pins (bit 6 AVALID, bit 3 ASAT_ANALOG, bit 4 ASAT_DIGITAL). So the gain actually
    #applied is NOT recoverable from the chip; the requested/auto-ranged gain recorded in
    #['gain'] remains the only account of it. ASTATUS is still read above because the datasheet's
    #read flow starts there and removing it would change a validated sensor path for nothing.
    sysData[M]['AS7341']['current']['saturated']=1 if (STATUS2 & 0x18) else 0
    sysData[M]['AS7341']['current']['fullScale']=adc_full_scale(ISteps)

    sysData[M]['AS7341']['current']['ADC0']=int(bin(C0_H)[2:].zfill(8)+bin(C0_L)[2:].zfill(8),2)
    sysData[M]['AS7341']['current']['ADC1']=int(bin(C1_H)[2:].zfill(8)+bin(C1_L)[2:].zfill(8),2)
    sysData[M]['AS7341']['current']['ADC2']=int(bin(C2_H)[2:].zfill(8)+bin(C2_L)[2:].zfill(8),2)
    sysData[M]['AS7341']['current']['ADC3']=int(bin(C3_H)[2:].zfill(8)+bin(C3_L)[2:].zfill(8),2)
    sysData[M]['AS7341']['current']['ADC4']=int(bin(C4_H)[2:].zfill(8)+bin(C4_L)[2:].zfill(8),2)
    sysData[M]['AS7341']['current']['ADC5']=int(bin(C5_H)[2:].zfill(8)+bin(C5_L)[2:].zfill(8),2)

    #Compare against THIS read's full scale, not a hardcoded 65535 (which at short integration
    #times is unreachable, so saturation was invisible), and trust the chip's own flag too.
    #Upstream's "Not sure if this saturation check above actually works correctly..." was right:
    #it could not, at any ISteps below 65.
    fullScale=sysData[M]['AS7341']['current']['fullScale']
    adcs=[sysData[M]['AS7341']['current'][d] for d in ('ADC0','ADC1','ADC2','ADC3','ADC4','ADC5')]
    if sysData[M]['AS7341']['current']['saturated'] or any(a>=fullScale for a in adcs):
        logger.warning('Spectrometer saturated on %s (full scale %d at ISteps=%d, hw flag %d, max ADC %d)',
                       M, fullScale, ISteps, sysData[M]['AS7341']['current']['saturated'], max(adcs))


def as7341_smux(M, device, data1, data2):
    #Sets up the ADC multiplexer on the spectrometer, this is responsible for connecting photodiodes to amplifier/adc circuits within the device.
    #The spectrometer has only got 6 ADCs but >6 photodiodes channels, hence you need to select a subset of photodiodes to measure with each shot. The relative gain does change slightly (1-2%) between ADCs.
    M=str(M)
    Addresses=['0x00','0x01','0x02','0x03','0x04','0x05','0x06','0x07','0x08','0x0A','0x0B','0x0C','0x0D','0x0E','0x0F','0x10','0x11','0x12']
    for a in Addresses:
        A=sysItems['AS7341'][a]['A']
        B=sysItems['AS7341'][a]['B']
        if (A!='U'):
            As=sysData[M]['AS7341']['channels'][A]
        else:
            As=0
        if (B!='U'):
            Bs=sysData[M]['AS7341']['channels'][B]
        else:
            Bs=0
        Ab=str(bin(As))[2:].zfill(4)
        Bb=str(bin(Bs))[2:].zfill(4)
        C=Ab+Bb
        #time.sleep(0.001) #Added this to remove errors where beaglebone crashed!
        I2CCom(M,'AS7341',0,8,int(a,16),int(C,2),0) #Tells it we are going to now write SMUX configuration to RAM
        #sysDevices[M][device]['device'].write8(int(a,16),int(C,2))


def get_spectrum(M, Gain):
    #Measures entire spectrum, i.e. every different photodiode, which requires 2 measurement shots.
    Gain=int(Gain[1:])
    M=str(M)
    if (M=="0"):
        M=sysItems['UIDevice']
    #No auto-ranging here: get_spectrum feeds CharacteriseDevice, which sweeps LED power and
    #compares raw band counts ACROSS reads -- a per-read gain change would make them
    #non-comparable (and the sweep records no per-cell gain). Fixed gain keeps it comparable.
    out=get_light(M,['nm410','nm440','nm470','nm510','nm550','nm583'],Gain,255)
    out2=get_light(M,['nm620', 'nm670','CLEAR','NIR','DARK'],Gain,255)
    sysData[M]['AS7341']['spectrum']['nm410']=out[0]
    sysData[M]['AS7341']['spectrum']['nm440']=out[1]
    sysData[M]['AS7341']['spectrum']['nm470']=out[2]
    sysData[M]['AS7341']['spectrum']['nm510']=out[3]
    sysData[M]['AS7341']['spectrum']['nm550']=out[4]
    sysData[M]['AS7341']['spectrum']['nm583']=out[5]
    sysData[M]['AS7341']['spectrum']['nm620']=out2[0]
    sysData[M]['AS7341']['spectrum']['nm670']=out2[1]
    sysData[M]['AS7341']['spectrum']['CLEAR']=out2[2]
    sysData[M]['AS7341']['spectrum']['NIR']=out2[3]


def get_light(M, wavelengths, Gain, ISteps, autorange=False):
    #Runs spectrometer measurement and puts data into appropriate structure.
    #autorange (opt-in): adjust Gain and re-read on saturation/weak-signal, then record the
    #gain actually used. NEVER enable for OD -- its gain is locked to the OD calibration.
    M=str(M)
    channels=['nm410','nm440','nm470','nm510','nm550','nm583','nm620', 'nm670','CLEAR','NIR','DARK','ExtGPIO', 'ExtINT' , 'FLICKER']
    for channel in channels:
        sysData[M]['AS7341']['channels'][channel]=0 #First we set all measurement ADC indexes to zero.
    index=1
    for wavelength in wavelengths:
        if wavelength != "OFF":
            sysData[M]['AS7341']['channels'][wavelength]=index #Now assign ADCs to each of the channel where needed.
        index=index+1

    DACS=['ADC0', 'ADC1', 'ADC2', 'ADC3', 'ADC4', 'ADC5']
    success=0
    while success<2:
        try:
            as7341_read(M,Gain,ISteps,success)
            sysData[M]['AS7341']['current']['valid']=1
            success=2
        except Exception:
            print(str(datetime.now()) + 'AS7341 measurement failed on ' + str(M))
            logger.exception('AS7341 measurement failed on %s', M)
            success=success+1
            if success==2:
                # Don't fabricate a plausible reading (old code set ADC0=1, rest=0, which
                # looked like a real point in the data). Mark the read invalid and keep the
                # last-known ADC values so sysData stays numeric (the UI JSON and RegulateOD
                # never see NaN). csvData records NaN for this cycle so the failure is
                # distinguishable in analysis. See sensor-failure-semantics decision.
                print(str(datetime.now()) + 'AS7341 measurement failed twice on ' + str(M) + ', marking invalid (keeping last-known values)')
                sysData[M]['AS7341']['current']['valid']=0

    # Auto-range: step the gain toward a usable signal and re-read. Bounded retries so a
    # persistently saturated/dark sample can't loop. Only looks at the requested channels
    # (max() ignores the ~0 DARK channel, so it never forces the gain up).
    if autorange and sysData[M]['AS7341']['current']['valid']==1:
        nchan=sum(1 for w in wavelengths if w!="OFF")
        #Step down on lost HEADROOM (or the chip's own saturation flag), not on an exact
        #ceiling hit. Requiring a literal 65535 meant a base sitting anywhere in 60000-65534
        #was never re-read at a lower gain -- it just got flagged invalid and thrown away
        #downstream, which is how a run at x10 lost half its FP rows once the culture grew
        #(INVARIANTS 7). Stepping down here keeps the row instead: the emit/base ratio is
        #gain-invariant, so a lower gain is directly comparable.
        #Derived from ISteps rather than read back out of sysData: it is deterministic, and it
        #stays correct even if a caller stubs the low-level read.
        hot=adc_full_scale(ISteps)*NEAR_SATURATION_FRACTION
        tries=0
        while tries<_AUTORANGE_MAX_TRIES:
            adcs=[sysData[M]['AS7341']['current'][DACS[i]] for i in range(nchan)]
            saturated=sysData[M]['AS7341']['current'].get('saturated',0)
            if (saturated or any(a>=hot for a in adcs)) and Gain>0:
                Gain=Gain-1
            elif adcs and max(adcs)<_AUTORANGE_WEAK and Gain<10:
                Gain=Gain+1
            else:
                break
            try:
                as7341_read(M,Gain,ISteps,0)
            except Exception:
                sysData[M]['AS7341']['current']['valid']=0
                break
            tries=tries+1
    sysData[M]['AS7341']['current']['gain']=Gain #Record the gain actually used (transparency).

    output=[0.0,0.0,0.0,0.0,0.0,0.0]
    index=0
    for wavelength in wavelengths:
        if wavelength != "OFF":
            output[index]=sysData[M]['AS7341']['current'][DACS[index]]
        index=index+1

    return output


def get_transmission(M, item, wavelengths, Gain, ISteps, autorange=False):
    #Gets light transmission through sample by turning on light, measuring, turning off light.
    #The whole on->read->off runs under the reactor's measurement mutex. The global bus lock
    #only serializes the individual I2C transactions inside these three steps, so without this
    #a concurrent FluorescenceScan on the same reactor switches the light off between the
    #switch-on and the read: the read then succeeds against a dark sample and logs raw=0 with
    #valid=1, which no downstream check flags (INVARIANTS 5).
    from app import set_output_on_sync

    M=str(M)
    with measurement_sequence(M):
        set_output_on_sync(M,item,1)
        try:
            output=get_light(M,wavelengths,Gain,ISteps,autorange)
        finally:
            set_output_on_sync(M,item,0) #never leave the light on if the read raises
    return output
