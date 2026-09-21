# PV car charge - Fronius + go-e
# Martin Augustin
# 260921

# Import modules
import gc
import time

import async_urequests as requests
import badger2040
import config  # Import settings from config file
import ntptime
import uasyncio as asyncio
from async_urequests import TimeoutError, ConnectionError
from badger2040 import WIDTH
from machine import freq, WDT, reset, Pin
from micropython import schedule
from pcf85063a import PCF85063A
from pimoroni_i2c import PimoroniI2C


# Constants declaration
URL_PV = "http://" + config.IP_PV + "/solar_api/v1/GetPowerFlowRealtimeData.fcgi"
URL_WB = (
    "http://" + config.IP_WB + "/api/status?filter=alw,amp,car,dwo,frc,fst,fup,lmo,nrg,psm,tpa,wh"
)
URL_WB_SET = "http://" + config.IP_WB + "/api/set?"
OFFSET = 0.05 * config.CAR_BAT_SIZE
P_MIN_1P = -1440 # Minimum power in W for 1p charging ampere calculation
P_MIN_3P = -4320 # Minimum power in W for 3p charging ampere calculation
SWITCH_3P = -4200 # Power threshold in W to switch for 3 phase charging
SWITCH_1P = -3800 # Power threshold in W to switch for 1 phase charging

button_a = Pin(badger2040.BUTTON_A, Pin.IN, Pin.PULL_DOWN)
button_b = Pin(badger2040.BUTTON_B, Pin.IN, Pin.PULL_DOWN)
button_c = Pin(badger2040.BUTTON_C, Pin.IN, Pin.PULL_DOWN)
button_up = Pin(badger2040.BUTTON_UP, Pin.IN, Pin.PULL_DOWN)
button_down = Pin(badger2040.BUTTON_DOWN, Pin.IN, Pin.PULL_DOWN)

# Variable declaration
ntptime.host = config.NTP_HOST
cycle = config.CYCLE
list_grid = []  # List average grid power
ampere = [0, 0]  # Initialize list current calculation
screen_update = 0  # Last screen refresh

i2c = PimoroniI2C(sda=4, scl=5)
rtc = PCF85063A(i2c)
i2c.writeto_mem(0x51, 0x00, b"\x00")  # ensure rtc is running


def failsafe_wlan():
    """Connect to WLAN and reboot if not successful"""
    print("Connect to WLAN")
    try:
        display.connect()
    except (RuntimeError, OSError) as e:
        print(f"Wireless Error: {e}")
        time.sleep_ms(3000)
        reset()


def datetime_dst(timezone, dst):
    """Get time with timezone and EU daylight saving time"""
    global HMar, HOct
    now = time.mktime(rtc.datetime() + (0, 0))
    if dst:
        if HMar <= now < HOct:
            timezone += 1  # CEST: Add 1 hour
    return time.localtime(now + timezone * 3600)  # CET:  UTC+TIMEZONE hours


def rtc_timestamp():
    return time.mktime(rtc.datetime() + (0, 0))


async def get_data(url, wait):
    """Get data from inverter, wallbox, meter, or battery"""
    r = None
    try:
        r = await requests.get(url, timeout=wait)
        return r.json()
    except ConnectionError as e:
        print("Request error:", url, e)
        return False
    except TimeoutError:
        print(f"Timeout of {wait} s:", url)
        return False
    except Exception as e:
        print("Response error:", url, e)
        return False
    finally:
        if r is not None:
            r.close()


async def get_pv_and_wb():
    """Request inverter and wallbox in parallel"""
    pv_task = asyncio.create_task(get_data(URL_PV, 2.5))
    wb_task = asyncio.create_task(get_data(URL_WB, 2.5))
    wdt.feed()
    data_pv, data_wb = await asyncio.gather(pv_task, wb_task)
    wdt.feed()
    return data_pv, data_wb


def get_inverter_values(data):
    """Get data from inverter"""
    r_grid = 0
    r_pv = 0
    if not data:
        return 0, 0
    try:
        r_grid = int(data["Body"]["Data"]["Site"]["P_Grid"])
    except:
        print("No P_Grid value from inverter")
        pass
    try:
        r_pv = int(data["Body"]["Data"]["Site"]["P_PV"])
    except:
        print("No P_PV value from inverter")
        pass
    return r_grid, r_pv


