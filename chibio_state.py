import copy
from threading import Lock


lock = Lock()


# Sysdata is a structure created for each device and contains the setup / measured data
# related to that device during an experiment. All of this information is passed into
# the user interface during an experiment.
sysData = {'M0' : {
   'UIDevice' : 'M0',
   'present' : 0,
   'presentDevices' : { 'M0' : 0,'M1' : 0,'M2' : 0,'M3' : 0,'M4' : 0,'M5' : 0,'M6' : 0,'M7' : 0},
   'Version' : {'value' : 'Turbidostat V3.0','LED' : 1},
   'DeviceID' : '',
   'time' : {'record' : []},
   'LEDA' : {'WL' : '395', 'default': 0.1, 'target' : 0.0, 'max': 1.0, 'min' : 0.0,'ON' : 0},
   'LEDB' : {'WL' : '457', 'default': 0.1, 'target' : 0.0, 'max': 1.0, 'min' : 0.0,'ON' : 0},
   'LEDC' : {'WL' : '500', 'default': 0.1, 'target' : 0.0, 'max': 1.0, 'min' : 0.0,'ON' : 0},
   'LEDD' : {'WL' : '523', 'default': 0.1, 'target' : 0.0, 'max': 1.0, 'min' : 0.0,'ON' : 0},
   'LEDE' : {'WL' : '595', 'default': 0.1, 'target' : 0.0, 'max': 1.0, 'min' : 0.0,'ON' : 0},
   'LEDF' : {'WL' : '623', 'default': 0.1, 'target' : 0.0, 'max': 1.0, 'min' : 0.0,'ON' : 0},
   'LEDG' : {'WL' : '6500K', 'default': 0.1, 'target' : 0.0, 'max': 1.0, 'min' : 0.0,'ON' : 0},
   'LEDH' : {'WL' : '600', 'default': 0.1, 'target' : 0.0, 'max': 1.0, 'min' : 0.0,'ON' : 0}, #80nm FWHM
   'LEDI' : {'WL' : '550', 'default': 0.1, 'target' : 0.0, 'max': 1.0, 'min' : 0.0,'ON' : 0}, #105nm FWHM
   'LEDV' : {'WL' : 'White', 'default': 0.1, 'target' : 0.0, 'max': 1.0, 'min' : 0.0,'ON' : 0,'ScaleFactor' : 0.4}, #Virtual LED which mixes LEDB and LEDI. ScaleFactor is something to balance between the LED intensites being combined if you want to tune the spectra. Could tune this if you want to get a specific white spectrum blue balance.
   'LASER650' : {'name' : 'LASER650', 'default': 0.5, 'target' : 0.0, 'max': 1.0, 'min' : 0.0,'ON' : 0},
   'UV' : {'WL' : 'UV', 'default': 0.5, 'target' : 0.0, 'max': 1.0, 'min' : 0.0,'ON' : 0},
   'Heat' : {'default': 0.0, 'target' : 0.0, 'max': 1.0, 'min' : 0.0,'ON' : 0,'record' : []},
   'Thermostat' : {'default': 37.0, 'target' : 0.0, 'max': 50.0, 'min' : 0.0,'ON' : 0,'record' : [],'cycleTime' : 30.0, 'Integral' : 0.0,'last' : -1},
   'Experiment' : {'indicator' : 'USR0', 'startTime' : 'Waiting', 'startTimeRaw' : 0, 'ON' : 0,'cycles' : 0, 'cycleTime' : 60.0,'threadCount' : 0},
   'Terminal' : {'text' : ''},
   'AS7341' : {
        'spectrum' : {'nm410' : 0, 'nm440' : 0, 'nm470' : 0, 'nm510' : 0, 'nm550' : 0, 'nm583' : 0, 'nm620' : 0, 'nm670' : 0,'CLEAR' : 0, 'NIR' : 0,'DARK' : 0,'ExtGPIO' : 0, 'ExtINT' : 0, 'FLICKER' : 0},
        'channels' : {'nm410' : 0, 'nm440' : 0, 'nm470' : 0, 'nm510' : 0, 'nm550' : 0, 'nm583' : 0, 'nm620' : 0, 'nm670' : 0,'CLEAR' : 0, 'NIR' : 0,'DARK' : 0,'ExtGPIO' : 0, 'ExtINT' : 0, 'FLICKER' : 0},
        'current' : {'ADC0': 0,'ADC1': 0,'ADC2': 0,'ADC3': 0,'ADC4': 0,'ADC5' : 0}},
   'ThermometerInternal' : {'current' : 0.0,'record' : []},
   'ThermometerExternal' : {'current' : 0.0,'record' : []},
   'ThermometerIR' : {'current' : 0.0,'record' : []},
   'OD' :  {'current' : 0.0,'target' : 0.5,'default' : 0.5,'max': 10, 'min' : 0,'record' : [],'targetrecord' : [],'Measuring' : 0, 'ON' : 0,'Integral' : 0.0,'Integral2' : 0.0,'device' : 'LASER650'},
   'OD0' : {'target' : 0.0,'raw' : 0.0,'max' : 100000.0,'min': 0.0,'LASERb' : 1.833 ,'LASERa' : 0.226, 'LEDFa' : 0.673, 'LEDAa' : 7.0  },
   'Chemostat' : {'ON' : 0, 'p1' : 0.0, 'p2' : 0.1},
   'Zigzag': {'ON' : 0, 'Zig' : 0.04,'target' : 0.0,'SwitchPoint' : 0},
   'GrowthRate': {'current' : 0.0,'record' : [],'default' : 2.0},
   'Volume' : {'target' : 20.0,'max' : 50.0, 'min' : 0.0,'ON' : 0},
   'Pump1' :  {'target' : 0.0,'default' : 0.0,'max': 1.0, 'min' : -1.0, 'direction' : 1.0, 'ON' : 0,'record' : [], 'thread' : 0},
   'Pump2' :  {'target' : 0.0,'default' : 0.0,'max': 1.0, 'min' : -1.0, 'direction' : 1.0, 'ON' : 0,'record' : [], 'thread' : 0},
   'Pump3' :  {'target' : 0.0,'default' : 0.0,'max': 1.0, 'min' : -1.0, 'direction' : 1.0, 'ON' : 0,'record' : [], 'thread' : 0},
   'Pump4' :  {'target' : 0.0,'default' : 0.0,'max': 1.0, 'min' : -1.0, 'direction' : 1.0, 'ON' : 0,'record' : [], 'thread' : 0},
   'Stir' :  {'target' : 0.0,'default' : 0.5,'max': 1.0, 'min' : 0.0, 'ON' : 0},
   'Light' :  {'target' : 0.0,'default' : 0.5,'max': 1.0, 'min' : 0.0, 'ON' : 0, 'Excite' : 'LEDD', 'record' : []},
   'Custom' :  {'Status' : 0.0,'default' : 0.0,'Program': 'C1', 'ON' : 0,'param1' : 0, 'param2' : 0, 'param3' : 0.0, 'record' : []},
   'FP1' : {'ON' : 0 ,'LED' : 0,'BaseBand' : 0, 'Emit1Band' : 0,'Emit2Band' : 0,'Base' : 0, 'Emit1' : 0,'Emit2' : 0,'BaseRecord' : 0, 'Emit1Record' : 0,'Emit2Record' : 0 ,'Gain' : 0},
   'FP2' : {'ON' : 0 ,'LED' : 0,'BaseBand' : 0, 'Emit1Band' : 0,'Emit2Band' : 0,'Base' : 0, 'Emit1' : 0,'Emit2' : 0,'BaseRecord' : 0, 'Emit1Record' : 0,'Emit2Record' : 0 ,'Gain' : 0},
   'FP3' : {'ON' : 0 ,'LED' : 0,'BaseBand' : 0, 'Emit1Band' : 0,'Emit2Band' : 0,'Base' : 0, 'Emit1' : 0,'Emit2' : 0,'BaseRecord' : 0, 'Emit1Record' : 0,'Emit2Record' : 0 ,'Gain' : 0},
   'biofilm' : {'LEDA' : {'nm410' : 0, 'nm440' : 0, 'nm470' : 0, 'nm510' : 0, 'nm550' : 0, 'nm583' : 0, 'nm620' : 0, 'nm670' : 0,'CLEAR' : 0,'NIR' : 0},
                'LEDB' : {'nm410' : 0, 'nm440' : 0, 'nm470' : 0, 'nm510' : 0, 'nm550' : 0, 'nm583' : 0, 'nm620' : 0, 'nm670' : 0,'CLEAR' : 0,'NIR' : 0},
                'LEDC' : {'nm410' : 0, 'nm440' : 0, 'nm470' : 0, 'nm510' : 0, 'nm550' : 0, 'nm583' : 0, 'nm620' : 0, 'nm670' : 0,'CLEAR' : 0,'NIR' : 0},
                'LEDD' : {'nm410' : 0, 'nm440' : 0, 'nm470' : 0, 'nm510' : 0, 'nm550' : 0, 'nm583' : 0, 'nm620' : 0, 'nm670' : 0,'CLEAR' : 0,'NIR' : 0},
                'LEDE' : {'nm410' : 0, 'nm440' : 0, 'nm470' : 0, 'nm510' : 0, 'nm550' : 0, 'nm583' : 0, 'nm620' : 0, 'nm670' : 0,'CLEAR' : 0,'NIR' : 0},
                'LEDF' : {'nm410' : 0, 'nm440' : 0, 'nm470' : 0, 'nm510' : 0, 'nm550' : 0, 'nm583' : 0, 'nm620' : 0, 'nm670' : 0,'CLEAR' : 0,'NIR' : 0},
                'LEDG' : {'nm410' : 0, 'nm440' : 0, 'nm470' : 0, 'nm510' : 0, 'nm550' : 0, 'nm583' : 0, 'nm620' : 0, 'nm670' : 0,'CLEAR' : 0,'NIR' : 0},
                'LASER650' : {'nm410' : 0, 'nm440' : 0, 'nm470' : 0, 'nm510' : 0, 'nm550' : 0, 'nm583' : 0, 'nm620' : 0, 'nm670' : 0,'CLEAR' : 0,'NIR' : 0}}
   }}


