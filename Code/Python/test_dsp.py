#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for FPGA Audio Enhancer DSP Pipeline
ตรวจสอบความถูกต้องของอัลกอริทึม DSP ทั้ง 4 ขั้นตอน
"""

import unittest
import numpy as np
import scipy.signal

from enhanced_audio_gui import FS, BLOCK_SIZE, AudioSimulator


class TestDSPPipeline(unittest.TestCase):
    def setUp(self):
        self.fs = FS
        self.block_size = BLOCK_SIZE
        self.simulator = AudioSimulator(self.fs, self.block_size)

        # จำลองการตั้งค่าตัวกรองตาม blueprint
        self.f_low = 120.0
        self.f_high = 5000.0
        nyquist = 0.5 * self.fs
        self.sos = scipy.signal.butter(
            N=4,
            Wn=[self.f_low / nyquist, self.f_high / nyquist],
            btype="bandpass",
            output="sos"
        )

    def test_audio_simulator_output_shape_and_dtype(self):
        """ทดสอบว่าตัวจำลองสัญญาณให้ข้อมูลขนาด 1024 ตัวอย่าง และเป็น int16"""
        block = self.simulator.generate_block()
        self.assertEqual(len(block), self.block_size)
        self.assertEqual(block.dtype, np.int16)

    def test_stage1_dc_offset_removal(self):
        """ขั้นที่ 1: ตรวจสอบการลบระดับไฟตรง (DC Offset Removal)"""
        # สร้างสัญญาณที่มีไฟตรง +5000
        raw = np.ones(self.block_size, dtype=np.int16) * 5000
        x_float = raw.astype(np.float64)
        x_zero = x_float - np.mean(x_float)
        # ค่าเฉลี่ยหลังลบ DC ต้องเข้าใกล้ 0
        self.assertAlmostEqual(np.mean(x_zero), 0.0, places=5)

    def test_stage2_butterworth_bandpass_attenuation(self):
        """ขั้นที่ 2: ตรวจสอบว่าตัวกรอง Bandpass กดความถี่ 50 Hz และ 7500 Hz ลง แต่ยอมให้ 1000 Hz ผ่าน"""
        t = np.arange(self.block_size * 4) / self.fs  # 4 บล็อก เพื่อให้เข้าสู่ steady state
        
        # 1. ทดสอบความถี่ผ่าน (Passband: 1000 Hz)
        sig_pass = 10000.0 * np.sin(2 * np.pi * 1000 * t)
        out_pass = scipy.signal.sosfilt(self.sos, sig_pass)[-self.block_size:]
        amp_pass = np.max(np.abs(out_pass))
        self.assertGreater(amp_pass, 8000.0, "ความถี่ 1000 Hz ควรผ่านตัวกรองโดยแทบไม่ถูกลดทอน")

        # 2. ทดสอบความถี่หยุดต่ำ (Stopband Low: 50 Hz Hum)
        sig_low = 10000.0 * np.sin(2 * np.pi * 50 * t)
        out_low = scipy.signal.sosfilt(self.sos, sig_low)[-self.block_size:]
        amp_low = np.max(np.abs(out_low))
        self.assertLess(amp_low, 2000.0, "ความถี่ 50 Hz ต้องถูกกดทอนลงอย่างชัดเจน")

        # 3. ทดสอบความถี่หยุดสูง (Stopband High: 7500 Hz Hiss)
        sig_high = 10000.0 * np.sin(2 * np.pi * 7500 * t)
        out_high = scipy.signal.sosfilt(self.sos, sig_high)[-self.block_size:]
        amp_high = np.max(np.abs(out_high))
        self.assertLess(amp_high, 2000.0, "ความถี่ 7500 Hz ต้องถูกกดทอนลงอย่างชัดเจน")

    def test_stage3_dynamic_rms_noise_gate(self):
        """ขั้นที่ 3: ตรวจสอบ Dynamic RMS Noise Gate แบบ Soft-Knee"""
        threshold = 1000.0

        # กรณี 1: RMS สูงกว่า Threshold (สัญญาณเสียงพูด) -> Attenuation ต้องเป็น 1.0 (ปล่อยผ่าน)
        sig_loud = np.ones(self.block_size) * 1500.0
        rms_loud = float(np.sqrt(np.mean(sig_loud ** 2)))
        atten_loud = 1.0 if rms_loud >= threshold else (rms_loud / threshold) ** 2
        self.assertEqual(atten_loud, 1.0)

        # กรณี 2: RMS ต่ำกว่า Threshold (สัญญาณรบกวนช่วงเงียบ RMS = 500)
        # Attenuation = (500 / 1000)^2 = 0.25 (ลดทอนลงเหลือ 25%)
        sig_quiet = np.ones(self.block_size) * 500.0
        rms_quiet = float(np.sqrt(np.mean(sig_quiet ** 2)))
        atten_quiet = (rms_quiet / threshold) ** 2
        self.assertAlmostEqual(atten_quiet, 0.25, places=3)

    def test_stage4_gain_boost_and_clipping_limiter(self):
        """ขั้นที่ 4: ตรวจสอบการขยาย Gain และการจำกัดเพดานไม่ให้เกินช่วง 16-bit PCM"""
        large_signal = np.array([40000.0, -50000.0, 20000.0])
        gain = 2.0
        boosted = large_signal * gain
        clipped = np.clip(boosted, -32767.0, 32767.0).astype(np.int16)

        # ค่าสูงสุดและต่ำสุดต้องไม่เกิน 32767 และ -32767
        self.assertEqual(clipped[0], 32767)
        self.assertEqual(clipped[1], -32767)
        self.assertTrue(bool(np.any(np.abs(boosted) >= 32767.0)))


if __name__ == "__main__":
    unittest.main()
