# Übergabe an Claude Code: omlet-fan-esphome

Diese Datei ist der Startauftrag für Claude Code. Die Reverse-Engineering-Analyse ist abgeschlossen; alles, was
sich aus der Firmware ableiten ließ, steht in `analysis/FINDINGS.md`. Was jetzt noch fehlt, geht nur am Gerät.

## Ziel

ESPHome-Firmware für den **Omlet Smart Fan** (Platine `X117 FAN ISS 2.0`, ESP32-S3-WROOM-1 N16R8) als eigenes
GitHub-Repo, aufgebaut wie [swoboda1337/omlet-esphome](https://github.com/swoboda1337/omlet-esphome) (Türsteuerung
X107, gleiches Modul, gleiches Partitionslayout, gleicher Serial-Header). Funktional soll sich der Lüfter **so
verhalten wie mit der Omlet-App** (Manuell / Zeit / Thermostatisch, drei Stufen), nur lokal mit Home Assistant.
Kein Feuchte-Modus (würde im Winter Dauerbetrieb bedeuten); Luftfeuchte nur als Sensor.

## Stand

| Datei | Inhalt | Status |
| --- | --- | --- |
| `omlet-fan.yaml` | ESPHome-Paket: Pins, PWM, AHT20, Modus-Logik, Tasten | `esphome config` fehlerfrei und C++-Codegenerierung ok (ESPHome 2026.10.1); **vollständiger Build noch nicht gelaufen** (Espressif-/PlatformIO-Downloads waren in der Analyse-Umgebung gesperrt); **nicht am Gerät getestet** |
| `example.yaml` | Minimale Nutzerkonfiguration | Platzhalter `<owner>` ersetzen |
| `README.md` | Hardware, Pin-Map, Flashen/Restore, Partitionen | Platzhalter `<owner>` ersetzen |
| `analysis/FINDINGS.md` | Befunde mit Adressen in der Stock-Firmware 1.0.7 | fertig |
| `analysis/tools/dis.py` | Disassembler-Wrapper (Literal-Auflösung) | Hilfsmittel |
| `analysis/tools/blank_nvs.py` | NVS in einem Dump löschen, bevor man ihn teilt | Hilfsmittel |
| `analysis/tools/read_fan_nvs.py` | Nur die `FAN`-Einstellungen aus der NVS lesen | Hilfsmittel |
| `tests/run.sh`, `tests/logic_test.cpp` | Host-Test der Steuerlogik: generiert C++ aus dem Paket, kompiliert die `omlet_evaluate`-Lambda gegen Stub-Typen, prüft Thermostat-Hysterese, Minusgrade, Zeitfenster (auch über Mitternacht), Uhr-Fallback | **besteht** |

Die Firmware-Sicherung des Nutzers (`omlet-fan-backup.bin`) gehört **nicht** ins Repo (WLAN-Zugang, Omlet-Token).
`.gitignore` schließt `*.bin` aus.

## Die wichtigsten Befunde (Kurzfassung)

- GPIO1 = Lüfter-PWM über LEDC, 5 kHz, 13 Bit, **active-low** (Stock: Duty = 8192 × (100 − %) / 100; aus = HIGH).
  → `ledc` mit `inverted: true`, `zero_means_zero: true`.
- GPIO4/5 = I2C SCL/SDA, 200 kHz; AHT20 auf 0x38, Stock misst alle 60 s.
- GPIO0 = BOOT (active-low), ~6 s halten = Werksreset. GPIO17 = RECOVERY (Polarität unklar), GPIO3 = Prod-Test.
- Kein Tacho (blaues Kabel wird nie gelesen), keine per Firmware gesteuerte LED.
- Modi: 0 Manuell, 1 Zeit (4 Fenster, je Ein/Aus/Stufe, erstes aktives gewinnt), 2 Thermostat (an bei
  `temp ≥ on`, aus bei `temp < off`, Defaults 25/23 °C, 100 %).
- Zwei Stock-Bugs bewusst **nicht** übernommen: vorzeichenloser Temperaturvergleich (unter 0 °C läuft der Lüfter
  dauerhaft) und Zeitfenster über Mitternacht enden um 24:00.

## Aufgaben

### 1. Repo anlegen und bauen

- **Zuerst einmal komplett bauen** (`esphome compile` mit der Testconfig unten) und Compilerfehler in der
  `omlet_evaluate`-Lambda beheben. Die verwendeten APIs (`Select::active_index()`, `TimeEntity::hour/minute`,
  `Fan::turn_on().set_speed().perform()`) wurden gegen die Header von 2026.10.1 geprüft; die Lambda kompiliert
  im Host-Test gegen Stubs, aber noch nie gegen das echte ESPHome/ESP-IDF.
- `tests/run.sh` danach ebenfalls ausführen (braucht `esphome` und `g++`); gehört mit in die CI.

