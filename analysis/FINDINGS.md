# Stock firmware analysis: Omlet Smart Fan (X117)

Source: full 16 MB flash dump of one unit, read over HDR2 with esptool 4.10
(`read_flash 0 0x1000000`). The NVS partition was blanked before analysis; no
credentials, tokens or Wi-Fi data were used or kept. The dump itself is **not**
part of this repository.

Tools: Espressif `xtensa-esp32s3-elf-objdump` (crosstool-NG esp-14.2.0_20241119)
over the raw app segments, plus a small script that resolves `l32r` literals to
values and C strings (`tools/dis.py`). All addresses below are virtual addresses
in the app image.

## Image

| Item | Value |
| --- | --- |
| Project name | `Omlet_SmartCoop_Fan_1_0_7-d192f` |
| App version | `1.0.7-d192fcd2` |
| ESP-IDF | `v5.4.1-568-gb62c2cef1b` (app and bootloader) |
| Chip | ESP32-S3 (QFN56) rev v0.2, embedded PSRAM 8 MB, 40 MHz crystal |
| Module | ESP32-S3-WROOM-1 **N16R8** |
| Flash | 16 MB, DIO, 80 MHz |
| Security | Secure boot off, flash encryption off, no key blocks burned |
| `factory_test` vs `ota_0` | Byte-identical app (same ELF SHA256 `fd4c2a62…`) |
| `ota_1` | Empty |

Partition table (same layout as the X107 door panel):

| Name | Type | SubType | Offset | Size |
| --- | --- | --- | --- | --- |
| nvs | data | nvs | 0x9000 | 16 KiB |
| otadata | data | ota | 0xD000 | 8 KiB |
| phy_init | data | phy | 0xF000 | 4 KiB |
| factory_test | app | test (0x20) | 0x10000 | 4032 KiB |
| ota_0 | app | ota_0 | 0x400000 | 5 MiB |
| ota_1 | app | ota_1 | 0x900000 | 5 MiB |
| littlefs | data | 0x82 | 0xE00000 | 2 MiB |

## Pin map

| GPIO | Function | Evidence |
| --- | --- | --- |
| 0 | BOOT button (SW1, back). Active low, pull-up. Long hold (~6 s) = factory reset | `0x4200dea0` input setup + poll loop; `0x4200de68` "Factory reset has been initiated" |
| 1 | Fan PWM (LEDC ch 0, timer 0, 5 kHz, 13 bit), **active low** | `FanInit` `0x4208eccc`: `ledc_channel_config_t.gpio_num = 1` |
| 3 | Prod Test header HDR3 input (no pull). Low at boot = production test | `0x4201241d`: input on 3, `gpio_get_level(3)` |
| 4 | I2C SCL (AHT20, HDR4) | `0x42012896`: `i2c_config_t`, `scl_io_num = 4` |
| 5 | I2C SDA | same, `sda_io_num = 5`, 200 kHz, internal pull-ups on |
| 17 | RECOVERY button (SW3). Pull-up; stock ISR treats high as pressed (unverified) | `0x42012457`: input on 17; ISR `0x403770d8` stores level unmodified; bootloader checks GPIO17 |
| 43 / 44 | UART0 TX / RX on HDR2 | console |
| 19 / 20 | USB D- / D+ on test pads (USBN/USBP) | silkscreen |

Not found in firmware:

- **No tachometer input.** HDR1 pin 3 (blue fan wire) is never read. The
  production "Fan Test" runs the fan at 100 % and 50 % and the operator
  confirms by pressing BOOT (pass) or RECOVERY (fail): `0x420121d6`,
  `0x42012208`.
- **No firmware-controlled LED.** No GPIO output is driven by the app apart
  from the LEDC pin. The green LED on the back is most likely a power LED
  (it is lit in download mode). Verify on hardware.

## Fan drive (`./components/drivers/Fans.c`)

`FanInit` (`0x4208eccc`):

- `ledc_timer_config`: low-speed mode, `duty_resolution = 13`, `timer 0`,
  `freq_hz = 5000`.
- `ledc_channel_config`: `gpio_num = 1`, channel 0, timer 0, initial duty 50,
  no hardware inversion.
- AHT20 init, then trigger two measurements.
- If `FANMODE == 0` and `FANMANUALSTATE == 0`, it immediately calls
  `fanSet(on, FANMANUALSPEED)`. This is the "runs at full speed out of the box"
  behaviour.

`fanSet(on, speed_pc)` (`0x4208ebf0`) and `fanPwm`:

