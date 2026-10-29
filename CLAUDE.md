# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An ESPHome package (`omlet-fan.yaml`) that replaces the stock firmware of the Omlet Smart Chicken Coop Fan (board
X117, ESP32-S3-WROOM-1 N16R8) so it runs locally with Home Assistant. Users include the package from their own config
(`example.yaml`). There is no custom C++ component, only standard ESPHome plus one lambda. Keep it that way unless
standard ESPHome can't do the job.

`HANDOFF.md` (German) is the original task brief: current status, open hardware questions to work through with the
user, and the user's flashing setup. `analysis/FINDINGS.md` holds the reverse-engineering results (with addresses in
stock firmware 1.0.7) that justify every pin and behaviour choice in the package.

## Commands

Validate / build the package with a local test config in `.test/` (gitignored), which includes `../omlet-fan.yaml`
(template in `HANDOFF.md`) and needs a `secrets.yaml` with `wifi_ssid` / `wifi_password`:

```bash
esphome config .test/test.yaml
esphome compile .test/test.yaml
```

Host-side logic test (needs `esphome` and `g++`):

```bash
tests/run.sh
```

There is no way to run a single test case; all assertions live in `main()` of `tests/logic_test.cpp`.

## Architecture

- **Control logic** is the `omlet_evaluate` script lambda in `omlet-fan.yaml`. It mirrors the stock `Fans.c` loop:
  Mode select 0 = Manual (leave fan alone), 1 = Time (four windows, first active one wins, otherwise off),
  2 = Thermostatic (on at `temp >= on`, off at `temp < off`). It runs on the `control_interval`, on each temperature
  reading and on Mode / threshold changes. Speeds are select indices + 1 mapped onto a 3-speed `speed` fan.
- **Deliberate deviations from stock** (stock bugs): signed temperature comparison, and time windows crossing
  midnight keep running after 00:00. The tests assert both; don't "fix" them back.
- **Time source**: Home Assistant time first, SNTP as fallback; with no valid clock the Time mode changes nothing.
- **How the test works**: `tests/run.sh` runs `esphome compile --only-generate`, cuts the lambda body out of the
  generated `main.cpp` using text anchors (the `auto speed_of = ...` line as start, the last `set_fan(false, 0);`
  before the closing `});` as end), and `#include`s it into `logic_test.cpp`, which defines stub ESPHome types and
  globals for every `omlet_*` id. Consequences when editing the lambda:
  - keep the first line `auto speed_of = [](select::Select *s) -> int {` and the final `set_fan(false, 0);` intact,
    or update the anchors in `run.sh`;
  - any new entity referenced via `id(...)` or any new ESPHome API call needs a matching stub in `logic_test.cpp`.
- **Hardware facts that shape the YAML**: fan PWM on GPIO1 is active low (`inverted: true`, 5 kHz LEDC), AHT20 on
  I2C GPIO4/5 at 0x38, logs on UART0 (serial header HDR2), BOOT button GPIO0 with a 6 s hold for factory reset,
  RECOVERY on GPIO17 with unconfirmed polarity (`recovery_inverted`). User-tunable values are `substitutions:` at the
  top of the package.

## Open items and status

Not yet verified on a real unit: fan polarity, Low/Medium duty (default 33/67 %, `fan_min_power`), RECOVERY polarity,
LED behaviour, whether the tacho wire reaches a GPIO. When a hardware question is settled, record the result in
`README.md` (status note, pin map) and `analysis/FINDINGS.md`.

The repo is published as `skolodziej/omlet-fan-esphome`; users pull the package from `main`, so anything pushed there
ships. CI (`.github/workflows/ci.yml`) turns `example.yaml` into a local-include config by rewriting its `omlet:`
package line, then runs `esphome config`, `tests/run.sh` and `esphome compile`. Keep that line's format in
`example.yaml` or update the `sed` in the workflow.

## Working with the user's hardware

The user can solder and flash but has no firmware experience; walk them through device steps one at a time. Setup:
macOS, USB-serial adapter on `/dev/cu.usbserial-0001`, esptool 4.10 (underscore commands: `read_flash`,
`write_flash`), 115200 baud only (460800 is unreliable), no RTS/DTR, so download mode is manual (hold BOOT, press
RESET, release BOOT) and every command needs `--before no_reset`.

## Don't

- Commit flash dumps, NVS contents, MAC addresses or tokens (`*.bin` and `secrets.yaml` are gitignored). Use
  `analysis/tools/blank_nvs.py` before sharing a dump; `read_fan_nvs.py` reads only the FAN settings.
- Add a humidity-based mode unless the user explicitly asks; humidity stays a sensor only.
