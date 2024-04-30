# PV car charge - Fronius + go-e
# Martin Augustin
# 240430

# Import modules
import badger2040
from badger2040 import WIDTH
from machine import freq, RTC, Timer, WDT, reset
import time, ntptime
from async_urequests import urequests as requests
import gc
gc.enable()
import config # Import settings from config file

# Constants declaration
URL_PV = "http://"+config.IP_PV+"/solar_api/v1/GetPowerFlowRealtimeData.fcgi"
URL_WB = "http://"+config.IP_WB+"/api/status?filter=alw,amp,car,dwo,frc,nrg,psm,tpa,wh"
URL_WB_SET = "http://"+config.IP_WB+"/api/set?"
OFFSET = 0.05 * config.CAR_BAT_SIZE

# Variable declaration
ntptime.host = config.NTP_HOST
cycle = config.CYCLE
list_grid = [] # List average grid power
ampere = [0, 0] # Initialize list current calculation
screen_update = 0 # Last screen refresh


def failsafe_wlan(): # Connect to WLAN and reboot if not successful
    try:
        print("Connect to WLAN")
        display.connect()
        if display.isconnected():
            ntptime.settime()
            badger2040.pico_rtc_to_pcf()
    except (RuntimeError, OSError) as e:
        print(f"Wireless Error: {e.value}")
        time.sleep_ms(3000)
        reset()
        

def time_dst(timezone, dst): # Local time with dst function
    now=time.time()
    if dst:
        year = time.localtime()[0]       #get current year
        HMarch   = time.mktime((year,3 ,(31-(int(5*year/4+4))%7),1,0,0,0,0,0)) #Time of March change to CEST
        HOctober = time.mktime((year,10,(31-(int(5*year/4+1))%7),1,0,0,0,0,0)) #Time of October change to CET
        if HMarch < now < HOctober:               
            return time.localtime(now+timezone*7200) # CEST:  UTC+TIMEZONE HOURS + 1 HOUR
    else:                            
        return time.localtime(now+timezone*3600) # CET:  UTC+TIMEZONE HOURS
    
    
def get_data(url,wait):
    """Get data from inverter, wallbox, meter, or battery"""
    try:
        r = requests.get(url, timeout=wait)
    except:
        print("No response from ", url)
        return False
    else:
        r.close()
        return r.json()


def grid():
    """Get current grid power"""
    r = 0
    if data_pv:
        try:
            r = int(data_pv['Body']['Data']['Site']['P_Grid'])
        except:
            print("No P_Grid value from inverter")
            pass
    return r


def wb(key):
    """Get data from wallbox response"""
    if not data_wb:
        return False
    elif key == 'P_wb':
        return data_wb['nrg'][11]
    elif key == 'I_wb':
        return data_wb['amp']
    elif key == 'U_wb':
        return [data_wb['nrg'][0], data_wb['nrg'][1], data_wb['nrg'][2]]
    elif key == '1p3p':
        return 3 if data_wb['psm'] == 2 else data_wb['psm']
    elif key == 'car':
        return data_wb['car']
    elif key == 'allow' :
        return data_wb['alw']
    elif key == 'energy':
        return int(data_wb['wh'])/1000 if data_wb['wh'] else 0
    elif key == 'frc' :
        return data_wb['frc']
    elif key == 'tpa' :
        return int(data_wb['tpa'])
    elif key == 'dwo' :
        return int(data_wb['dwo'])/1000 if data_wb['dwo'] else 0
    else:
        return False

        
