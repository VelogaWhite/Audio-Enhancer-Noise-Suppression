#include <Arduino.h>
#include <SPI.h>

// กำหนด Pinout SPI ตามโครงสร้างบอร์ด ESP32-S3 UNO
#define FPGA_CS       10  // ขา IO10 ไปยัง JP1 Pin 3 (PIN_V9)
#define SPI_MOSI      11  // ขา IO11 ไปยัง JP1 Pin 4 (PIN_W9)
#define SPI_SCK       12  // ขา IO12 ไปยัง JP1 Pin 2 (PIN_W10)
#define SPI_MISO      13  // ขา IO13 ไปยัง JP1 Pin 5 (PIN_V8)

#define BLOCK_SIZE    1024
uint16_t audio_buffer[BLOCK_SIZE];

// ความเร็ว SPI 4 MHz, MSB First, SPI Mode 0
SPISettings fpgaSpiSettings(4000000, MSBFIRST, SPI_MODE0);

// Header Sync 2 ไบต์สำหรับล็อกเฟรมใน Python
const uint8_t SYNC_HEADER[2] = {0xAA, 0x55};

void setup() {
  Serial.begin(1000000);

  pinMode(FPGA_CS, OUTPUT);
  digitalWrite(FPGA_CS, HIGH); // Idle เป็น HIGH

  // กำหนดขา SPI ให้ตรงกับฮาร์ดแวร์ ESP32-S3
  // พารามิเตอร์: SPI.begin(sck, miso, mosi, ss)
  SPI.begin(SPI_SCK, SPI_MISO, SPI_MOSI, FPGA_CS);
  delay(200);
}

void loop() {
  unsigned long start_time = millis();

  // 1. ดึง CS ลง LOW เพื่อเริ่มส่งข้อมูลจาก BRAM ของ FPGA
  SPI.beginTransaction(fpgaSpiSettings);
  digitalWrite(FPGA_CS, LOW);
  delayMicroseconds(2); // ให้เวลา FPGA ซิงค์ขอบขาตกของ CS

  // 2. ดึงข้อมูล 1024 ตัวอย่าง (ตัวอย่างละ 16 บิต = 2 ไบต์)
  for (int i = 0; i < BLOCK_SIZE; i++) {
    uint8_t msb = SPI.transfer(0x00);
    uint8_t lsb = SPI.transfer(0x00);
    audio_buffer[i] = ((uint16_t)msb << 8) | lsb;
  }

  // 3. ดึง CS กลับขึ้น HIGH เพื่อ Reset ตัวชี้ตำแหน่งอ่านใน FPGA
  digitalWrite(FPGA_CS, HIGH);
  SPI.endTransaction();

  // 4. ส่ง Sync Header 2 ไบต์ แล้วตามด้วย Data Block 2048 ไบต์
  Serial.write(SYNC_HEADER, 2);
  Serial.write((uint8_t*)audio_buffer, BLOCK_SIZE * sizeof(uint16_t));

  // 5. คุมรอบการทำงานให้ใกล้เคียง 64 ms (1024 ตัวอย่าง / 16 kHz = 64 ms)
  unsigned long elapsed = millis() - start_time;
  if (elapsed < 64) {
    delay(64 - elapsed);
  }
}