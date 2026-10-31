// kiro-crew-deck firmware: wake, ask the bridge what to show, stream the image
// to the e-paper, sleep. Everything happens in setup(); loop() is never reached.
#include <Arduino.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <ImprovWiFiLibrary.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <GxEPD2_7C.h>  // pulls in the 7-colour driver headers
#include <driver/gpio.h>
#include <driver/rtc_io.h>
#include <esp_sleep.h>
#include <time.h>

#include "config.h"

// Driver: GxEPD2_730c_ACeP_730 is the Waveshare 7.3" (F). We use the raw EPD class,
// not the GFX wrapper, so no framebuffer is allocated and no drawing code runs
// (Adafruit GFX is still linked in as a dependency of GxEPD2).
static GxEPD2_730c_ACeP_730 epd(EPD_CS, EPD_DC, EPD_RST, EPD_BUSY);

// State that survives deep sleep.
// Holds 15 chars; the bridge sends a 12-char sha1 prefix.
RTC_DATA_ATTR static char rtcHash[16] = "";
static_assert(sizeof(rtcHash) > 12, "rtcHash must fit the bridge image_hash");
RTC_DATA_ATTR static time_t rtcLastRefreshS = 0;  // system time survives deep sleep (RTC timer)
RTC_DATA_ATTR static char rtcScreenId[48] = "";
RTC_DATA_ATTR static char rtcActions[3][12] = {"", "", ""};  // action name per button A/B/C
RTC_DATA_ATTR static char rtcPendingBtn = 0;                  // button not yet delivered
RTC_DATA_ATTR static char rtcPendingScreen[48] = "";

static Preferences prefs;
static WiFiClient plainClient;
static WiFiClientSecure tlsClient;

// Switched HAT supply: on while the panel is used, held off during deep sleep.
static void vextOn() {
#ifdef VEXT
  gpio_hold_dis((gpio_num_t)VEXT);
  pinMode(VEXT, OUTPUT);
  digitalWrite(VEXT, VEXT_ON_LEVEL);
  delay(20);
#endif
}

// Drives a pin LOW and latches it through deep sleep.
static void holdLow(int pin) {
  gpio_hold_dis((gpio_num_t)pin);
  pinMode(pin, OUTPUT);
  digitalWrite(pin, LOW);
  gpio_hold_en((gpio_num_t)pin);
}

// Unused Heltec peripherals, kept off whenever the chip runs (the OLED is held in reset).
// Pin numbers come from the research notes; FEM/VFEM polarity is NOT CONFIRMED (LOW = off assumed).
static void parkUnusedPeripherals() {
#ifdef OLED_RST
  holdLow(OLED_RST);
#endif
#ifdef LORA_FEM_EN
  holdLow(LORA_FEM_EN);
#endif
#ifdef LORA_VFEM
  holdLow(LORA_VFEM);
#endif
}

// Everything that could leak current into the HAT or the board while asleep.
static void parkForSleep() {
#ifdef VEXT
  // Release the bus and float the HAT signals first: driven high, they would back-power the
  // HAT through its input diodes once Vext is off. epd.init() and SPI.begin() re-drive them on wake.
  SPI.end();
  for (int p : {EPD_SCK, EPD_MOSI, EPD_CS, EPD_DC, EPD_RST}) pinMode(p, INPUT);  // only when Vext cuts the HAT
  pinMode(VEXT, OUTPUT);
  digitalWrite(VEXT, !VEXT_ON_LEVEL);
  gpio_hold_en((gpio_num_t)VEXT);
#endif
#ifdef BAT_ADC_CTRL
  holdLow(BAT_ADC_CTRL);
#endif
  parkUnusedPeripherals();
  gpio_deep_sleep_hold_en();
}

static void sleepFor(uint32_t seconds) {
  const uint8_t pins[] = {BTN_A, BTN_B, BTN_C};
  const int nWake = BTN_C_WAKE ? 3 : 2;
  // Wait for all buttons released, otherwise a held button wakes us again at once.
  for (uint8_t p : pins) pinMode(p, INPUT_PULLUP);
  for (uint32_t t0 = millis(); millis() - t0 < 2000;) {
    if (digitalRead(BTN_A) && digitalRead(BTN_B) && digitalRead(BTN_C)) break;
    delay(10);
  }
  uint64_t mask = 0;
  for (int i = 0; i < nWake; i++) {
    uint8_t p = pins[i];
    rtc_gpio_init((gpio_num_t)p);
    rtc_gpio_set_direction((gpio_num_t)p, RTC_GPIO_MODE_INPUT_ONLY);
    rtc_gpio_pullup_en((gpio_num_t)p);
    rtc_gpio_pulldown_dis((gpio_num_t)p);
    mask |= 1ULL << p;
  }
  // Needed for the RTC pull-ups on the buttons to stay powered in deep sleep.
  esp_sleep_pd_config(ESP_PD_DOMAIN_RTC_PERIPH, ESP_PD_OPTION_ON);
  parkForSleep();
  esp_sleep_enable_ext1_wakeup(mask, ESP_EXT1_WAKEUP_ANY_LOW);
  esp_sleep_enable_timer_wakeup((uint64_t)seconds * 1000000ULL);
  Serial.printf("sleep %us\n", (unsigned)seconds);
  Serial.flush();
  esp_deep_sleep_start();
}

