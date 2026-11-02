# ระบบปรับปรุงคุณภาพเสียงและลดสัญญาณรบกวนแบบเวลาจริง
## FPGA Audio Enhancer & Noise Suppression System

> Mini-Project ต่อยอดจาก Task 3 รายวิชา Signals & Systems / Digital Signal Processing Practical Labs

---

## 📁 โครงสร้างโปรเจกต์ (Project Structure)

```text
Signal_Project2/
├── .gitignore               # ละเว้นไฟล์ขยะ Python, WAV และ Quartus build files
├── README.md                # เอกสารคู่มือการติดตั้งและการใช้งาน
├── Document/                # เอกสารแบบแผน (Blueprint) และรายงานผลการทดลอง
│   ├── FPGA Audio Enhancer & Noise Suppression System.md
│   └── FPGA Audio Enhancer & Noise Suppression System.pdf
└── Code/
    ├── FPGA/                # โปรเจกต์ Intel Quartus Prime (DE10-Lite MAX 10 FPGA)
    └── Python/              # โปรแกรมประมวลผล DSP และ GUI หลัก
        ├── requirements.txt # รายการไลบรารีที่จำเป็น
        ├── test_dsp.py      # Unit Test ตรวจสอบความถูกต้องของ DSP Pipeline
        └── enhanced_audio_gui.py  # โค้ดโปรแกรมหลัก (GUI + DSP + Real-time Audio)
```

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

---

## 🚀 วิธีการรันโปรแกรม (How to Run)

เรียกใช้งานโปรแกรมหลัก:
```bash
python Code/Python/enhanced_audio_gui.py
```

### ฟีเจอร์หลักของโปรแกรม:
1. **โหมดทดสอบสัญญาณจำลอง (Demo Simulation Mode):**
   * สามารถรันทดสอบ DSP Pipeline ได้ทันทีโดยไม่ต้องต่อบอร์ดจริง
   * จำลองเสียงพูด (300 Hz, 1,000 Hz, 2,500 Hz) ผสมเสียงฮัมไฟบ้าน 50 Hz, เสียงซ่า 6,500 Hz และสัญญาณรบกวนพื้นหลัง
   * สลับช่วงพูดและช่วงเงียบอัตโนมัติ เพื่อให้เห็นการทำงานของ Dynamic Noise Gate อย่างชัดเจน
2. **โหมดเชื่อมต่อฮาร์ดแวร์จริง (Hardware Serial Mode):**
   * เลือกพอร์ต COM ของ ESP32 และความเร็ว Baud Rate (แนะนำ `921600` หรือ `2000000`)
   * ตรวจจับ Header Sync ไบนารี `0xAA 0x55` และอ่านบล็อกข้อมูล 1,024 ตัวอย่าง (2,048 ไบต์) ต่อเนื่อง
3. **สายพานการประมวลผล DSP Pipeline (4 ขั้นตอน):**
   * **Stage 1 (DC Offset Removal):** ลบระดับไฟตรงแอนะล็อก
   * **Stage 2 (4th-Order Butterworth Bandpass):** ปรับความถี่ตัด High-Pass ($f_{\text{low}}$) และ Low-Pass ($f_{\text{high}}$) แบบเวลาจริง โดยใช้โครงสร้าง SOS ที่คงสถานะ $z_i$ ข้ามบล็อกเพื่อตัดเสียงคลิก
   * **Stage 3 (Dynamic RMS Noise Gate):** ลดทอนพื้นหลังช่วงเงียบด้วยสมการ Soft-Knee กำลังสอง
   * **Stage 4 (Gain Boost & Limiter):** ขยายเสียงพูดและป้องกันเสียงแตกด้วย `np.clip`
4. **การมอนิเตอร์เสียงสด & บันทึกไฟล์:**
   * สลับฟังเสียงสดผ่านลำโพง/หูฟังด้วยปุ่ม **Filter / Bypass (Hear Raw)**
   * บันทึกเสียงที่ปรับปรุงแล้วเป็นไฟล์มาตรฐาน **16-bit PCM WAV** ลงโฟลเดอร์ `recordings/`