def calc_I(power,last):
    """Calculate currents 1p and 3p for max pv usage"""
    I_1p, I_3p = config.I_MIN, config.I_MIN
    if power != 0 and wb('P_wb'):
        if power < config.P_MIN_3P:
            I_1p = config.I_MAX_1P
            I_3p = min(abs(power)//sum(wb('U_wb')), config.I_MAX)
        elif power < config.P_MIN_1P:
            I_1p = min(abs(power)//wb('U_wb')[0], config.I_MAX_1P)
            I_3p = config.I_MIN
    return [I_1p, I_3p, I_1p-last[0] != 1, I_3p-last[1] != 1]


def set_wb(settings):
    """Set go-e parameters"""
    try:
        r = requests.get(URL_WB_SET, params=settings, timeout=1)
    except:
        print("No response from ",URL_WB_SET, settings)
        return False
    else:
        r.close()
        return r.json()

    
def average(data, list):
    short, long = None, None
    list.append(data)
    rounds = len(list)    
    if rounds >= config.SHORT_CYCLES:
        short = round(sum(list[rounds-config.SHORT_CYCLES:rounds])/config.SHORT_CYCLES)
    if rounds >= config.LONG_CYCLES:
        long = round(sum(list)/config.LONG_CYCLES)
        list.pop(0)
    return [short, long] # [average last #SHORT_CYCLES loops, average last #LONG_CYCLES loops]


def update_screen():
    global screen_update
    refresh = time.time()-screen_update
    if refresh > config.SCREEN_REFRESH:
        localtime = time_dst(config.TIMEZONE,config.DST)
        update = "{:02d}.{:02d}.{} {:02d}:{:02d}:{:02d}".format(localtime[2], localtime[1], localtime[0], localtime[3], localtime[4], localtime[5])
        print("Last screen update:", update)
        display.set_pen(0)
        display.rectangle(98, 0, WIDTH, 20)
        display.set_font("bitmap6")
        display.set_pen(15)
        display.text(update, 105, 3)
        display.set_pen(0)
        display.line(0, 55, 95, 55)
        display.text("+", WIDTH-10, 25)
        display.text("-", WIDTH-10, 88)
        display.line(WIDTH-8, 45, WIDTH-8, 80)
        display.line(WIDTH-15, 65, WIDTH-8, 65)
        display.set_font("bitmap8")
        display.update()
        screen_update = time.time()
        gc.collect()
        
        
def feed_wdt(timer):
    wdt.feed()
 
display = badger2040.Badger2040()
display.set_update_speed(2) 
if not display.isconnected():
    failsafe_wlan()
print("Start program PV charge")
# Watchdog timer for auto reboot if program stopped
wdt = WDT(timeout=8000)
feed_timer = Timer(mode=Timer.PERIODIC, period=7500, callback=feed_wdt)
         
while 1: # Loop forever
    freq(125000000) # Normal CPU freq for fast execusion
    if not display.isconnected(): # Check if connected
        failsafe_wlan()
    tstart = time.ticks_ms() # Start time measurement
    display.led(25) # LED on during cycle
    # Clear the display
    display.set_pen(15)
    display.clear()
    display.set_pen(0)
    display.set_font("bitmap8")
    data_pv = get_data(URL_PV, 2) # Get grid power
    data_wb = get_data(URL_WB, 2) # Get wallbox values
    if wb('P_wb') is not False and config.WB_METERED:
        P_Grid = grid()-wb('P_wb')
    else:
        P_Grid = grid()
    grid_average = average(P_Grid,list_grid)
    if data_pv: # Received data from pv inverter
        print("P_Grid:", P_Grid, "W")
        display.text("PV", 40, 5)
        display.text(str(grid_average[0] if grid_average[0] is not None else P_Grid) + " W", 65-10*len(str(grid_average[0])), 30)
    else: # No pv data
        print("PV offline")
        display.text("PV", 40, 5)
        display.text("offline", 15, 30)     
    if data_wb: # Received data from wallbox
        P_wb = wb('P_wb')
        P_wba = min(P_wb,wb('tpa'))
        phases = wb('1p3p')
        allow = wb('allow')
        energy = wb('energy')
        percent_energy = energy/config.CAR_BAT_SIZE
        limit = wb('dwo')
        if display.pressed(badger2040.BUTTON_UP): # Increase energy limit equal 5% battery capacity
            limit_new = (limit+OFFSET)*1000
            r = set_wb({'dwo':limit_new})
            print(f"Set limit to: {limit_new}")
            limit = limit_new/1000
            screen_update = 0
        if display.pressed(badger2040.BUTTON_DOWN): # Decrease energy limit equal 5% battery capacity
            if limit > OFFSET:
                limit_new = (limit-OFFSET)*1000
                r = set_wb({'dwo':limit_new})
                print(f"Set limit to: {limit_new}")
                limit = limit_new/1000
                screen_update = 0
        percent_limit = limit/config.CAR_BAT_SIZE
        print(f"P_WB:   {P_wb} W ({phases} phases)\n"+
        f"Allow: {allow}\n"+
        f"Energy charged: {energy:.2f} kWh ({percent_energy:.0%})\n"+
        f"Limit: {limit:.2f} kWh ({percent_limit:.0%})\n"+
        f"Average P_Grid: {grid_average}")
        display.text(f"{P_wba} W", 65-10*len(str(P_wba)), 65)
        display.text("WB", 15, 89)
        display.rectangle(55, 85, 35, 22)
        display.set_pen(15)
        display.text(f"{phases} P", 60, 89)
        display.set_pen(0)
        display.text(f"{energy:.2f} kWh ({percent_energy:.0%})", 105, 30)
        display.text(f"{limit:.1f} kWh max. ({percent_limit:.0%})", 105, 60)
        if allow and wb('car') == 2 and P_Grid != 0:
            display.text("Charging", 105, 90)
            cycle = config.CYCLE
            ampere = calc_I(P_Grid, ampere)
            if phases == 1:
                if wb('I_wb') != ampere[0] and ampere[2]:
                    r = set_wb({'amp':ampere[0]})
                    print("Set current to", ampere[0],"A ... ", r)
                if grid_average[1] is not None and max(P_Grid, grid_average[1], grid_average[0]) < config.SWITCH_3P:
                    r = set_wb({'psm':'2', 'amp':ampere[1]})
                    print("Phase change to 3 phases ... ",r)
                    display.text("-> 3P", 190, 90)
                    cycle = config.WAIT_PHASE_CHANGE
                    screen_update = 0
            elif phases == 3:
                if wb('I_wb') != ampere[1] and ampere[3]:
                    r = set_wb({'amp':ampere[1]})
                    print("Set current to", ampere[1],"A ... ", r)
                if grid_average[1] is not None and min(P_Grid, grid_average[1]) > config.SWITCH_1P:
                    r = set_wb({'psm':'1','amp':ampere[0]})
                    print("Phase change to 1 phase ... ", r)
                    display.text("-> 1P", 190, 90)
                    cycle = config.WAIT_PHASE_CHANGE
                    screen_update = 0     
        # Stop charging 
        if wb('frc') == 0 and grid_average[1] is not None and min(P_Grid, grid_average[1]) > config.SWITCH_OFF and wb('car') == 2:
            r = set_wb({'amp':'6', 'psm':'1', 'frc':'1'}) # Set min charge power, 1 phase and switch off
            print("Stop charging ... ",r)
            display.text("Charging stop", 105, 90)
            screen_update = 0
        # Start charging
        elif wb('frc') == 1 and grid_average[1] is not None and grid_average[1] < config.SWITCH_ON and wb('car') > 2:
            r = set_wb({'frc':'0'})
            print("Allow charging ... ",r)
            display.text("Allow charging", 105, 90)
            screen_update = 0
            cycle = config.CYCLE
        # Large cycle when no car or full
        if wb('car') == 1:
            display.text("No car.", 105, 90)
            print(f"Wait {config.WAIT/60: 0.1f} min, no car.")
            if cycle != config.WAIT:
                cycle = config.WAIT
                screen_update = 0

    else: # No wallbox data
        print("Wallbox offline")
        display.text("WB", 40, 89)
        display.text("offline", 15, 65)
        
    if (P_Grid >= 0 and grid_average[0] is not None and grid_average[0] >= 0):
        cycle = config.WAIT
        print(f"Wait {config.WAIT/60: 0.1f} min, no PV surplus.")
        screen_update = 0
    
    time_thread = time.ticks_diff(time.ticks_ms(),tstart) # Finish time measurement
    print(f"It took{time_thread/1000: 0.3f} second(s) to complete.")
    display.led(0) # LED off after logic cycle
    wdt.feed()
    update_screen()
    pause_program = max(abs(cycle*1000-time_thread), 500)
    print (f"Sleep for{pause_program/1000: 0.3f} seconds.\n")
    freq(66000000) # Reduce CPU freq during sleep time
    time.sleep_ms(pause_program)