```
if on:   ledc_set_duty(PWM_MODE, 0, (PWM_100_PC * (100 - speed_pc)) / 100)   // PWM_100_PC = 8192
         ledc_update_duty(PWM_MODE, 0)
else:    ledc_stop(PWM_MODE, 0, MOTOR_DRIVE_OFF)                               // idle level 1
```

So the output is inverted in software: 100 % = constantly low, off = constantly
high. ESPHome: `ledc` output with `inverted: true` and `zero_means_zero: true`.

State is kept in RTC RAM at `0x50001028`: `+16` off flag, `+20` speed %, `+24`
temperature, `+28` humidity, `+32` clock-valid flag.

## Sensor

- Aosong AHT2x on the HDR5 daughterboard (`117.0009` / `117.1006`), I2C address
  0x38 (`0x71`/`0x70` on the wire).
- Init `aht20_initialise` (`0x4208ef90`): read status, if bit 3 (calibrated) is
  clear send `0xBE 0x08 0x00`.
- Trigger `0xAC 0x33 0x00` (`0x4208f040`), read 6 bytes.
- Sampled every **60 s** (`vTaskDelay(0x753 << 5 = 60000 ms)` at `0x4208ee15`).
  Temperature and humidity are converted to integers before use and reported
  as status items 20 and 21.
- ESPHome: `aht10` platform, `variant: AHT20`.

## Control logic (`0x4208ed7c`, called every control-task iteration)

Config lives in NVS namespace `FAN`. Stock defaults (as found on an unpaired
unit):

| Key | Default | Meaning |
| --- | --- | --- |
| `FANMODE` | 0 | 0 Manual, 1 Time, 2 Thermostatic |
| `FANMANUALSTATE` | 0 | 0 = on, 1 = off |
| `FANMANUALSPEED` | 100 | % |
| `FANTIMEON1..4` / `FANTIMEOFF1..4` | 0 | minutes since midnight |
| `FANSPEED1..4` | 100 | % per time window |
| `FANTEMPON` | 25 | degC |
| `FANTEMPOFF` | 23 | degC |
| `FANTEMPSPEED` | 100 | % |

MQTT topics mirror these (`/fan/mode`, `/fan/manualState`, `/fan/manualSpeed`,
`/fan/timeOn1..4`, `/fan/timeOff1..4`, `/fan/timeSpeed1..4`, `/fan/tempOn`,
`/fan/tempOff`, `/fan/tempSpeed`, `/fan/state`, `/fan/temperature`,
`/fan/humidity`). The app shows Low/Medium/High; the percentages it sends for
Low and Medium are **not** in the firmware (the firmware just takes 0–100).

**Manual (0):** nothing in the loop. The app's on/off action stores
`FANMANUALSTATE` (item 18) and calls `fanSet(1, manualSpeed)` / `fanSet(0, 0)`
(`0x42012703`, `0x42012730`).

**Time (1):** only if the clock is valid (RTC `+32`). `now` = seconds since
midnight (`0x42090f48`: `(h*60+m)*60+s`). For windows 1..4 in order,
`inWindow(on, off)` (`0x4208ebb8`):

```
if on == off: false
if on*60 >= off*60: return now >= on*60          // window past midnight ends at 24:00
return now >= on*60 && now < off*60
```

First active window → `fanSet(1, speedN)`. None active and fan running →
log "Turning fan off as no time window active", `fanSet(0, 0)`.

**Thermostatic (2)** (`0x4208ef10`):

```
if fan running:  if temp <u tempOff: "Temperature < off, turning fan off"; fanSet(0, 0)
else:            if temp >=u tempOn: "Temperature >= on, turning fan on"; fanSet(1, tempSpeed)
```

The comparisons are **unsigned** (`bgeu`/`bltu`). A negative temperature
compares as a huge number, so below 0 °C the fan switches on and stays on.
The ESPHome package compares signed on purpose.

## Buttons in normal operation

`pwr_man` task (`0x4200dea0`): polls GPIO0 about once a second. Held for six
consecutive polls → `0x4200de68`: fan off, erase config, reboot. RECOVERY is
not used by the app outside production test.

Bootloader (`0x403c8936`): `bootloader_common_check_long_hold_gpio_level(17, 5,
1)`. Holding RECOVERY for 5 s at power-up boots the `factory_test` partition
(the "recovery app", identical to `ota_0` on this unit).

## Production test

Entered when GPIO3 (HDR3 "Prod Test") is low at boot. Steps: AHT20 read,
BOOT press/release, RECOVERY press/release, fan at 100 % and at 50 % confirmed
by the operator. State in RTC `0x50001008`.
