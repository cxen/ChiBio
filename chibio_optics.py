import time
import logging
from datetime import datetime

from chibio_hardware import I2CCom
from chibio_state import sysData, sysItems

logger = logging.getLogger('chibio')


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
    I2CCom(M,'AS7341',0,8,int(0x83),0xFF,0)  #Sets maxinum wait time of 0.7mS (multiplex by 16 due to WLONG)
    I2CCom(M,'AS7341',0,8,int(0xAA),Gain,0)  #Sets gain on ADCs. Maximum value of Gain is 10 and can take values from 0 to 10.
    #I2CCom(M,'AS7341',0,8,int(0xA9),int(0x14),0) #This sets us into BANK mode 1, for accessing 0x60 to 0x74. The 4 means we have WTIMEx16
    #I2CCom(M,'AS7341',0,8,int(0x70),int(0x00),0)  #Sets integration mode SPM (normal mode)
    #Above is default of 0x70!
    I2CCom(M,'AS7341',0,8,int(0x80),int(0x0B),0)  #Starts spectral measurement, with WEN (wait between measurements feature) enabled.
    time.sleep((ISteps+1)*0.0028 + 0.2) #Wait whilst integration is done and results are processed.

    ASTATUS=int(I2CCom(M,'AS7341',1,8,0x94,0x00,0)) #Get measurement status, including saturation details.
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

    #Status2=int(I2CCom(M,'AS7341',1,8,0xA3,0x00,0)) #Reads system status at end of spectral measursement.
    #print(str(ASTATUS))
    #print(str(Status2))

    sysData[M]['AS7341']['current']['ADC0']=int(bin(C0_H)[2:].zfill(8)+bin(C0_L)[2:].zfill(8),2)
    sysData[M]['AS7341']['current']['ADC1']=int(bin(C1_H)[2:].zfill(8)+bin(C1_L)[2:].zfill(8),2)
    sysData[M]['AS7341']['current']['ADC2']=int(bin(C2_H)[2:].zfill(8)+bin(C2_L)[2:].zfill(8),2)
    sysData[M]['AS7341']['current']['ADC3']=int(bin(C3_H)[2:].zfill(8)+bin(C3_L)[2:].zfill(8),2)
    sysData[M]['AS7341']['current']['ADC4']=int(bin(C4_H)[2:].zfill(8)+bin(C4_L)[2:].zfill(8),2)
    sysData[M]['AS7341']['current']['ADC5']=int(bin(C5_H)[2:].zfill(8)+bin(C5_L)[2:].zfill(8),2)

    if (sysData[M]['AS7341']['current']['ADC0']==65535 or sysData[M]['AS7341']['current']['ADC1']==65535 or sysData[M]['AS7341']['current']['ADC2']==65535 or sysData[M]['AS7341']['current']['ADC3']==65535 or sysData[M]['AS7341']['current']['ADC4']==65535 or sysData[M]['AS7341']['current']['ADC5']==65535 ):
        print(str(datetime.now()) + ' Spectrometer measurement was saturated on device ' + str(M)) #Not sure if this saturation check above actually works correctly...


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


def get_light(M, wavelengths, Gain, ISteps):
    #Runs spectrometer measurement and puts data into appropriate structure.
    M=str(M)
    channels=['nm410','nm440','nm470','nm510','nm550','nm583','nm620', 'nm670','CLEAR','NIR','DARK','ExtGPIO', 'ExtINT' , 'FLICKER']
    for channel in channels:
        sysData[M]['AS7341']['channels'][channel]=0 #First we set all measurement ADC indexes to zero.
    index=1
    for wavelength in wavelengths:
        if wavelength != "OFF":
            sysData[M]['AS7341']['channels'][wavelength]=index #Now assign ADCs to each of the channel where needed.
        index=index+1

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

    output=[0.0,0.0,0.0,0.0,0.0,0.0]
    index=0
    DACS=['ADC0', 'ADC1', 'ADC2', 'ADC3', 'ADC4', 'ADC5']
    for wavelength in wavelengths:
        if wavelength != "OFF":
            output[index]=sysData[M]['AS7341']['current'][DACS[index]]
        index=index+1

    return output


def get_transmission(M, item, wavelengths, Gain, ISteps):
    #Gets light transmission through sample by turning on light, measuring, turning off light.
    from app import set_output_on_sync

    M=str(M)
    set_output_on_sync(M,item,1)
    output=get_light(M,wavelengths,Gain,ISteps)
    set_output_on_sync(M,item,0)
    return output
