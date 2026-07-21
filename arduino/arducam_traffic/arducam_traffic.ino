/*
 * Smart Traffic-Density Monitoring System — Arduino edge node
 * -----------------------------------------------------------
 * Board : Arduino Nano 33 BLE (nRF52840, 3.3 V logic)
 * Camera: Arducam Mini 2MP Plus (OV2640, SPI + I2C)
 *
 * Role in the system:
 *   - Captures a JPEG frame from the OV2640 on request and streams it to the
 *     laptop over USB serial (the laptop runs YOLO — the Arduino cannot).
 *   - Drives the on-board RGB LED as a "traffic light" based on the density
 *     level the laptop sends back.
 *
 * Serial protocol (115200 baud nominal; USB-CDC runs at full USB speed):
 *   Laptop -> Arduino (single ASCII byte):
 *       'c'  capture one frame and stream it back
 *       '0'  set LED green   (Low density)
 *       '1'  set LED amber   (Moderate density)
 *       '2'  set LED red     (High density)
 *       'x'  LED off
 *   Arduino -> Laptop (one frame):
 *       0xA5 0x5A                 magic start marker
 *       <len : uint32 LE>         number of JPEG bytes to follow
 *       <len bytes>               the JPEG image (starts FFD8, ends FFD9)
 *
 * Library: install "ArduCAM" via the Library Manager, then edit its
 * memorysaver.h and enable ONLY:   #define OV2640_MINI_2MP_PLUS
 *
 * Wiring (Arducam Mini 2MP Plus -> Nano 33 BLE):
 *   CS   -> D7      MOSI -> D11     MISO -> D12     SCK -> D13
 *   SDA  -> A4      SCL  -> A5      VCC  -> 3V3     GND -> GND
 *
 * NOTE: The ArduCAM library targets many MCUs but nRF52840/mbed support can
 * be patchy depending on library version. If it will not compile for the
 * Nano 33 BLE, see the README fallback (run the camera on an ESP32-CAM / Uno
 * and keep the Nano 33 BLE as the BLE traffic-light actuator only).
 */

#include <Wire.h>
#include <SPI.h>
#include <ArduCAM.h>
#include "memorysaver.h"

#if !(defined OV2640_MINI_2MP_PLUS)
  #error "Enable #define OV2640_MINI_2MP_PLUS in the ArduCAM library's memorysaver.h"
#endif

const int CS = 7;                 // camera chip-select
ArduCAM myCAM(OV2640, CS);

void setLed(int level) {
  // Nano 33 BLE on-board RGB LED is ACTIVE-LOW (LOW = on).
  digitalWrite(LEDR, HIGH);
  digitalWrite(LEDG, HIGH);
  digitalWrite(LEDB, HIGH);
  switch (level) {
    case 0: digitalWrite(LEDG, LOW); break;                       // green
    case 1: digitalWrite(LEDR, LOW); digitalWrite(LEDG, LOW); break; // amber
    case 2: digitalWrite(LEDR, LOW); break;                       // red
    default: break;                                               // off
  }
}

void setup() {
  Serial.begin(115200);
  while (!Serial) { /* wait for USB-CDC */ }

  pinMode(LEDR, OUTPUT);
  pinMode(LEDG, OUTPUT);
  pinMode(LEDB, OUTPUT);
  setLed(-1);                     // LED off at boot

  pinMode(CS, OUTPUT);
  digitalWrite(CS, HIGH);
  Wire.begin();
  SPI.begin();

  // Reset the CPLD on the Arducam.
  myCAM.write_reg(0x07, 0x80);
  delay(100);
  myCAM.write_reg(0x07, 0x00);
  delay(100);

  // Verify SPI bus to the Arducam.
  myCAM.write_reg(ARDUCHIP_TEST1, 0x55);
  if (myCAM.read_reg(ARDUCHIP_TEST1) != 0x55) {
    Serial.println("ERROR: Arducam SPI not found (check CS/MOSI/MISO/SCK).");
    while (1) { setLed(2); delay(300); setLed(-1); delay(300); }
  }

  // Verify the OV2640 sensor over I2C.
  uint8_t vid, pid;
  myCAM.wrSensorReg8_8(0xff, 0x01);
  myCAM.rdSensorReg8_8(OV2640_CHIPID_HIGH, &vid);
  myCAM.rdSensorReg8_8(OV2640_CHIPID_LOW, &pid);
  if (vid != 0x26 || (pid != 0x41 && pid != 0x42)) {
    Serial.println("ERROR: OV2640 not detected (check SDA/SCL).");
    while (1) { setLed(2); delay(300); setLed(1); delay(300); }
  }

  myCAM.set_format(JPEG);
  myCAM.InitCAM();
  myCAM.OV2640_set_JPEG_size(OV2640_320x240);  // small = faster transfer
  delay(1000);
  myCAM.clear_fifo_flag();

  Serial.println("READY");        // handshake line the laptop can wait for
}

void captureAndStream() {
  myCAM.flush_fifo();
  myCAM.clear_fifo_flag();
  myCAM.start_capture();
  while (!myCAM.get_bit(ARDUCHIP_TRIG, CAP_DONE_MASK)) { /* wait */ }

  uint32_t len = myCAM.read_fifo_length();
  if (len == 0 || len >= 0x07ffff) {            // 0 or > ~512KB is invalid
    myCAM.clear_fifo_flag();
    return;
  }

  // Frame header: magic + 4-byte little-endian length.
  Serial.write(0xA5);
  Serial.write(0x5A);
  Serial.write((uint8_t)(len & 0xff));
  Serial.write((uint8_t)((len >> 8) & 0xff));
  Serial.write((uint8_t)((len >> 16) & 0xff));
  Serial.write((uint8_t)((len >> 24) & 0xff));

  // Burst-read the JPEG out of the camera FIFO and stream it.
  myCAM.CS_LOW();
  myCAM.set_fifo_burst();
  for (uint32_t i = 0; i < len; i++) {
    Serial.write(SPI.transfer(0x00));
  }
  myCAM.CS_HIGH();
  myCAM.clear_fifo_flag();
}

void loop() {
  if (!Serial.available()) return;
  char cmd = Serial.read();
  switch (cmd) {
    case 'c': captureAndStream(); break;
    case '0': setLed(0); break;
    case '1': setLed(1); break;
    case '2': setLed(2); break;
    case 'x': setLed(-1); break;
    default: break;                 // ignore stray bytes / newlines
  }
}
