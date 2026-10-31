# Hardware assembly guide

Desk gadget: Heltec WiFi LoRa 32 V4 (primary), Waveshare 7.3" e-Paper HAT (F), three buttons, one LiPo cell.
Pins come from `firmware/src/config.h`. Items marked "to confirm" were not verified against a datasheet or schematic.

## Bill of materials

| Item | Qty | Notes | Link |
|---|---|---|---|
| Heltec WiFi LoRa 32 V4 (R2, or V4R8) | 1 | ESP32-S3, onboard LiPo charger (SH1.25-2P), datasheet V4.3.1 | https://s.heltec.cn/download/WiFi_LoRa_32_V4/datasheet/WiFi_LoRa_32_V4.3.1_Datasheet.pdf |
| Waveshare 7.3" e-Paper HAT (F), 800x480, 7 colours | 1 | Includes driver board and FFC cable | https://www.waveshare.com/7.3inch-e-paper-hat-f.htm |
| LiPo 3.7 V, about 3000 mAh, SH1.25-2P | 1 | Check polarity against the board before plugging in | n/a |
| Momentary push buttons | 3 | Normally open, one side to GND | n/a |
| Dupont wires or soldered hookup wire | about 14 | 8 for the HAT, 6 for buttons | n/a |
| USB-C cable | 1 | Flashing and charging | n/a |

## HAT to Heltec V4 wiring

| HAT pin | Heltec V4 GPIO | Note |
|---|---|---|
| VCC | Vext (GPIO36 switches it) or 3V3 | Vext lets the firmware cut the HAT during sleep. Wire VCC to the Ve header pin |
| GND | GND | |
| DIN (MOSI) | 40 | V4R8: 47 (not confirmed on the header), because Vext is on 40 there |
| CLK (SCK) | 39 | |
| CS | 41 | |
| DC | 42 | |
| RST | 38 | |
| BUSY | 34 | input only, low = busy |

GPIO38 to 42 are the GNSS header pins on this board and are free when no GNSS module is fitted.
Vext polarity is NOT CONFIRMED: the datasheet says HIGH is on, espboards.dev says LOW. Test on the bench; the level is `VEXT_ON_LEVEL` in `platformio.ini`.
The OLED and LoRa radio are not used and not initialised. LoRa SPI is on GPIO8 to 14 and not on the header.

### Generic ESP32-S3 example: FireBeetle 2 ESP32-S3

Env `firebeetle2_esp32s3`, defaults of `config.h`: SCK 17, MOSI 15, CS 18, DC 3, RST 38, BUSY 14, buttons 7, 9, 12, battery on GPIO4 (assumed 2:1 divider, to confirm in the schematic), HAT on 3V3.
The DFRobot FireBeetle 2 ESP32-P4 (DFR1237) is not a valid target for battery use: its wiki reports 31.5 mA in deep sleep (5 V on VIN), and neither the product page nor the wiki mention a LiPo charger. It would also need the pioarduino fork and esp_hosted on the C6 (source: pesquisa-boards-v2, https://wiki.dfrobot.com/dfr1237/).

Power: the Waveshare wiki and product page state a 3.3 V / 5 V HAT with an onboard level translator. Neither page mentions a power switch or a 0.47 ohm setting, so none is documented here. Check the driver board version printed under its name: versions before V2.1 only support 3.3 V (NOT CONFIRMED: second-hand, from the Waveshare product page summary in the hardware research, not checked on the board), and 3.3 V is what this build uses.

## Battery

- Plug the LiPo into the board SH1.25-2P connector. The onboard charger takes 500 mA from USB 5 V (datasheet). Check polarity first.
- Battery voltage: GPIO1 (ADC1_CH0) behind a divider, read as Vbat = Vadc x 4.9. GPIO37 (ADC_Ctrl) must be HIGH while reading; the firmware does that. Divider and ADC_Ctrl level are from the datasheet and not verified on the board.

## Buttons

Wire each button between the GPIO and GND. The firmware enables the internal pull-up.

| Button | Heltec V4 GPIO | Action | Wakes from sleep |
|---|---|---|---|
| A | 4 | approve | yes |
| B | 6 | reject | yes |
| C | 3 | stop | no |

GPIO3 is a strapping pin (JTAG source) and is not used as a wake source here, so button C only acts while the chip is awake. Keep wake buttons on RTC GPIOs (0 to 21).

## First power-on

1. Copy `firmware/src/secrets.example.h` to `secrets.h` and set the bridge URL and device token.
2. Flash with PlatformIO (see `firmware/README.md`) or with the browser flasher in `docs/flash` (Chrome or Edge).
3. With no stored Wi-Fi, the device waits 5 minutes for Improv Wi-Fi over USB serial. Provision the network from ESP Web Tools or https://www.improv-wifi.com.
4. The device fetches the screen from the bridge and streams it to the panel.
5. The first image appears after about 35 s, the full refresh time. Do not power off during this time.
6. The panel then hibernates and the chip enters deep sleep. Button presses during the refresh are lost.

To clear stored Wi-Fi, hold button A for 5 s while powering on or resetting.

## Battery life

Estimates, not measurements. Assumptions for a 3000 mAh cell with 80% usable (2400 mAh):

| Phase | Current | Duration | Charge |
|---|---|---|---|
| Panel refresh | 45 mA | 35 s | 0.44 mAh |
| Wi-Fi and fetch | 120 mA | 3 s | 0.10 mAh |
| SPI transfer | 60 mA | 2 s | 0.03 mAh |
| Total per cycle | | | 0.57 mAh |

Deep sleep is assumed at 50 uA (Heltec datasheet: 20 uA on battery, 2 mA with USB connected; not independently measured) (1.2 mAh/day).

| Refresh interval | Cycles/day | Use/day | Life |
|---|---|---|---|
| 5 min | 288 | about 165 mAh | about 14 days |
| 15 min | 96 | about 56 mAh | about 43 days |

The refresh is about 77% of the consumption, so the interval matters more than sleep current. Even 174 uA of sleep current adds only about 3 mAh/day.

Saving tips:
- Use the longest interval you can accept. The panel requires at least 180 s between refreshes.
- Skip the refresh when the image hash is unchanged (the firmware already does this).
- Panel power is switched with Vext during sleep (see wiring); keep the OLED and radio uninitialised.
- With USB connected the board draws about 2 mA in sleep, so measure on battery.

## Known unknowns

- **Panel controller:** no source named the chip. The firmware uses the GxEPD2 class `GxEPD2_730c_ACeP_730`.
- **Vext polarity:** datasheet HIGH, espboards.dev LOW. Test on the bench.
- **Battery divider:** 4.9 and ADC_Ctrl HIGH come from the datasheet, unverified on the board.
- **Deep sleep current:** 20 uA is the manufacturer figure, with no independent measurement.
- **PlatformIO board:** `esp32-s3-devkitc-1` per espboards.dev; `heltec_wifi_lora_32_V3` compatibility is not confirmed.
- **V4R8:** MOSI on GPIO47 and PSRAM (likely octal) interaction with GPIO33 to 37 are not confirmed.
- **Serial:** assumed UART bridge (no CDC on boot). If the console is silent, enable `ARDUINO_USB_CDC_ON_BOOT`.
- **Operating temperature:** 15 to 35 C per the wiki. Do not place the unit in cold or hot spots.
