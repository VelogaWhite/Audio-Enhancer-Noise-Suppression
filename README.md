# ระบบปรับปรุงคุณภาพเสียงและลดสัญญาณรบกวนแบบเวลาจริง
## FPGA Audio Enhancer & Noise Suppression System

> Mini-Project ต่อยอดจาก Task 3 รายวิชา Signals & Systems / Digital Signal Processing Practical Labs

---

## 📁 โครงสร้างโปรเจกต์ (Project Structure)

```text
Audio-Enhancer-Noise-Suppression/
├── .gitignore               # กำหนดละเว้นไฟล์ชั่วคราว Python, WAV, Quartus build และ Qsys cache
├── README.md                # เอกสารคู่มือการติดตั้ง แผนผังวงจร และการใช้งาน
├── Document/                # เอกสารแบบแผน (Blueprint) และสเปกสถาปัตยกรรมระบบ
│   ├── FPGA Audio Enhancer & Noise Suppression System.md
│   └── FPGA Audio Enhancer & Noise Suppression System.pdf
└── Code/
    ├── FPGA/                # โปรเจกต์ Intel Quartus Prime (DE10-Lite MAX 10 FPGA)
    │   ├── DE10_Lite_Audio_Sampler.qpf  # Quartus Project File
    │   ├── DE10_Lite_Audio_Sampler.qsf  # Pin Assignment & Project Settings
    │   ├── DE10_Lite_Audio_Sampler.vhd  # Top-Level Structural VHDL Entity
    │   ├── clk_en_gen.vhd               # 16 kHz Sampling Tick Generator (จาก 50 MHz)
    │   ├── adc_mic_reader.vhd           # Modular ADC Interface (Channel 1 / A0)
    │   ├── bram_dp_1024x16.vhd          # Dual-Port Ping-Pong Block RAM (1024 x 16-bit)
    │   ├── spi_slave.vhd                # SPI Slave Controller to ESP32
    │   └── adc_qsys/                    # Platform Designer (Qsys) ADC Core Files
    ├── ESP32/               # ซอร์สโค้ด Arduino สำหรับบอร์ด ESP32-S3 UNO
    │   └── ArduinoTask3.ino # SPI Master อ่านข้อมูลจาก FPGA และสตรีม Serial 1,000,000 bps
    └── Python/              # โปรแกรมประมวลผล DSP และ GUI หลัก
        ├── requirements.txt # รายการไลบรารีที่จำเป็น (numpy, scipy, matplotlib, pyserial, sounddevice)
        ├── test_dsp.py      # Unit Test ตรวจสอบความถูกต้องของ DSP Pipeline 4 ขั้นตอน
        └── enhanced_audio_gui.py  # โค้ดโปรแกรมหลัก (GUI + DSP + Real-time Audio + Telemetry)
```

---

## 🔌 แผนผังการต่อวงจรฮาร์ดแวร์ (Hardware Pinout & Connections)

### 1. ไมโครโฟนแอนะล็อก MAX9814 $\leftrightarrow$ บอร์ด DE10-Lite (Arduino Header)
| ขาบน MAX9814 | ตำแหน่งบนบอร์ด DE10-Lite | รายละเอียด |
| :--- | :--- | :--- |
| **`VDD`** | Arduino Header **`3.3V`** (หรือ `5V`) | แหล่งจ่ายไฟเลี้ยงโมดูลไมค์ |
| **`GND`** | Arduino Header **`GND`** | กราวด์ร่วม |
| **`OUT`** | Arduino Header **`A0`** (`PIN_B14`) | สัญญาณเสียงแอนะล็อกเข้า ADC Channel 1 |
| **`GAIN`** | ปล่อยลอย (Unconnected: 40 dB) | อัตราขยายเริ่มต้นของ AGC |

### 2. บอร์ด DE10-Lite (JP1 Header) $\leftrightarrow$ บอร์ด ESP32-S3 UNO
| สัญญาณ SPI | ขาบนบอร์ด DE10-Lite (Header JP1) | ขาบนบอร์ด ESP32-S3 | รายละเอียด |
| :--- | :--- | :--- | :--- |
| **`SPI_SCK`** | JP1 Pin 2 (**`PIN_W10`**) | **`IO12`** | สัญญาณนาฬิกา SPI Clock (4 MHz) |
| **`SPI_CS`** | JP1 Pin 3 (**`PIN_V9`**) | **`IO10`** | สัญญาณ Chip Select (Active Low) |
| **`SPI_MOSI`** | JP1 Pin 4 (**`PIN_W9`**) | **`IO11`** | ข้อมูลจาก ESP32 ไปยัง FPGA |
| **`SPI_MISO`** | JP1 Pin 5 (**`PIN_V8`**) | **`IO13`** | ข้อมูลเสียงจาก FPGA ไปยัง ESP32 |
| **`GND`** | JP1 Pin 12 (หรือจุด GND ใดๆ) | **`GND`** | **Common Ground (จำเป็นอย่างยิ่ง)** |