def get_wb_values(data):
    if not data:
        return False
    try:
        return (
            data["amp"],  # I_wb: Charge current
            data["nrg"][:3],  # U_wb: Phase voltages
            3 if data["psm"] == 2 else data["psm"],  # 1p3p: 1 or 3 phase charge
            data["car"],  # car: Car status
            data["alw"],  # allow: Charging allowed?
            int(data["wh"]) / 1000 if data["wh"] else 0,  # energy: Energy charged
            data["frc"],  # frc: Force charging state
            int(min(data["nrg"][11], data["tpa"])),  # P_wba: min(charge power,30s avg)
            data["dwo"] / 1000 if data["dwo"] else 0,  # limit: Charge energy limit
            data["fup"] and data["lmo"] == 3,  # PVmode: PV surplus and State charge mode
            -data["fst"],  # switchOn: PV starting power
        )
    except (KeyError, IndexError, TypeError, ValueError):
        return False


def calc_I(power, last, P_wb, U_wb):
    """Calculate currents 1p and 3p for max pv usage"""
    I_1p, I_3p = config.I_MIN, config.I_MIN
    if power != 0 and P_wb:
        if power < P_MIN_3P:
            I_1p = config.I_MAX_1P
            I_3p = int(min(abs(power) // sum(U_wb), config.I_MAX))
        elif power < P_MIN_1P:
            I_1p = int(min(abs(power) // U_wb[0], config.I_MAX_1P))
            I_3p = config.I_MIN
    return [I_1p, I_3p, I_1p - last[0] != 1, I_3p - last[1] != 1]


async def set_wb_async(settings):
    """Set go-e parameters"""
    r = None
    wdt.feed()
    try:
        r = await requests.get(URL_WB_SET, params=settings, timeout=1.5)
        return r.json()
    except TimeoutError:
        print("Timeout from: ", URL_WB_SET, settings)
        return False
    except Exception as e:
        print("Error connecting to ", URL_WB_SET, settings, e)
        return False
    finally:
        wdt.feed()
        if r is not None:
            r.close()


def set_wb(settings):
    """Synchronos wrapper"""
    try:
        return asyncio.run(set_wb_async(settings))
    except:
        return False


def average(data, list):
    """Average data over two time spans"""
    short, long = None, None
    list.append(data)
    rounds = len(list)
    if rounds >= config.SHORT_CYCLES:
        short = round(sum(list[rounds - config.SHORT_CYCLES : rounds]) / config.SHORT_CYCLES)
    if rounds >= config.LONG_CYCLES:
        long = round(sum(list) / config.LONG_CYCLES)
        list.pop(0)
    return [short, long]  # Average last loops: [#SHORT_CYCLES, #LONG_CYCLES]


def update_screen():
    """Update epaper display when triggered or time elapsed"""
    global screen_update
    global lastboot
    wdt.feed()
    refresh = rtc_timestamp() - screen_update
    if refresh > config.SCREEN_REFRESH:
        t = datetime_dst(config.TIMEZONE, config.DST)
        update = f"{t[2]:02d}.{t[1]:02d}.{t[0]} {t[3]:02d}:{t[4]:02d}:{t[5]:02d}"
        print("Last screen update:", update)
        display.set_pen(0)
        display.rectangle(98, 0, WIDTH, 20)
        display.set_font("bitmap6")
        display.set_pen(15)
        display.text(update, 105, 3)
        display.set_pen(0)
        display.line(0, 50, 95, 50)
        display.text("+", WIDTH - 10, 25)
        display.text("-", WIDTH - 10, 88)
        display.line(WIDTH - 8, 45, WIDTH - 8, 80)
        display.line(WIDTH - 15, 62, WIDTH - 8, 62)
        display.text(lastboot, 105, 108)
        display.set_font("bitmap8")
        wdt.feed()
        display.update()
        screen_update = rtc_timestamp()


def button_up_irq(pin):
    button_up.irq(handler=None)
    button_down.irq(handler=None)
    schedule(change_limit, 1)


def button_down_irq(pin):
    button_up.irq(handler=None)
    button_down.irq(handler=None)
    schedule(change_limit, 0)


def change_limit(button_id):
    """Change charge energy limit when button UP or DOWN pressed"""
    global limit
    button = button_up if button_id else button_down
    try:
        time.sleep_ms(100)  # Time based debounce
        if button.value():
            return  # Not pressed
        if button_id:
            # Increase energy limit equal 5% battery capacity
            limit_new = int((limit + OFFSET) * 1000)
        else:
            if limit <= OFFSET:
                return
            # Decrease energy limit equal 5% battery capacity
            limit_new = int((limit - OFFSET) * 1000)
        # Long time for answer, will mostly timeout, no check for result
        set_wb({"dwo": limit_new})
        print(f"Set limit to: {limit_new}")
        limit = limit_new / 1000
        percent_limit = limit / config.CAR_BAT_SIZE
        display.set_pen(15)
        display.rectangle(98, 54, WIDTH - 15, 25)
        display.set_pen(0)
        display.text(f"{limit:.1f} kWh max. ({percent_limit:.0%})", 105, 55)
        display.partial_update(100, 48, WIDTH - 15, 32)
    except:
        pass
    finally:  # Enable button IRQ
        button_up.irq(trigger=Pin.IRQ_FALLING, handler=button_up_irq)
        button_down.irq(trigger=Pin.IRQ_FALLING, handler=button_down_irq)


def watchdog_sleep_ms(duration):
    """Sleep while keeping watchdog alive"""
    CHUNK_MS = 5000
    wdt.feed()
    while duration > 0:
        chunk = min(duration, CHUNK_MS)
        time.sleep_ms(chunk)
        wdt.feed()
        duration -= chunk


# Start program
gc.enable()
display = badger2040.Badger2040()
display.set_update_speed(2)
if not display.isconnected():
    failsafe_wlan()
if display.isconnected():
    try:
        ntptime.settime()
        badger2040.pico_rtc_to_pcf()
    except:
        print("NTP-Server not available")
year = rtc.datetime()[0]  # Get current year
# Time of March change to CEST and time of October change to CET
HMar = time.mktime((year, 3, (31 - (int(5 * year / 4 + 4)) % 7), 1, 0, 0, 0, 0, 0))
HOct = time.mktime((year, 10, (31 - (int(5 * year / 4 + 1)) % 7), 1, 0, 0, 0, 0, 0))
boot = datetime_dst(config.TIMEZONE, config.DST)
lastboot = f"{boot[2]:02d}.{boot[1]:02d}. {boot[3]:02d}:{boot[4]:02d}:{boot[5]:02d}"
# Set button IRQ triggers
button_up.irq(trigger=Pin.IRQ_FALLING, handler=button_up_irq)
button_down.irq(trigger=Pin.IRQ_FALLING, handler=button_down_irq)
print("Start program PV charge")
# Watchdog timer for auto reboot if program stopped
wdt = WDT(timeout=7500)

while 1:  # Loop forever
    freq(125_000_000)  # Normal CPU freq for fast execution
    tstart = time.ticks_ms()  # Start time measurement
    display.led(25)  # LED on during cycle
    print("Mem free: ", gc.mem_free(), " mem alloc: ", gc.mem_alloc())
    wdt.feed()
    if not display.isconnected():  # Check if connected
        failsafe_wlan()
    # Clear the display
    display.set_pen(15)
    display.clear()
    display.set_pen(0)
    display.set_font("bitmap8")
    data_pv, data_wb = asyncio.run(get_pv_and_wb())
    inverter_values = get_inverter_values(data_pv)
    P_Grid, P_PV = inverter_values
    P_wb = data_wb["nrg"][11] if data_wb else False
    if P_wb is not False and config.WB_METERED:
        P_Grid = P_Grid - P_wb
    grid_average = average(P_Grid, list_grid)
    if data_pv:  # Received data from pv inverter
        print("P_Grid:", P_Grid, "W")
        display.text("PV", 40, 3)
        display.text(
            str(grid_average[0] if grid_average[0] is not None else P_Grid) + " W",
            65 - 10 * len(str(grid_average[0])),
            28,
        )
    else:  # No pv data
        print("PV offline")
        display.text("PV", 40, 3)
        display.text("offline", 15, 28)
    wb_values = get_wb_values(data_wb)
    del data_pv
    del data_wb
    if wb_values:  # Received data from wallbox
        (I_wb, U_wb, phases, car, allow, energy, frc, P_wba, limit, PV_mode, switchOn) = wb_values
        percent_energy = energy / config.CAR_BAT_SIZE
        percent_limit = limit / config.CAR_BAT_SIZE
        print(
            f"P_WB: {P_wb} W ({phases} phases)\n"
            + f"Allow: {allow}, PV mode: {PV_mode}\n"
            + f"Energy charged: {energy:.2f} kWh ({percent_energy:.0%})\n"
            + f"Limit: {limit:.2f} kWh ({percent_limit:.0%})\n"
            + f"Average P_Grid: {grid_average}, P_PV: {P_PV} W\n"
            + f"Switch on: {switchOn} W"
        )
        display.text(f"{P_wba} W", 65 - 10 * len(str(P_wba)), 60)
        display.text("WB", 15, 85)
        display.rectangle(50, 81, 35, 22)
        display.set_pen(15)
        display.text(f"{phases} P", 55, 85)
        display.set_pen(0)
        display.text(f"{energy:.2f} kWh ({percent_energy:.0%})", 105, 28)
        display.text(f"{limit:.1f} kWh max. ({percent_limit:.0%})", 105, 55)
        if allow and PV_mode and car == 2 and P_Grid != 0:
            display.text("Charging", 105, 84)
            cycle = config.CYCLE
            ampere = calc_I(P_Grid, ampere, P_wb, U_wb)
            if phases == 1:
                if I_wb != ampere[0] and ampere[2]:
                    r = set_wb({"amp": ampere[0]})
                    print("Set current to", ampere[0], "A ... ", r)
                if (
                    grid_average[1] is not None
                    and max(P_Grid, grid_average[1], grid_average[0]) < SWITCH_3P
                ):
                    r = set_wb({"psm": "2", "amp": ampere[1]})
                    print("Phase change to 3 phases ... ", r)
                    display.text("-> 3P", 190, 84)
                    cycle = config.WAIT_PHASE_CHANGE
                    screen_update = 0
            elif phases == 3:
                if I_wb != ampere[1] and ampere[3]:
                    r = set_wb({"amp": ampere[1]})
                    print("Set current to", ampere[1], "A ... ", r)
                if (
                    grid_average[1] is not None 
                    and min(P_Grid, grid_average[1]) > SWITCH_1P
                ):
                    r = set_wb({"psm": "1", "amp": ampere[0]})
                    print("Phase change to 1 phase ... ", r)
                    display.text("-> 1P", 190, 84)
                    cycle = config.WAIT_PHASE_CHANGE
                    screen_update = 0
        # Stop charging if not enough PV and allowed
        if (
            car == 2 # Car charging
            and frc == 0
            and PV_mode
            and grid_average[1] is not None
            and min(P_Grid, grid_average[1]) > config.SWITCH_OFF
        ):
            # Set min charge power, 1 phase and switch off
            r = set_wb({"amp": "6", "psm": "1", "frc": "1"})
            print("Stop charging ... ", r)
            display.text("Charging stop", 105, 84)
            screen_update = 0
        # Start charging
        elif (
            2 < car < 5 # Car plugged in
            and frc == 1
            and PV_mode
            and grid_average[1] is not None
            and grid_average[1] < switchOn
        ):
            r = set_wb({"frc": "0"})
            print("Allow charging ... ", r)
            display.text("Allow charging", 105, 84)
            screen_update = 0
            cycle = config.CYCLE
        elif 2 < car < 5:
            display.text("Car plugged in.", 105, 84)
        # Keep fast polling if PV surplus but not charging
        if P_Grid < 0 and cycle > config.CYCLE and 2 < car < 5:
            cycle = config.CYCLE
            print(f"Wait {config.CYCLE} s, PV surplus detected.")
        # Large cycle when no car or full
        if car == 1:
            display.text("No car.", 105, 84)
            print(f"Wait {config.WAIT / 60: 0.1f} min, no car.")
            if cycle != config.WAIT:
                cycle = config.WAIT
                screen_update = 0
        elif car == 5:
            display.text("Error! Check car.", 105, 84)
            print("Error! Check car.")

    else:  # No wallbox data
        print("Wallbox offline")
        display.text("WB", 40, 85)
        display.text("offline", 15, 60)

    if (
        P_Grid >= 0
        and grid_average[0] is not None
        and grid_average[0] >= 0
        and cycle != config.WAIT
    ):
        cycle = config.WAIT
        print(f"Wait {config.WAIT / 60: 0.1f} min, no PV surplus.")

    update_screen()
    if gc.mem_free() < 100_000:
        gc.collect()
        print("After gc mem free: ", gc.mem_free(), " mem alloc: ", gc.mem_alloc())
    display.led(0)  # LED off after logic cycle
    time_thread = time.ticks_diff(time.ticks_ms(), tstart)  # Finish time measurement
    print(f"It took{time_thread / 1000: 0.3f} second(s) to complete.")
    pause_program = max(int(abs(cycle * 1000 - time_thread)), 500)
    print(f"Sleep for{pause_program / 1000: 0.3f} seconds.\n")
    freq(66_000_000)  # Reduce CPU freq during sleep time
    watchdog_sleep_ms(pause_program)
