# omlet-fan-esphome

[![CI](https://github.com/skolodziej/omlet-fan-esphome/actions/workflows/ci.yml/badge.svg)](https://github.com/skolodziej/omlet-fan-esphome/actions/workflows/ci.yml)

ESPHome firmware for the **Omlet Smart Chicken Coop Fan** (board `X117 FAN ISS 2.0`).

The stock fan is an ESP32-S3 that only talks to Omlet's cloud. This project replaces the firmware with ESPHome so
the fan works fully locally with Home Assistant. The stock module has no secure boot and no flash encryption, so it
can be flashed over the serial header and restored from a backup at any time.

> **Status: work in progress.** The pin map and control logic were recovered by disassembling the stock firmware
> (1.0.7, see [`analysis/FINDINGS.md`](analysis/FINDINGS.md)). The package compiles with ESPHome 2026.10.1 (checked in CI). Fan polarity, the Low/Medium
> duty cycles and the RECOVERY button polarity still need to be confirmed on a real unit. Back up your stock firmware
> first (see below) so you can always go back.

## Usage

Everything board-specific lives in the `omlet-fan.yaml` package. Your own config only needs a name, networking and
the package line:

```yaml
esphome:
  name: coop-fan
  friendly_name: Coop Fan

packages:
  omlet: github://skolodziej/omlet-fan-esphome/omlet-fan.yaml@main

api:

ota:
  - platform: esphome

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
  ap:

captive_portal:
```

See `example.yaml`. Tunables such as `fan_min_power`, `timezone` and `factory_reset_hold` are substitutions at the
top of the package; set them in your own `substitutions:` block to override.

The package provides:

- `fan` with three speeds (Low / Medium / High), on by default at full speed like the stock fan.
- `select` **Mode**: Manual, Time or Thermostatic, the same three modes as the Omlet app. The logic runs on the
  device, so it keeps working without Home Assistant.
- Manual: **Manual Speed** (Low / Medium / High) sets the level; on and off stay on the fan entity. It follows speed
  changes made on the fan entity.
- Thermostatic: **On At** / **Off Below** (defaults 25 / 23 °C, as stock) and a speed.
- Time: four windows, each with on time, off time and speed. A window with equal on and off times is disabled.
- `sensor` temperature and humidity from the built-in AHT20 (sampled every 60 s like stock).
- `binary_sensor` for the BOOT and RECOVERY buttons. Holding BOOT for 6 s does a factory reset, as on stock.
- `button` Factory Reset and Restart.

Two deliberate differences from stock, both bugs in the stock firmware:

- Stock compares temperatures unsigned, so below 0 °C the thermostatic mode turns the fan on and keeps it running.
  Here the comparison is signed.
- Stock ends a time window that crosses midnight (e.g. 22:00–06:00) at 24:00. Here it runs until the off time.

## Hardware

- ESP32-S3-WROOM-1 N16R8 (16 MB flash, 8 MB PSRAM), 40 MHz crystal
- Power: barrel jack (12 V adapter), buck regulator (IC1, L1 "3R3") to 3.3 V
- Serial header `HDR2` (through-hole, near the module): `0V / RXI / TXO`, 115200 8N1, 3.3 V logic
- `CON1` 2×3 programming header: RX, TX, EN, IO0, 0V, 3V3 (see TP3–TP8 on the back)
- Download mode: hold **BOOT** (back side, GPIO0), press **RESET** (SW2), release BOOT
- `HDR1` 3-pin fan connector: red +12 V, black switched return (through T1), blue tacho (not used by stock)
- `HDR4` I2C header `3V3 / SCL / SDA / 0V`, `HDR5` carries the sensor daughterboard (Aosong AHT2x, 0x38)
- `HDR3` "Prod Test": pulled low at boot enters the stock production test
- **RECOVERY** (SW3): held for 5 s at power-up, the stock bootloader starts the `factory_test` app

## Pin map

Recovered from the stock firmware (`FanInit`, the I2C init in the control task, and the button setup).

| GPIO | Function | Notes |
| --- | --- | --- |
| 0 | BOOT button | Active low; boot strap; stock: hold ~6 s for factory reset |
| 1 | Fan PWM | LEDC 5 kHz, 13 bit, **active low** (stock duty = 8192 × (100 − speed) / 100) |
| 3 | Prod Test (HDR3) | Input, low enters production test in stock firmware |
| 4 | I2C SCL | AHT20, 200 kHz |
| 5 | I2C SDA | |
| 17 | RECOVERY button | Pull-up; stock ISR treats high as pressed (to confirm) |
| 19 / 20 | USB D− / D+ | Test pads only |
| 43 / 44 | UART0 TX / RX | Serial header HDR2 |

No GPIO is driven for the green LED (probably a power LED) and the blue tacho wire is never read.

## Flashing and recovery

1. Solder a 3-pin header on HDR2 and connect a 3.3 V USB-serial adapter: GND to 0V, adapter TX to RXI, adapter RX
   to TXO. Do not connect VCC; power the board from its own adapter.
2. Hold BOOT, press RESET, release BOOT.
3. Back up the stock flash before anything else. Many cheap adapters fail at 460800 baud; 115200 always works (about
   25 minutes). Read it twice and compare the checksums:

   ```
   esptool --chip esp32s3 --port /dev/ttyUSB0 --before no_reset read-flash 0 0x1000000 omlet-fan-backup.bin
   ```

   Keep this file private. It contains your Wi-Fi credentials and the device's Omlet API token. If you want to share
   a dump for analysis, blank the NVS first with `analysis/tools/blank_nvs.py`.

4. Flash ESPHome as usual (first time over serial, then OTA). To go back to stock, write the backup to offset 0 with
   `write-flash`.

## Partition layout of the stock firmware

| Name | Type | Offset | Size |
| --- | --- | --- | --- |
| nvs | data | 0x9000 | 16 KiB |
| otadata | data | 0xD000 | 8 KiB |
| phy_init | data | 0xF000 | 4 KiB |
| factory_test | app | 0x10000 | 4032 KiB |
| ota_0 | app | 0x400000 | 5 MiB |
| ota_1 | app | 0x900000 | 5 MiB |
| littlefs | data | 0xE00000 | 2 MiB |

## Related

- [swoboda1337/omlet-esphome](https://github.com/swoboda1337/omlet-esphome): the same approach for the Omlet Smart
  Autodoor control panel (X107), which shares the module, partition layout and serial header.