- Neues öffentliches Repo im Account des Nutzers, Vorschlag `omlet-fan-esphome`. Name/Owner mit dem Nutzer klären.
- `<owner>` in `README.md`, `example.yaml` und im Kopfkommentar von `omlet-fan.yaml` ersetzen.
- Optional: GitHub Action, die `example.yaml` mit dem lokalen Paket kompiliert (Testconfig wie unten,
  `esphome compile`). Secrets per Dummy-`secrets.yaml` im Workflow erzeugen.

Lokale Testconfig (liegt in `.test/`, ist ignoriert):

```yaml
esphome:
  name: coop-fan
packages:
  omlet: !include ../omlet-fan.yaml
api:
ota:
  - platform: esphome
wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
  ap:
captive_portal:
```

### 2. Offene Punkte, die nur am Gerät geklärt werden können

Mit dem Nutzer Schritt für Schritt durchgehen. Der Nutzer kann löten, flashen und Logs mitlesen, hat aber keine
Firmware-Erfahrung. Sein Setup: macOS, USB-Seriell-Adapter an HDR2 auf `/dev/cu.usbserial-0001`, esptool 4.10
(Befehle mit **Unterstrich**: `read_flash`, `write_flash`, `chip_id`). Der Adapter schafft 460800 Baud nicht
zuverlässig → Standard 115200 verwenden. Kein RTS/DTR verdrahtet → Download-Modus von Hand (BOOT halten, RESET
drücken, BOOT loslassen) und `--before no_reset`.

1. **Low/Medium-Prozentwerte der App** (vor dem Flashen, solange die Stock-Firmware drauf ist):
   In der Omlet-App im Modus Manuell die Stufe auf „Niedrig“ stellen und speichern, dann nur die NVS lesen:
   ```
   python3 -m esptool --port /dev/cu.usbserial-0001 --before no_reset read_flash 0x9000 0x4000 nvs-low.bin
   python3 analysis/tools/read_fan_nvs.py nvs-low.bin
   ```
   `FANMANUALSPEED` ablesen. Dasselbe für „Mittel“. Falls die Werte nicht 33/67 sind: entweder `speed_count`
   auf 100 umstellen und Presets abbilden, oder `min_power` / ein eigenes Mapping verwenden. Der Lüfter war bisher
   nicht mit dem Omlet-Konto gekoppelt (`VALIDWIFICREDS = 0`); ggf. muss er dafür erst eingerichtet werden. Wenn
   das zu aufwendig ist, Schritt überspringen und am Gerät per Augenmaß/Messung festlegen.
2. **Erstes Flashen**: Die Sicherung existiert bereits (zweimal gelesen, gleiche Prüfsumme bestätigen lassen).
   Dann `esphome run` über Seriell bzw. die Factory-Binary mit esptool an Offset 0 schreiben. Danach OTA.
3. **Lüfter-Polarität**: Lüfter in HA aus → muss stehen; Hoch → volle Drehzahl. Wenn invertiert, `inverted` im
   Paket korrigieren.
4. **Niedrigste Stufe**: läuft „Low“ sicher an (auch aus dem Stillstand)? Sonst `fan_min_power` anheben.
   PWM-Pfeifen hörbar? Stock nutzt 5 kHz; nur ändern, wenn nötig.
5. **AHT20**: plausible Temperatur/Feuchte im Log.
6. **Tasten**: BOOT und RECOVERY drücken, Binary Sensoren beobachten. RECOVERY-Polarität ggf. über
   `recovery_inverted` korrigieren. Werksreset durch 6 s BOOT prüfen (oder bewusst weglassen).
7. **LED**: Leuchtet sie dauerhaft, sobald Strom anliegt (dann Power-LED, im README so vermerken)?
8. **Optional Tacho**: Durchgang von HDR1 Pin 3 (blau) zu einem ESP-Pin messen. Wenn verbunden: `pulse_counter`
   als Drehzahl-Sensor ergänzen (Achtung: Masse wird per PWM geschaltet, Tacho nur bei 100 % zuverlässig).
9. **Zurück zu Stock** einmal testen:
   `python3 -m esptool --port /dev/cu.usbserial-0001 --before no_reset write_flash 0 omlet-fan-backup.bin`

Ergebnisse in `README.md` (Status-Hinweis, Pin-Map) und `analysis/FINDINGS.md` nachtragen.

### 3. Nicht tun

- Keine Dumps, NVS-Inhalte, MAC-Adressen oder Tokens committen.
- Keinen Feuchte-Modus einbauen, solange der Nutzer das nicht ausdrücklich will.
- Keine eigenen C++-Komponenten, solange Standard-ESPHome reicht.

## Hintergrund: Wie die Befunde entstanden sind

Flash-Dump über HDR2, NVS vor der Analyse geleert. App-Image (`factory_test` = `ota_0`, Firmware
`1.0.7-d192fcd2`, ESP-IDF 5.4.1) mit Espressifs `xtensa-esp32s3-elf-objdump` disassembliert, `l32r`-Literale
aufgelöst, Funktionen über Assert-/Log-Strings identifiziert (`Fans.c`, `fanPwm`, `FanInit`, `aht20_initialise`,
`ProductionTest`, `pwr_man`, `controlTask`). Details und Adressen in `analysis/FINDINGS.md`.