# SysDevices is unique to each device and is responsible for storing information
# required for the digital communications, and various automation funtions. These
# values are stored outside sysData since they are not passable into the HTML
# interface using the jsonify package.
sysDevices = {'M0' : {
    'AS7341' : {'device' : 0},
    'ThermometerInternal' : {'device' : 0},
    'ThermometerExternal' : {'device' : 0},
    'ThermometerIR' : {'device' : 0,'address' :0},
    'DAC' : {'device' : 0},
    'Pumps' : {'device' : 0,'startup' : 0, 'frequency' : 0},
    'PWM' : {'device' : 0,'startup' : 0, 'frequency' : 0},
    'Pump1' : {'thread' : 0,'threadCount' : 0, 'active' : 0, 'running' : 0},
    'Pump2' : {'thread' : 0,'threadCount' : 0, 'active' : 0, 'running' : 0},
    'Pump3' : {'thread' : 0,'threadCount' : 0, 'active' : 0, 'running' : 0},
    'Pump4' : {'thread' : 0,'threadCount' : 0, 'active' : 0, 'running' : 0},
    'Experiment' : {'thread' : 0, 'running' : 0},
    'Thermostat' : {'thread' : 0,'threadCount' : 0, 'running' : 0},

}}


for M in ['M1','M2','M3','M4','M5','M6','M7']:
        sysData[M]=copy.deepcopy(sysData['M0'])
        sysDevices[M]=copy.deepcopy(sysDevices['M0'])


