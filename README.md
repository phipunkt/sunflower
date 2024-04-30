# sunflower

Charge car with pv - Fronius + go-e running on Pimoroni Badger 2040 W  
PV-Überschussladen mit Fronius + go-e charger auf einem Pimoroni Badger 2040 W

This runs on the Badger 2040 W and monitors the grid power. If you have enough pv surplus and the car is connected to the charger, it starts charging. Only excess power is used, grid usage is avoided. The go-e charger settings are respected, e.g. schedule and power limits. On the e-paper you see the current status. Automatic start and stop and phase change depending on available excess pv power is supported. This is tested with a Fronius Symo inverter, go-e charger HOME V3 and Stellantis EV platform (Citroen). 

All runs in the local network which allows a fast update cycle to track clouds. More inverters can be supported if someone helps with getting the current grid power and testing.

There is no handling of a battery storage. As only the grid consumption is monitored, this will not compete with a battery controller as only excess power to the grid is used for charging.

![Sunflower running on Badger 2040 W](/pictures/badger_running_sunflower.jpg)

Note: Wallbox power is smaller than available pv as the car is almost full and limits the charging.

## Hardware Requirements

- Fronius inverter with datamanager (Symo, Gen 24, etc.)
- go-e charger (HOME with V3 hardware for phase change, Gemini)
- [Pimoroni Badger 2040 W](https://shop.pimoroni.com/products/badger-2040-w?variant=40514062188627)
- Electric vehicle

## Usage

After initial setup, pv charging is mostly automatic.

- In the go-e app under settings you need to make sure charging in allowed in the scheduler and define a kWh limit if you want to only charge to a certain level.
- Set charge mode to standard (no ECO or next trip mode)
- Plug Badger 2040 W on a power supply, USB or on batteries to run.
- Information is shown on the display
- When data is retrived and the logic cycle is running, the LED in on.
- Keep `UP` or `DOWN` button pressed during cycle (LED on) to change charge limit (+/- 2.5 kWh).

- To stop unplug from power supply as the program will always run.

#### Attention

> If you want to charge when there is not enough pv power (e.g. during the night) or charge with full power, you have 2 options. Otherwise it will always stop the charging.
> - Stop the program by cutting the power supply.
> - Use the next trip mode. (Currently behaviour not fully tested)

## Installation

### go-e charger

- [Enable local API V2](https://github.com/goecharger/go-eCharger-API-v2/blob/main/http-de.md)

### Badger 2040 W

- Get latest firmware [Github Badger 2040 W](https://github.com/pimoroni/badger2040)
- Install using instructions
- Download / install [Thonny IDE](https://thonny.org/)
- Connect to Badger 2040 W via USB, see [Pimoroni geeting started](https://learn.pimoroni.com/article/getting-started-with-badger-2040)

### Sunflower

- Download latest release
- Modify configuration, see section below
    - `config.py`
- Upoad files on Badger 2040 W
    - `config.py`
    - `sunflower.py`
    - `async_urequests.py` [modified async_requests included in release](https://github.com/phipunkt/async_urequests)  
    Current in micropython included requests modules miss handling all cases needed. The modified library fixes some server handling to make it work. (SSL seems to be broken, but not used here.)
- Edit files on Badger 2040 W, see below
    - `WIFI_CONFIG.py`
    - `main.py`  
- Reboot

## Configuration

### `config.py`

`TIMEZONE` - Default value: `1` (Central European Time (CET))  
Number of hours difference between UTC (positive or negative number)

`DST` - Default value: `True`  
If `True`, enable automatic DST time setting. `False`: No DST correction used.

`NTP_HOST` - Default value: `"1.europe.pool.ntp.org"`  
Hostname for NTP time server

`IP_PV` - Default value: `"xxx.xxx.xxx.xxx"`  
IP or hostname pv inverter Fronius, change to your your configuration

`IP_WB` - Default value: `"xxx.xxx.xxx.xxx"`  
IP or hostname go-e charger, change to your configuration

`CAR_BAT_SIZE` - Default value: `50`  
Car battery maximum capacity in kWh, used for percentage calculation charge status and limit

`I_MIN` - Default value: `6`  
Minimum charging current for car in ampere (usually 6 A)

`I_MAX` - Default value: `16`  
Maximum charging current allowed, electric installation and charger type. 16 A is for 11 kW charger.

`I_MAX_1P` - Default value: `16`  
Maximum current limit for 1 phase, set to country limit if less than `I_MAX`

`WB_METERED` - Default value: `True`  
`True` if the wallbox power is included in the grid meter power value. Depends on meter wiring in electric setup.

`CYCLE` - Default value: `6`  
Seconds to wait between cycles while charging (how close to follow the power generation)

`WAIT` - Default value: `60`  
Seconds to wait if there is no pv power or no car connected

`WAIT_PHASE_CHANGE` - Default value: `15`  
Seconds to wait after phase change: May be removed if future

`SHORT_CYCLES` - Default value: `6`  
Number of program cycles to use for average calculation of short period grid power: Equals 36 s with default 6 s `CYCLE`

`LONG_CYCLES` - Default value: `20`  
Number of program cycles to use for average calculation of long period grid power: Equals 120 s with default 6 s `CYCLE`

`SCREEN_REFRESH` - Default value: `120`  
Seconds to wait between badger screen updates (not used for status updates e.g. phase change), checked only on each cycle, so no exact timing

> Power values defined below are negative for excess pv and positive for grid consumption

`P_MIN_1P` - Default value: `-1440`  
Minimum power in W for 1p charging ampere calculation (I_MIN x U max), no need to change

`P_MIN_3P` - Default value: `-4320`  
Minimum power in W for 3p charging ampere calculation (I_MIN x U max), no need to change

`SWITCH_3P` - Default value: `-4200`
Power threshold in W to switch for 3 phase charging

`SWITCH_1P` - Default value: `-3800`  
Power threshold in W to switch for 1 phase charging

`SWITCH_ON` - Default value: `-1300`  
Power threshold in W to start charging when average of LONG_CYCLES is below (more power available)

`SWITCH_OFF` - Default value: `-900`  
Power threshold in W to stop charging when average of LONG_CYCLE is above (less power available), default allows up to 400 W grid consumption.

### `WIFI_CONFIG.py` on Badger 2040 W

`SSID` : Your WLAN network SSID, must be visible, case sensitive

`PSK` : Your WLAN password, case sensitive

`COUNTRY` : [2 character country code](https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2) for WLAN band selection, required

### `main.py`

Run sunflower program at startup. As sometimes the program does stop unintendedly, the watchdog timer will restart. The program must therefore be the one to start and not the badgerOS launcher.

Replace default launcher import with the following line.

```python
import sunflower
```