// --- Wi-Fi ---------------------------------------------------------------

static void onImprovConnected(const char* ssid, const char* pass) {
  prefs.putString("ssid", ssid);
  prefs.putString("pass", pass);
}

// Waits for Improv Wi-Fi over USB serial (ESP Web Tools or improv-wifi.com).
static void provision() {
  Serial.println("no Wi-Fi stored: waiting for Improv provisioning");
  ImprovWiFi improv(&Serial);
  improv.setDeviceInfo(ImprovTypes::ChipFamily::CF_ESP32_S3, "kiro-crew-deck", FW_VERSION, "Kiro Crew Deck");
  improv.onImprovConnected(onImprovConnected);
  WiFi.mode(WIFI_STA);
  for (uint32_t t0 = millis(); millis() - t0 < PROVISION_MS;) {
    improv.handleSerial();
    if (improv.isConnected()) return;
    delay(1);
  }
}

static bool connectWifi() {
  String ssid = prefs.getString("ssid");
  if (ssid.isEmpty()) {
    provision();
    ssid = prefs.getString("ssid");
    if (ssid.isEmpty()) return false;
  }
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid.c_str(), prefs.getString("pass").c_str());
  for (uint32_t t0 = millis(); WiFi.status() != WL_CONNECTED; delay(100))
    if (millis() - t0 > WIFI_TIMEOUT_MS) return false;
  return true;
}

// --- Bridge --------------------------------------------------------------

static bool openHttp(HTTPClient& http, const String& pathAndQuery) {
  String url = String(BRIDGE_URL) + pathAndQuery;
  bool ok;
  if (url.startsWith("https://")) {
    tlsClient.setInsecure();  // no CA bundle on the device; see README
    ok = http.begin(tlsClient, url);
  } else {
    ok = http.begin(plainClient, url);
  }
  http.addHeader("Authorization", "Bearer " DEVICE_TOKEN);
  http.setTimeout(15000);
  return ok;
}

static float readBattery() {
#ifdef BAT_ADC_CTRL
  gpio_hold_dis((gpio_num_t)BAT_ADC_CTRL);
  pinMode(BAT_ADC_CTRL, OUTPUT);
  digitalWrite(BAT_ADC_CTRL, BAT_ADC_CTRL_ON_LEVEL);
  delay(10);
#endif
  analogSetPinAttenuation(BAT_ADC, ADC_11db);
  float v = analogReadMilliVolts(BAT_ADC) * BAT_DIVIDER / 1000.0f;
#ifdef BAT_ADC_CTRL
  digitalWrite(BAT_ADC_CTRL, !BAT_ADC_CTRL_ON_LEVEL);
#endif
  return v;
}

// Sends the pending button press. It is cleared once the bridge answered with
// any HTTP status; on a network error it stays queued for the next connection.
static void postPendingAction() {
  if (!rtcPendingBtn) return;
  HTTPClient http;
  if (!openHttp(http, "/api/action")) return;
  http.addHeader("Content-Type", "application/json");
  char body[112];
  snprintf(body, sizeof(body), "{\"screen_id\":\"%s\",\"button\":\"%c\"}", rtcPendingScreen, rtcPendingBtn);
  int code = http.POST(body);
  Serial.printf("action %c -> %d\n", rtcPendingBtn, code);
  http.end();
  if (code > 0) rtcPendingBtn = 0;
}

