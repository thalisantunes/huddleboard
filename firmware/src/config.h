#pragma once
#include <Arduino.h>

#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#endif

// Pins. Defaults are for the DFRobot FireBeetle 2 ESP32-S3 (generic S3 example);
// platformio.ini overrides them per board with -D flags.
#ifndef EPD_SCK
#define EPD_SCK   17  // board default SPI
#endif
#ifndef EPD_MOSI
#define EPD_MOSI  15  // board default SPI
#endif
#ifndef EPD_CS
#define EPD_CS    18  // D6
#endif
#ifndef EPD_DC
#define EPD_DC     3  // D2
#endif
#ifndef EPD_RST
#define EPD_RST   38  // D3
#endif
#ifndef EPD_BUSY
#define EPD_BUSY  14  // D10, active low (low = busy)
#endif

// Buttons to GND, internal pull-up. Wake from deep sleep (ext1) needs RTC GPIOs (0..21).
#ifndef BTN_A
#define BTN_A      7  // D5, approve
#endif
#ifndef BTN_B
#define BTN_B      9  // D7, reject
#endif
#ifndef BTN_C
#define BTN_C     12  // D12, stop
#endif
#ifndef BTN_C_WAKE
#define BTN_C_WAKE 1  // 0 = button C does not wake the chip from deep sleep
#endif

// Battery sense: ADC pin and divider ratio (Vbat = Vpin * BAT_DIVIDER).
// FireBeetle: ASSUMPTION 2:1 divider on A0 (GPIO4), check the schematic.
#ifndef BAT_ADC
#define BAT_ADC 4
#endif
#ifndef BAT_DIVIDER
#define BAT_DIVIDER 2.0f
#endif
// Optional pin that must be driven to BAT_ADC_CTRL_ON_LEVEL while reading (Heltec: GPIO37).
// #define BAT_ADC_CTRL <gpio>
#ifndef BAT_ADC_CTRL_ON_LEVEL
#define BAT_ADC_CTRL_ON_LEVEL 1
#endif

// Optional switched supply for the e-paper HAT (Heltec Vext). Undefined = HAT always powered.
// #define VEXT <gpio>
#ifndef VEXT_ON_LEVEL
#define VEXT_ON_LEVEL 1
#endif

#define FW_VERSION "0.1.0"

#define MIN_SLEEP_S      180  // panel needs >= 180 s between refreshes
#define MAX_SLEEP_S     3600  // cap on the bridge's refresh_rate
#define RETRY_SLEEP_S    300  // after a Wi-Fi or bridge failure
#define WIFI_TIMEOUT_MS 20000
#define PROVISION_MS   300000 // how long to wait for Improv when no Wi-Fi is stored

// Image: 800x480, 4 bpp packed (2 px/byte), streamed in strips of STRIP_ROWS rows.
#define IMG_W      800
#define IMG_H      480
#define IMG_BYTES  (IMG_W * IMG_H / 2)
#define STRIP_ROWS 10
#define STRIP_BYTES (IMG_W * STRIP_ROWS / 2)  // 4000 bytes
