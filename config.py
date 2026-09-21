# Sunflower config

TIMEZONE = 1 # Hours to UTC (positive or negative number)
DST = True # Enable automatic DST time setting.
NTP_HOST = "europe.pool.ntp.org" # NTP timeserver hostname
IP_PV = "XXX.XXX.XXX.XXX" # IP or hostname pv inverter Fronius
IP_WB = "XXX.XXX.XXX.XXX" # IP or hostname go-e charger
CAR_BAT_SIZE = 50 # Car battery maximum capacity in kWh, used for percentage calculation
I_MIN = 6 # Minimum charging current for car in ampere (usually 6 A)
I_MAX = 16 # Maximum charging current allowed, electric installation and charger type. 16 A is for 11 kW charger.
I_MAX_1P = 16 # Maximum current limit for 1 phase, set to country limit if less than I_MAX
WB_METERED = True # True if the wallbox power is included in the grid meter power value. Depends on meter wiring in electric setup.
CYCLE = 6 # Seconds to wait between cycles while charging (how close to follow the power generation)
WAIT = 60 # Seconds to wait if there is no pv power or no car connected
WAIT_PHASE_CHANGE = 15 # Seconds to wait after phase change: May be removed if future
SHORT_CYCLES = 6 # Number of program cycles to use for average calculation of short period grid power: Equals 36 s with default 6 s CYCLE
LONG_CYCLES = 20 # Number of program cycles to use for average calculation of long period grid power: Equals 120 s with default 6 s CYCLE
SCREEN_REFRESH = 120 # Seconds between badger screen updates (not used for status updates e.g. phase change)
# Power values defined below are negative for excess pv and positive for grid consumption
SWITCH_OFF = -600 # Power threshold in W to stop charging when average of LONG_CYCLE is above (less power available), default allows up to 400 W grid consumption.