// Streams the .bin into the panel controller strip by strip, then refreshes.
// Returns true only if all IMG_BYTES arrived and the panel was refreshed.
static bool showImage(const String& imagePath) {
  HTTPClient http;
  if (imagePath.isEmpty() || !openHttp(http, imagePath)) return false;
  int code = http.GET();
  if (code != 200 || http.getSize() != IMG_BYTES) {
    Serial.printf("image GET %d size %d\n", code, http.getSize());
    http.end();
    return false;
  }

  vextOn();
  SPI.begin(EPD_SCK, -1, EPD_MOSI, -1);  // GxEPD2's own SPI.begin() is then a no-op; CS is driven by GxEPD2
  epd.init(0);
  epd.setPaged();  // GxEPD2 "paged" mode: full-width strips written in order
  static uint8_t strip[STRIP_BYTES];
  WiFiClient* stream = http.getStreamPtr();
  bool ok = true;
  for (int y = 0; y < IMG_H && ok; y += STRIP_ROWS) {
    ok = stream->readBytes(strip, STRIP_BYTES) == STRIP_BYTES;
    if (ok) epd.writeNative(strip, nullptr, 0, y, IMG_W, STRIP_ROWS);
  }
  http.end();
  WiFi.disconnect(true);  // radio off during the ~35 s refresh
  WiFi.mode(WIFI_OFF);

  if (ok) epd.refresh();
  epd.hibernate();
  return ok;
}

// --- Main cycle ----------------------------------------------------------

void setup() {
  Serial.begin(115200);
  prefs.begin("kcd", false);
  parkUnusedPeripherals();

  // Hold button A for 5 s at power-on or reset (not on a timer or button wake) to forget Wi-Fi.
  pinMode(BTN_A, INPUT_PULLUP);
  if (esp_sleep_get_wakeup_cause() == ESP_SLEEP_WAKEUP_UNDEFINED && !digitalRead(BTN_A)) {
    uint32_t t0 = millis();
    while (!digitalRead(BTN_A) && millis() - t0 < 5000) delay(10);
    if (millis() - t0 >= 5000) {
      prefs.remove("ssid");
      prefs.remove("pass");
      Serial.println("wifi credentials cleared");
    }
  }

  char button = 0;
  if (esp_sleep_get_wakeup_cause() == ESP_SLEEP_WAKEUP_EXT1) {
    uint64_t m = esp_sleep_get_ext1_wakeup_status();
    button = (m & (1ULL << BTN_A)) ? 'A' : (m & (1ULL << BTN_B)) ? 'B' : (m & (1ULL << BTN_C)) ? 'C' : 0;
  }
  Serial.printf("wake button=%c hash=%s\n", button ? button : '-', rtcHash);
  if (button) {
    const char* act = rtcActions[button - 'A'];
    if (rtcScreenId[0] && strcmp(act, "none") != 0) {  // unknown map (empty) still posts
      rtcPendingBtn = button;
      strlcpy(rtcPendingScreen, rtcScreenId, sizeof(rtcPendingScreen));
    }
  }

  if (!connectWifi()) {
    Serial.println("wifi failed");
    sleepFor(RETRY_SLEEP_S);
  }

  postPendingAction();

  // The panel must rest >= MIN_SLEEP_S between refreshes: an early button wake only posts.
  time_t sinceRefresh = time(nullptr) - rtcLastRefreshS;
  if (button && rtcHash[0] && sinceRefresh < MIN_SLEEP_S) sleepFor(MIN_SLEEP_S - sinceRefresh);

  HTTPClient http;
  char q[48];
  snprintf(q, sizeof(q), "/api/display?battery=%.2f", readBattery());
  if (!openHttp(http, q) || http.GET() != 200 || http.getSize() > 4096) {
    Serial.println("display GET failed or body too large");
    http.end();
    sleepFor(RETRY_SLEEP_S);
  }
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, http.getString());
  http.end();
  if (err) {
    Serial.printf("bad json: %s\n", err.c_str());
    sleepFor(RETRY_SLEEP_S);
  }

  String hash = doc["image_hash"] | "";
  String imageUrl = doc["image_url"] | "";
  uint32_t refresh = constrain(doc["refresh_rate"] | MIN_SLEEP_S, MIN_SLEEP_S, MAX_SLEEP_S);
  for (int i = 0; i < 3; i++) {
    const char key[2] = {(char)('A' + i), 0};
    strlcpy(rtcActions[i], doc["buttons"][key] | "", sizeof(rtcActions[i]));
  }
  strlcpy(rtcScreenId, doc["screen_id"] | "", sizeof(rtcScreenId));

  if (!hash.isEmpty() && hash != rtcHash) {
    if (showImage(imageUrl)) {
      strlcpy(rtcHash, hash.c_str(), sizeof(rtcHash));
      rtcLastRefreshS = time(nullptr);
    } else rtcHash[0] = 0;  // force a retry next cycle
  } else {
    Serial.println("image unchanged");
  }
  sleepFor(refresh);
}

void loop() {}