# sysItems stores information about digital addresses which is used as a reference
# for all devices.
sysItems = {
    'Multiplexer' : {'device' : 0 , 'M0' : '00000001','M1' : '00000010','M2' : '00000100','M3' : '00001000','M4' : '00010000','M5' : '00100000','M6' : '01000000','M7' : '10000000'},
    'UIDevice' : 'M0',
    'Watchdog' : {'pin' : 'P8_11','thread' : 0,'ON' : 1},
    'FailCount' : 0,
    'All' : {'ONL' : 0xFA, 'ONH' : 0xFB, 'OFFL' : 0xFC, 'OFFH' : 0xFD},
    'Stir' : {'ONL' : 0x06, 'ONH' : 0x07, 'OFFL' : 0x08, 'OFFH' : 0x09},
    'Heat' : {'ONL' : 0x3E, 'ONH' : 0x3F, 'OFFL' : 0x40, 'OFFH' : 0x41},
    'UV' : {'ONL' : 0x42, 'ONH' : 0x43, 'OFFL' : 0x44, 'OFFH' : 0x45},
    'LEDA' : {'ONL' : 0x0E, 'ONH' : 0x0F, 'OFFL' : 0x10, 'OFFH' : 0x11},# Only Led1
    'LEDB' : {'ONL' : 0x16, 'ONH' : 0x17, 'OFFL' : 0x18, 'OFFH' : 0x19},#Both LEDs common
    'LEDC' : {'ONL' : 0x0A, 'ONH' : 0x0B, 'OFFL' : 0x0C, 'OFFH' : 0x0D},#Both LEDs common
    'LEDD' : {'ONL' : 0x1A, 'ONH' : 0x1B, 'OFFL' : 0x1C, 'OFFH' : 0x1D},#Both LEDs Common
    'LEDE' : {'ONL' : 0x22, 'ONH' : 0x23, 'OFFL' : 0x24, 'OFFH' : 0x25},#Only Led1
    'LEDF' : {'ONL' : 0x1E, 'ONH' : 0x1F, 'OFFL' : 0x20, 'OFFH' : 0x21},#Both LEDs Common
    'LEDG' : {'ONL' : 0x12, 'ONH' : 0x13, 'OFFL' : 0x14, 'OFFH' : 0x15},#Only Led1
    'LEDH' : {'ONL' : 0x26, 'ONH' : 0x27, 'OFFL' : 0x28, 'OFFH' : 0x29},#Only Led2
    'LEDI' : {'ONL' : 0x2E, 'ONH' : 0x2F, 'OFFL' : 0x30, 'OFFH' : 0x31},#Only Led2
    'LEDJ' : {'ONL' : 0x36, 'ONH' : 0x37, 'OFFL' : 0x38, 'OFFH' : 0x39},#Only Led2 - same colour as LEDI so current not used.
    'Pump1' : {
        'In1' : {'ONL' : 0x06, 'ONH' : 0x07, 'OFFL' : 0x08, 'OFFH' : 0x09},
        'In2' : {'ONL' : 0x0A, 'ONH' : 0x0B, 'OFFL' : 0x0C, 'OFFH' : 0x0D},
    },
    'Pump2' : {
        'In1' : {'ONL' : 0x0E, 'ONH' : 0x0F, 'OFFL' : 0x10, 'OFFH' : 0x11},
        'In2' : {'ONL' : 0x12, 'ONH' : 0x13, 'OFFL' : 0x14, 'OFFH' : 0x15},
    },
    'Pump3' : {
        'In1' : {'ONL' : 0x16, 'ONH' : 0x17, 'OFFL' : 0x18, 'OFFH' : 0x19},
        'In2' : {'ONL' : 0x1A, 'ONH' : 0x1B, 'OFFL' : 0x1C, 'OFFH' : 0x1D},
    },
    'Pump4' : {
        'In1' : {'ONL' : 0x1E, 'ONH' : 0x1F, 'OFFL' : 0x20, 'OFFH' : 0x21},
        'In2' : {'ONL' : 0x22, 'ONH' : 0x23, 'OFFL' : 0x24, 'OFFH' : 0x25},
    },
    'AS7341' : {
        '0x00' : {'A' : 'nm470', 'B' : 'U'},
        '0x01' : {'A' : 'U', 'B' : 'nm410'},
        '0x02' : {'A' : 'U', 'B' : 'U'},
        '0x03' : {'A' : 'nm670', 'B' : 'U'},
        '0x04' : {'A' : 'U', 'B' : 'nm583'},
        '0x05' : {'A' : 'nm510', 'B' : 'nm440'},
        '0x06' : {'A' : 'nm550', 'B' : 'U'},
        '0x07' : {'A' : 'U', 'B' : 'nm620'},
        '0x08' : {'A' : 'CLEAR', 'B' : 'U'},
        '0x09' : {'A' : 'nm550', 'B' : 'U'},
        '0x0A' : {'A' : 'U', 'B' : 'nm620'},
        '0x0B' : {'A' : 'U', 'B' : 'U'},
        '0x0C' : {'A' : 'nm440', 'B' : 'U'},
        '0x0D' : {'A' : 'U', 'B' : 'nm510'},
        '0x0E' : {'A' : 'nm583', 'B' : 'nm670'},
        '0x0F' : {'A' : 'nm470', 'B' : 'U'},
        '0x10' : {'A' : 'ExtGPIO', 'B' : 'nm410'},
        '0x11' : {'A' : 'CLEAR', 'B' : 'ExtINT'},
        '0x12' : {'A' : 'DARK', 'B' : 'U'},
        '0x13' : {'A' : 'FLICKER', 'B' : 'NIR'},
    }
}