---

## ⚙️ การติดตั้งและเตรียมสภาพแวดล้อม (Installation)

1. **ติดตั้งไลบรารีที่จำเป็น:**
   ```bash
   pip install -r Code/Python/requirements.txt
   ```

2. **ทดสอบความถูกต้องของ DSP Pipeline (Unit Tests):**
   ```bash
   python -m unittest Code/Python/test_dsp.py
   ```
   *(ผลลัพธ์ต้องผ่านครบทั้ง 5 tests: `OK`)*

---

## 🚀 วิธีการรันโปรแกรม (How to Run)

เรียกใช้งานโปรแกรมหลัก:
```bash
python Code/Python/enhanced_audio_gui.py
```

### ฟีเจอร์หลักของโปรแกรม:
1. **โหมดทดสอบสัญญาณจำลอง (Demo Simulation Mode):**
   * รันทดสอบ DSP Pipeline ได้ทันทีโดยไม่ต้องต่อบอร์ดจริง
   * จำลองเสียงพูดสลับช่วงเงียบ ผสมเสียงฮัมไฟบ้าน 50 Hz และเสียงซ่า 6,500 Hz
2. **โหมดเชื่อมต่อฮาร์ดแวร์จริง (Hardware Serial Mode):**
   * เลือกพอร์ต COM ของ ESP32 และตั้งค่า Baud Rate เป็น **`1000000`**
   * ตรวจจับ Header Sync ไบนารี `0xAA 0x55` และอ่านบล็อกข้อมูล 1,024 ตัวอย่าง (2,048 ไบต์) อัตโนมัติทุกๆ 64 ms ($F_s = 16\text{ kHz}$)
3. **สายพานการประมวลผล DSP Pipeline (4 ขั้นตอน):**
   * **Stage 1 (DC Offset Removal & Scaling):** ลบระดับไฟตรงแอนะล็อกและสเกลข้อมูล 12-bit ADC เข้าสู่มาตรฐาน 16-bit PCM ($\times 16.0$)
   * **Stage 2 (4th-Order Butterworth Bandpass):** ปรับความถี่ตัด High-Pass ($f_{\text{low}}$) และ Low-Pass ($f_{\text{high}}$) แบบเวลาจริง โครงสร้าง SOS ที่คงสถานะ $z_i$ ข้ามบล็อกเพื่อไม่ให้เกิดเสียงคลิก
   * **Stage 3 (Dynamic RMS Noise Gate):** ลดทอนพื้นหลังช่วงเงียบด้วยสมการ Soft-Knee กำลังสอง
   * **Stage 4 (Gain Boost & Limiter):** ขยายเสียงพูดและป้องกันอาการ Integer Overflow / Audio Clipping ด้วย `np.clip`
4. **การแสดงผลเชิงวิศวกรรมแบบ Real-Time (Live Telemetry & Analytics):**
   * **Dominant / Peak Frequency ($f_{\text{peak}}$):** ค้นหายอดคลื่นความถี่หลักแบบสด พร้อมจุดมาร์กเกอร์สีแดงบนกราฟ FFT
   * **Noise Reduction / Stopband Attenuation (dB):** คำนวณอัตราการกดเสียงรบกวนนอกย่านผ่านเปรียบเทียบก่อนและหลัง
   * **Peak Amplitude ($V_{\text{peak}}$) & RMS:** แสดงค่าแอมพลิจูดสูงสุดและพลังงานเฉลี่ยของบล็อกเสียง
   * **Dynamic Legend Synchronization:** ข้อความบน Legend ของกราฟจะซิงก์เปลี่ยนตัวเลขตาม Slider ทันที
5. **การมอนิเตอร์เสียงสด & บันทึกไฟล์:**
   * สลับฟังเสียงสดผ่านลำโพง/หูฟังด้วยปุ่ม **Filter / Bypass (Hear Raw)**
   * บันทึกเสียงที่ปรับปรุงแล้วเป็นไฟล์มาตรฐาน **16-bit PCM WAV** ลงโฟลเดอร์ `recordings/`
