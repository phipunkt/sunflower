# Sunflower config

TIMEZONE = 1 # Number of hours difference between UTC (+ or -)
DST = True # If True, enable automatic DST time setting
IP_PV = "xxx.xxx.xxx.xxx" # IP or hostname pv inverter Fronius
IP_WB = "xxx.xxx.xxx.xxx" # IP or hostname go-e charger
I_MIN = 6 # Min charging current for car
I_MAX = 16 # Max charging current
I_MAX_1P = 16 # Set to country limit if less than I_MAX
WB_METERED = False # Is the wallbox included in grid meter power value?
CYCLE = 6 # Seconds to wait between cycles while charging
WAIT = 60 # Seconds to wait if no pv or no car
WAIT_PHASE_CHANGE = 15 # Seconds to wait after phase change
SHORT_CYCLES = 6 # Short average over given cycles, is 36s with default 6s cycle
LONG_CYCLES = 20 # Long average over given cycles, is 120s with default 6s cycle
SCREEN_REFRESH = 120 # Seconds between badger screen updates (not used for status updates e.g. phase change)
# Power values defined below are negative for excess pv and positive for from grid
P_MIN_1P = -1440 # Min power for 1p charging (I_MIN x U max)
P_MIN_3P = -4320 # Min power for 3p charging (I_MIN x U max)
SWITCH_3P = -4200 # Threshold to switch for 3 phase charging
SWITCH_1P = -3800 # Threshold to switch for 1 phase charging
SWITCH_ON = -1300 # Threshold to enable charging when average of LONG_CYCLES is below (more power)
SWITCH_OFF = -900 # Threshold to stop charging when average of LONG_CYCLE is above (less power)
