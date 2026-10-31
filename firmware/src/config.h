#pragma once
#include <Arduino.h>

#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#endif

// Pins for DFRobot FireBeetle 2 ESP32-S3. The SPI bus uses the board defaults
// (SCK GPIO17, MOSI GPIO15), which GxEPD2 picks via SPI.begin().
#define EPD_CS    18  // D6
#define EPD_DC     3  // D2
#define EPD_RST   38  // D3
#define EPD_BUSY  14  // D10, active low (low = busy)

// Buttons to GND, internal pull-up. Must be RTC-capable GPIOs (0..21) for ext1 wake.
#define BTN_A      7  // D5, approve
#define BTN_B      9  // D7, reject
#define BTN_C     12  // D12, stop

// Battery sense: ADC pin and divider ratio (Vbat = Vpin * BAT_DIVIDER).
// ASSUMPTION: 2:1 divider on A0 (GPIO4). Check the FireBeetle 2 S3 schematic.
#define BAT_ADC_PIN 4
#define BAT_DIVIDER 2.0f

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
