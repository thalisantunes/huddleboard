# Hardware assembly guide

Desk gadget: DFRobot FireBeetle 2 ESP32-S3, Waveshare 7.3" e-Paper HAT (F), three buttons, one LiPo cell.
Pins come from `firmware/src/config.h`. Items marked "to confirm" were not verified against a datasheet or schematic.

## Bill of materials

| Item | Qty | Notes | Link |
|---|---|---|---|
| DFRobot FireBeetle 2 ESP32-S3 (N16R8) | 1 | Confirm it is the S3 and not the P4 variant, see Known unknowns | https://www.dfrobot.com/product-2950.html |
| Waveshare 7.3" e-Paper HAT (F), 800x480, 7 colours | 1 | Includes driver board and FFC cable | https://www.waveshare.com/7.3inch-e-paper-hat-f.htm |
| LiPo 3.7 V, about 3000 mAh, JST 2-pin | 1 | Check polarity against the board before plugging in | n/a |
| Momentary push buttons | 3 | Normally open, one side to GND | n/a |
| Dupont wires or soldered hookup wire | about 14 | 8 for the HAT, 6 for buttons | n/a |
| USB-C cable | 1 | Flashing and charging | n/a |

## HAT to FireBeetle wiring

| HAT pin | FireBeetle GPIO | Silkscreen | Note |
|---|---|---|---|
| VCC | 3V3 | 3V3 | HAT accepts 3.3 V or 5 V |
| GND | GND | GND | |
| DIN (MOSI) | 15 | MOSI | board default SPI |
| CLK (SCK) | 17 | SCK | board default SPI |
| CS | 18 | D6 | |
| DC | 3 | D2 | |
| RST | 38 | D3 | |
| BUSY | 14 | D10 | low = busy |

Power: the Waveshare wiki and product page state a 3.3 V / 5 V HAT with an onboard level translator. Neither page mentions a power switch or a 0.47 ohm setting, so none is documented here. Check the driver board version printed under its name: versions before V2.1 only support 3.3 V (NOT CONFIRMED: second-hand, from the Waveshare product page summary in the hardware research, not checked on the board), and 3.3 V is what this build uses.

## Battery

- Plug the LiPo into the board JST connector. The board charger is rated up to 1 A (third-party report).
- Battery voltage is read on GPIO4 (A0) with an assumed 2:1 divider (`BAT_DIVIDER` in `config.h`). To confirm in the FireBeetle 2 S3 schematic. If the divider differs, edit `config.h`.

## Buttons

Wire each button between the GPIO and GND. The firmware enables the internal pull-up.

| Button | GPIO | Silkscreen | Action |
|---|---|---|---|
| A | 7 | D5 | approve |
| B | 9 | D7 | reject |
| C | 12 | D12 | stop |

Keep buttons on RTC GPIOs (0 to 21) so they can wake the chip from deep sleep.

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

Deep sleep is assumed at 50 uA (1.2 mAh/day).

| Refresh interval | Cycles/day | Use/day | Life |
|---|---|---|---|
| 5 min | 288 | about 165 mAh | about 14 days |
| 15 min | 96 | about 56 mAh | about 43 days |

The refresh is about 77% of the consumption, so the interval matters more than sleep current. Even 174 uA of sleep current (measured by a user on another FireBeetle 2) adds only about 3 mAh/day.

Saving tips:
- Use the longest interval you can accept. The panel requires at least 180 s between refreshes.
- Skip the refresh when the image hash is unchanged (the firmware already does this).
- Cut the LP jumper on the board and measure sleep current (NOT CONFIRMED: the jumper is mentioned for the FireBeetle 2 ESP32-E in a user forum thread; check the S3 board before cutting).
- Optionally switch panel power with a MOSFET during sleep (as other frame projects do). Not implemented here.

## Known unknowns

- **Panel controller:** no source named the chip. The firmware uses the GxEPD2 class `GxEPD2_730c_ACeP_730`.
- **Battery divider:** the 2:1 on GPIO4 is an assumption. Check the schematic.
- **Deep sleep current:** unmeasured on this board. Reports range from under 20 uA (reseller) to 174 uA (user, other board).
- **FireBeetle variant:** the DFRobot page product-2950 describes 32 MB PSRAM and Wi-Fi through an ESP32-C6, which looks like a P4 board and not the S3. Confirm the model you hold.
- **Operating temperature:** 15 to 35 C per the wiki. Do not place the unit in cold or hot spots.
