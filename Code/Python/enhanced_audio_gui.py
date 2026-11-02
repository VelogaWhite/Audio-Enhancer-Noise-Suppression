#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
FPGA Audio Enhancer & Noise Suppression System
โปรแกรมประมวลผลและปรับปรุงคุณภาพเสียงแบบเวลาจริง (Host PC Python GUI)
===============================================================================
วิชา: Signals & Systems / Digital Signal Processing Practical Labs (ต่อยอดจาก Task 3)
ฮาร์ดแวร์ต้นทาง: บอร์ด DE10-Lite MAX 10 FPGA + ESP32/ESP32-S3 (Fs = 16 kHz, N = 1024)
ไฟล์หลัก: enhanced_audio_gui.py
===============================================================================
"""

import os
import sys
import time
import queue
import wave
import threading
from datetime import datetime
from typing import Optional, Tuple

import numpy as np
import scipy.signal

# GUI & Plotting
import tkinter as tk
from tkinter import ttk, messagebox
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Optional Hardware/Audio Drivers with graceful fallback
try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except ImportError:
    HAS_SOUNDDEVICE = False


# =============================================================================
# คอนฟิกูเรชันหลัก (System Constants)
# =============================================================================
FS = 16000            # ความถี่สุ่มสัญญาณ 16 kHz
BLOCK_SIZE = 1024     # ขนาดบล็อก 1024 ตัวอย่าง (64 ms ต่อบล็อก)
FRAME_HEADER = b"\xAA\x55"  # Header Sync ไบนารี 2 ไบต์
PAYLOAD_BYTES = BLOCK_SIZE * 2  # 1024 samples * 2 bytes (16-bit PCM = 2048 bytes)

DEFAULT_F_LOW = 120.0       # High-Pass cutoff เริ่มต้น (Hz)
DEFAULT_F_HIGH = 5000.0     # Low-Pass cutoff เริ่มต้น (Hz)
DEFAULT_THRESHOLD = 600.0   # Noise Gate RMS Threshold เริ่มต้น
DEFAULT_GAIN_BOOST = 1.5    # Enhance Gain Boost เริ่มต้น


# =============================================================================
# คลาสจำลองสัญญาณทดสอบ (Synthetic Audio Signal Generator for Simulation)
# =============================================================================
class AudioSimulator:
    """
    สร้างสัญญาณจำลองสำหรับทดสอบระบบ DSP โดยไม่ต้องเชื่อมต่อฮาร์ดแวร์จริง:
    - เสียงพูดจำลอง: ฟอร์มันต์ 300 Hz, 1000 Hz, 2500 Hz (สลับช่วงพูดและช่วงเงียบ)
    - สัญญาณรบกวนความถี่ต่ำ: ไฟบ้าน 50 Hz Hum
    - สัญญาณรบกวนความถี่สูง: เสียงซ่า Hiss 6500 Hz + Noise พื้นหลัง
    """
    def __init__(self, fs: int = FS, block_size: int = BLOCK_SIZE):
        self.fs = fs
        self.block_size = block_size
        self.phase = 0
        self.time_elapsed = 0.0

    def generate_block(self) -> np.ndarray:
        t = (np.arange(self.block_size) + self.phase) / self.fs
        self.phase += self.block_size
        self.time_elapsed += self.block_size / self.fs

        # วงจรสลับเสียงพูด 2.5 วินาที สลับช่วงเงียบ 1.5 วินาที
        cycle_time = self.time_elapsed % 4.0
        is_talking = cycle_time < 2.5

        if is_talking:
            # ซิมูเลชันเสียงพูด (ผสมหลายโทนความถี่ + แอมพลิจูดโมดูเลชัน)
            speech = (
                0.55 * np.sin(2 * np.pi * 300 * t) +
                0.35 * np.sin(2 * np.pi * 1000 * t) +
                0.20 * np.sin(2 * np.pi * 2500 * t)
            )
            # เพิ่มการสั่นไหวของเสียงพูด (Modulation)
            speech *= (0.7 + 0.3 * np.sin(2 * np.pi * 3.0 * t))
            speech_amp = 14000.0
        else:
            speech = np.zeros(self.block_size)
            speech_amp = 0.0

        # สัญญาณรบกวนไฟบ้าน 50 Hz (Low-Frequency Hum)
        hum_50hz = 2500.0 * np.sin(2 * np.pi * 50 * t)

        # สัญญาณรบกวนความถี่สูง 6500 Hz (High-Frequency Tone)
        hiss_tone = 1800.0 * np.sin(2 * np.pi * 6500 * t)

        # สัญญาณรบกวนเกาส์เซียน (Background White Noise)
        white_noise = np.random.normal(0, 400.0, self.block_size)

        # ไฟตรง DC Offset แอนะล็อก (เช่น +1500 เพื่อทดสอบ Step 1 DC Removal)
        dc_offset = 1500.0

        # รวมทุกองค์ประกอบ
        raw_signal = (speech * speech_amp) + hum_50hz + hiss_tone + white_noise + dc_offset

        # จำลองเป็น 16-bit PCM Signed Integer
        raw_int16 = np.clip(raw_signal, -32767, 32767).astype(np.int16)
        return raw_int16


# =============================================================================
# คลาสหลัก: AudioEnhancerGUI
# =============================================================================
class AudioEnhancerGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("FPGA Audio Enhancer & Noise Suppression System (Task 3 Extension)")
        self.root.geometry("1280x880")
        self.root.minsize(1050, 750)
        self.root.configure(bg="#12161f")

        # พารามิเตอร์ DSP (Thread-safe shared variables)
        self.f_low = DEFAULT_F_LOW
        self.f_high = DEFAULT_F_HIGH
        self.threshold = DEFAULT_THRESHOLD
        self.gain_boost = DEFAULT_GAIN_BOOST
        self.bypass_mode = False          # False = Enhanced Audio, True = Raw Bypass
        self.is_recording = False
        self.source_mode = "Simulation"   # "Simulation" หรือ "Serial"
        self.is_muted = False

        # สถานะการประมวลผลตัวกรอง Stateful IIR Filter
        self.sos = self._design_bandpass_sos(self.f_low, self.f_high)
        self.filter_zi = scipy.signal.sosfilt_zi(self.sos) * 0.0

        # เธรดและคิวส่งข้อมูล (Thread & Queue)
        self.plot_queue: queue.Queue = queue.Queue(maxsize=10)
        self.is_running = True
        self.serial_port: Optional[serial.Serial] = None
        self.wav_file: Optional[wave.Wave_write] = None
        self.record_filename: str = ""

        # เครื่องมือจำลองสัญญาณ
        self.simulator = AudioSimulator(FS, BLOCK_SIZE)

        # สร้างโฟลเดอร์สำหรับเก็บไฟล์บันทึกเสียง
        self.record_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recordings")
        os.makedirs(self.record_dir, exist_ok=True)

        # สตรีมเสียงออกลำโพง (sounddevice)
        self.audio_stream: Optional[sd.OutputStream] = None
        self._init_audio_output()

        # สร้างส่วนติดต่อผู้ใช้ (GUI Layout)
        self._setup_style()
        self._build_gui()

        # เริ่มต้น Background Worker Thread
        self.worker_thread = threading.Thread(target=self._worker_read_and_dsp, daemon=True)
        self.worker_thread.start()

        # เริ่มต้น Loop อัปเดต GUI (35 ms refresh rate ~ 28 FPS)
        self.root.after(35, self._update_gui_loop)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # -------------------------------------------------------------------------
    # การตั้งค่าสไตล์ UI
    # -------------------------------------------------------------------------
    def _setup_style(self):
        style = ttk.Style()
        style.theme_use("clam")

        # กำหนด Palette สไตล์มืดแนววิศวกรรม (Cyber / Studio Dark)
        style.configure(".", background="#12161f", foreground="#ecf0f1", font=("Segoe UI", 10))
        style.configure("TFrame", background="#12161f")
        style.configure("Card.TFrame", background="#1b212f", relief="flat")
        style.configure("TLabel", background="#12161f", foreground="#ecf0f1")
        style.configure("Card.TLabel", background="#1b212f", foreground="#ecf0f1")
        style.configure("Header.TLabel", background="#12161f", foreground="#00e5ff", font=("Segoe UI", 14, "bold"))
        style.configure("SubHeader.TLabel", background="#1b212f", foreground="#00e5ff", font=("Segoe UI", 11, "bold"))
        style.configure("Value.TLabel", background="#1b212f", foreground="#26c6da", font=("Consolas", 10, "bold"))

        style.configure("TButton", background="#2a354b", foreground="#ffffff", borderwidth=0, padding=6, font=("Segoe UI", 9, "bold"))
        style.map("TButton", background=[("active", "#394b69"), ("pressed", "#1c2638")])

        style.configure("Accent.TButton", background="#00838f", foreground="#ffffff")
        style.map("Accent.TButton", background=[("active", "#00acc1"), ("pressed", "#006064")])

        style.configure("Record.TButton", background="#c62828", foreground="#ffffff")
        style.map("Record.TButton", background=[("active", "#e53935"), ("pressed", "#8e0000")])

        style.configure("TCombobox", fieldbackground="#12161f", background="#2a354b", foreground="#ecf0f1")
        style.configure("Horizontal.TScale", background="#1b212f", troughcolor="#0e131b")

    # -------------------------------------------------------------------------
    # สร้าง Layout GUI
    # -------------------------------------------------------------------------
    def _build_gui(self):
        # แถบ Header ด้านบน
        header_frame = ttk.Frame(self.root, padding="12 10 12 6")
        header_frame.pack(fill=tk.X)

        title_lbl = ttk.Label(header_frame, text="⚡ FPGA Audio Enhancer & Noise Suppression System", style="Header.TLabel")
        title_lbl.pack(side=tk.LEFT)

        sub_lbl = ttk.Label(header_frame, text="Fs = 16.0 kHz | N = 1024 (64 ms) | Real-Time DSP Pipeline", font=("Segoe UI", 9), foreground="#78909c")
        sub_lbl.pack(side=tk.RIGHT, pady=4)

        # พื้นที่หลัก แบ่งเป็น 2 ส่วน (ซ้าย: กราฟ, ขวา: แผงควบคุม)
        main_paned = ttk.Frame(self.root, padding="10")
        main_paned.pack(fill=tk.BOTH, expand=True)

        # ซีกซ้าย: Visualization Panel (Matplotlib Figures)
        plot_frame = ttk.Frame(main_paned)
        plot_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        self._build_plots(plot_frame)

        # ซีกขวา: Controls & Status Panel
        control_frame = ttk.Frame(main_paned, width=370)
        control_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=False)
        control_frame.pack_propagate(False)

        self._build_controls(control_frame)

        # Status Bar ด้านล่างสุด
        self._build_statusbar()

    def _build_plots(self, parent):
        # สร้าง Matplotlib Figure ด้วยธีมมืด
        self.fig = Figure(figsize=(8, 6), dpi=100, facecolor="#161b26")
        self.fig.subplots_adjust(left=0.08, right=0.96, top=0.94, bottom=0.08, hspace=0.32)

        # แกนพล็อตโดเมนเวลา (Time-Domain Waveform)
        self.ax_time = self.fig.add_subplot(2, 1, 1, facecolor="#0e131b")
        self.ax_time.set_title("Time-Domain Waveform (Block N=1024, 64 ms)", color="#b0bec5", fontsize=10, loc="left", pad=6)
        self.ax_time.set_xlabel("Time (ms)", color="#78909c", fontsize=8)
        self.ax_time.set_ylabel("Amplitude (16-bit)", color="#78909c", fontsize=8)
        self.ax_time.set_xlim(0, (BLOCK_SIZE / FS) * 1000)
        self.ax_time.set_ylim(-35000, 35000)
        self.ax_time.grid(True, color="#212b3d", linestyle="--", linewidth=0.6)
        self.ax_time.tick_params(colors="#78909c", labelsize=8)

        # แกนเวลา (0 ถึง 64 ms)
        self.time_axis_ms = np.linspace(0, (BLOCK_SIZE / FS) * 1000, BLOCK_SIZE)

        # เส้นสัญญาณดิบ (Raw: สีเทาจาง) และ สัญญาณปรับปรุงแล้ว (Enhanced: สีฟ้าสด)
        self.line_time_raw, = self.ax_time.plot(self.time_axis_ms, np.zeros(BLOCK_SIZE), color="#607d8b", alpha=0.65, linewidth=1.1, label="Raw Signal")
        self.line_time_enh, = self.ax_time.plot(self.time_axis_ms, np.zeros(BLOCK_SIZE), color="#00e5ff", linewidth=1.4, label="Enhanced Signal")
        
        # เส้น Threshold ของ Noise Gate (±Threshold)
        self.line_th_pos = self.ax_time.axhline(self.threshold, color="#ff7043", linestyle=":", linewidth=1.1, label="Gate Threshold")
        self.line_th_neg = self.ax_time.axhline(-self.threshold, color="#ff7043", linestyle=":", linewidth=1.1)
        self.ax_time.legend(loc="upper right", facecolor="#161b26", edgecolor="#212b3d", labelcolor="#cfd8dc", fontsize=8)

        # แกนพล็อตโดเมนความถี่ (Frequency-Domain FFT Spectrum)
        self.ax_freq = self.fig.add_subplot(2, 1, 2, facecolor="#0e131b")
        self.ax_freq.set_title("Frequency-Domain FFT Spectrum (Hann Window, Δf = 15.625 Hz)", color="#b0bec5", fontsize=10, loc="left", pad=6)
        self.ax_freq.set_xlabel("Frequency (Hz)", color="#78909c", fontsize=8)
        self.ax_freq.set_ylabel("Magnitude (dB)", color="#78909c", fontsize=8)
        self.ax_freq.set_xlim(0, FS / 2)  # 0 ถึง 8000 Hz
        self.ax_freq.set_ylim(-30, 100)
        self.ax_freq.grid(True, color="#212b3d", linestyle="--", linewidth=0.6)
        self.ax_freq.tick_params(colors="#78909c", labelsize=8)

        self.freq_bins = np.fft.rfftfreq(BLOCK_SIZE, 1.0 / FS)
        self.hann_window = np.hanning(BLOCK_SIZE)

        self.line_freq_raw, = self.ax_freq.plot(self.freq_bins, np.zeros(len(self.freq_bins)), color="#607d8b", alpha=0.55, linewidth=1.0, label="Raw Spectrum")
        self.line_freq_enh, = self.ax_freq.plot(self.freq_bins, np.zeros(len(self.freq_bins)), color="#00e676", linewidth=1.3, label="Enhanced Spectrum")

        # เส้นความถี่ตัด High-Pass / Low-Pass
        self.line_f_low = self.ax_freq.axvline(self.f_low, color="#ffd54f", linestyle="--", linewidth=1.0, label=f"High-Pass ({int(self.f_low)} Hz)")
        self.line_f_high = self.ax_freq.axvline(self.f_high, color="#ffd54f", linestyle="--", linewidth=1.0, label=f"Low-Pass ({int(self.f_high)} Hz)")
        self.ax_freq.legend(loc="upper right", facecolor="#161b26", edgecolor="#212b3d", labelcolor="#cfd8dc", fontsize=8)

        # ผูกเข้า Canvas ของ Tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def _build_controls(self, parent):
        # กล่อง 1: แหล่งข้อมูลสัญญาณ (Data Source & Serial)
        card_src = ttk.Frame(parent, style="Card.TFrame", padding="10")
        card_src.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(card_src, text="1. แหล่งรับสัญญาณ (Data Acquisition)", style="SubHeader.TLabel").pack(anchor=tk.W, pady=(0, 6))

        src_btn_row = ttk.Frame(card_src, style="Card.TFrame")
        src_btn_row.pack(fill=tk.X, pady=2)

        self.btn_source = ttk.Button(src_btn_row, text="Source: DEMO SIMULATION", command=self._toggle_source_mode, style="Accent.TButton")
        self.btn_source.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        # แถวเลือกพอร์ต Serial
        port_row = ttk.Frame(card_src, style="Card.TFrame")
        port_row.pack(fill=tk.X, pady=(6, 2))

        ttk.Label(port_row, text="Port:", style="Card.TLabel").pack(side=tk.LEFT)
        self.cbo_port = ttk.Combobox(port_row, width=9, state="readonly")
        self.cbo_port.pack(side=tk.LEFT, padx=4)

        ttk.Label(port_row, text="Baud:", style="Card.TLabel").pack(side=tk.LEFT, padx=(4, 0))
        self.cbo_baud = ttk.Combobox(port_row, values=["115200", "460800", "921600", "2000000"], width=8, state="readonly")
        self.cbo_baud.set("921600")
        self.cbo_baud.pack(side=tk.LEFT, padx=4)

        self.btn_refresh_ports = ttk.Button(port_row, text="🔄", width=3, command=self._refresh_serial_ports)
        self.btn_refresh_ports.pack(side=tk.RIGHT)

        self.btn_connect_serial = ttk.Button(card_src, text="Connect Hardware Serial", command=self._toggle_serial_connection)
        self.btn_connect_serial.pack(fill=tk.X, pady=(6, 2))
        self._refresh_serial_ports()

        # กล่อง 2: แผงปรับตั้งค่าพารามิเตอร์ DSP (DSP Sliders)
        card_dsp = ttk.Frame(parent, style="Card.TFrame", padding="10")
        card_dsp.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(card_dsp, text="2. แผงควบคุม DSP Pipeline", style="SubHeader.TLabel").pack(anchor=tk.W, pady=(0, 8))

        # Slider 1: High-Pass Cutoff (80 - 500 Hz)
        self.lbl_flow_val = ttk.Label(card_dsp, text=f"High-Pass Cutoff (f_low): {int(self.f_low)} Hz", style="Card.TLabel")
        self.lbl_flow_val.pack(anchor=tk.W)
        self.scale_flow = ttk.Scale(card_dsp, from_=80, to=500, value=self.f_low, command=self._on_flow_change)
        self.scale_flow.pack(fill=tk.X, pady=(2, 8))

        # Slider 2: Low-Pass Cutoff (1000 - 7500 Hz)
        self.lbl_fhigh_val = ttk.Label(card_dsp, text=f"Low-Pass Cutoff (f_high): {int(self.f_high)} Hz", style="Card.TLabel")
        self.lbl_fhigh_val.pack(anchor=tk.W)
        self.scale_fhigh = ttk.Scale(card_dsp, from_=1000, to=7500, value=self.f_high, command=self._on_fhigh_change)
        self.scale_fhigh.pack(fill=tk.X, pady=(2, 8))

        # Slider 3: Noise Gate Threshold (0 - 5000)
        self.lbl_th_val = ttk.Label(card_dsp, text=f"Noise Gate Threshold: {int(self.threshold)}", style="Card.TLabel")
        self.lbl_th_val.pack(anchor=tk.W)
        self.scale_th = ttk.Scale(card_dsp, from_=0, to=5000, value=self.threshold, command=self._on_threshold_change)
        self.scale_th.pack(fill=tk.X, pady=(2, 8))

        # Slider 4: Gain Boost (1.0x - 5.0x)
        self.lbl_gain_val = ttk.Label(card_dsp, text=f"Enhance Gain Boost: {self.gain_boost:.1f}x", style="Card.TLabel")
        self.lbl_gain_val.pack(anchor=tk.W)
        self.scale_gain = ttk.Scale(card_dsp, from_=1.0, to=5.0, value=self.gain_boost, command=self._on_gain_change)
        self.scale_gain.pack(fill=tk.X, pady=(2, 4))

        # กล่อง 3: การฟังเสียงสดและการบันทึกไฟล์ (Audio & Record Controls)
        card_audio = ttk.Frame(parent, style="Card.TFrame", padding="10")
        card_audio.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(card_audio, text="3. ระบบมอนิเตอร์เสียง & บันทึก", style="SubHeader.TLabel").pack(anchor=tk.W, pady=(0, 6))

        # ปุ่ม A/B Bypass Switch
        self.btn_bypass = ttk.Button(card_audio, text="Filter: ENHANCED (Hear Filtered)", command=self._toggle_bypass_mode, style="Accent.TButton")
        self.btn_bypass.pack(fill=tk.X, pady=3)

        # ปุ่ม Mute/Unmute
        self.btn_mute = ttk.Button(card_audio, text="Speaker Output: UNMUTED", command=self._toggle_mute)
        self.btn_mute.pack(fill=tk.X, pady=3)

        # ปุ่ม Start/Stop WAV Recording
        self.btn_record = ttk.Button(card_audio, text="⏺ Start Recording (.wav)", command=self._toggle_recording, style="Record.TButton")
        self.btn_record.pack(fill=tk.X, pady=3)

        # กล่อง 4: มาตรวัดสถานะแบบสด (Live Telemetry Indicators)
        card_telemetry = ttk.Frame(parent, style="Card.TFrame", padding="10")
        card_telemetry.pack(fill=tk.BOTH, expand=True)

        ttk.Label(card_telemetry, text="4. มาตรวัดสถานะแบบเวลาจริง (Telemetry)", style="SubHeader.TLabel").pack(anchor=tk.W, pady=(0, 6))

        grid_telem = ttk.Frame(card_telemetry, style="Card.TFrame")
        grid_telem.pack(fill=tk.X)

        ttk.Label(grid_telem, text="Current RMS:", style="Card.TLabel").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.lbl_telem_rms = ttk.Label(grid_telem, text="0.0", style="Value.TLabel")
        self.lbl_telem_rms.grid(row=0, column=1, sticky=tk.E, padx=10, pady=2)

        ttk.Label(grid_telem, text="Noise Gate Status:", style="Card.TLabel").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.lbl_telem_gate = ttk.Label(grid_telem, text="OPEN (100%)", style="Value.TLabel", foreground="#00e676")
        self.lbl_telem_gate.grid(row=1, column=1, sticky=tk.E, padx=10, pady=2)

        ttk.Label(grid_telem, text="Clipping Status:", style="Card.TLabel").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.lbl_telem_clip = ttk.Label(grid_telem, text="NORMAL", style="Value.TLabel", foreground="#00e676")
        self.lbl_telem_clip.grid(row=2, column=1, sticky=tk.E, padx=10, pady=2)

    def _build_statusbar(self):
        self.status_bar = ttk.Frame(self.root, padding="6 4 10 4")
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        self.lbl_status_msg = ttk.Label(self.status_bar, text="Ready. Running in Demo Simulation Mode.", foreground="#90a4ae", font=("Segoe UI", 9))
        self.lbl_status_msg.pack(side=tk.LEFT)

        self.lbl_fps_msg = ttk.Label(self.status_bar, text="GUI: ~28 FPS | Latency: ~64 ms/block", foreground="#78909c", font=("Consolas", 9))
        self.lbl_fps_msg.pack(side=tk.RIGHT)

    # -------------------------------------------------------------------------
    # ตัวกรอง IIR Butterworth Bandpass (Second-Order Sections: SOS)
    # -------------------------------------------------------------------------
    def _design_bandpass_sos(self, lowcut: float, highcut: float) -> np.ndarray:
        """
        ออกแบบสัมประสิทธิ์ตัวกรอง 4th-Order Butterworth Bandpass ในรูปแบบ SOS:
        - ป้องกันปัญหา Numerical Instability
        - ตรวจสอบความถูกต้องของช่วงความถี่ตัด
        """
        nyquist = 0.5 * FS
        low = max(20.0, float(lowcut)) / nyquist
        high = min(nyquist - 20.0, float(highcut)) / nyquist

        if low >= high:
            low = high - 0.05

        sos = scipy.signal.butter(N=4, Wn=[low, high], btype="bandpass", output="sos")
        return sos

    # -------------------------------------------------------------------------
    # สายพานการประมวลผล DSP Pipeline ทั้ง 4 ขั้นตอน
    # -------------------------------------------------------------------------
    def _process_dsp_block(self, raw_int16: np.ndarray) -> Tuple[np.ndarray, np.ndarray, float, float, bool]:
        """
        รันสายพาน DSP ครบ 4 ขั้นตอน ตามสเปกในเอกสาร Blueprint:
        Input: raw_int16 (1024 samples)
        Returns:
            - x_zero: สัญญาณหลังลบ DC Offset (int16)
            - y_enhanced: สัญญาณผลลัพธ์สุดท้ายหลังผ่าน 4 ขั้นตอน (int16)
            - rms: ค่าพลังงาน RMS ของบล็อก
            - attenuation: ค่าลดทอนของ Noise Gate (0.0 ถึง 1.0)
            - is_clipping: แจ้งเตือนแอมพลิจูดชนขอบ ±32767 หรือไม่
        """
        # ขั้นที่ 1: แปลงเป็นทศนิยม float64 และลบไฟตรง DC Offset
        x_float = raw_int16.astype(np.float64)
        x_zero = x_float - np.mean(x_float)

        # ขั้นที่ 2: 4th-Order IIR Butterworth Bandpass (Stateful SOS Filtering)
        y_filt, self.filter_zi = scipy.signal.sosfilt(self.sos, x_zero, zi=self.filter_zi)

        # ขั้นที่ 3: Dynamic RMS Noise Gate (Soft-Knee Quadratic Attenuation)
        rms = float(np.sqrt(np.mean(y_filt ** 2)))
        th = float(self.threshold)

        if th <= 0.0 or rms >= th:
            attenuation = 1.0
        else:
            # สมการลดทอนแบบ Soft-Knee กำลังสอง
            attenuation = (rms / th) ** 2

        y_gated = y_filt * attenuation

        # ขั้นที่ 4: Enhance Gain Boost & Soft Limiter
        boost = float(self.gain_boost)
        y_boosted = y_gated * boost

        # ตรวจสอบการเกิด Clipping
        is_clipping = bool(np.any(np.abs(y_boosted) >= 32767.0))

        # จำกัดเพดาน (Soft/Hard Limiter) เข้าช่วง 16-bit PCM
        y_enhanced = np.clip(y_boosted, -32767.0, 32767.0).astype(np.int16)
        x_zero_int16 = np.clip(x_zero, -32767.0, 32767.0).astype(np.int16)

        return x_zero_int16, y_enhanced, rms, attenuation, is_clipping

    # -------------------------------------------------------------------------
    # Background Worker Thread: อ่านข้อมูล -> ประมวลผล DSP -> ส่งออกลำโพง/ไฟล์
    # -------------------------------------------------------------------------
    def _worker_read_and_dsp(self):
        """เธรดเบื้องหลัง ทำงานต่อเนื่องทุกๆ 64 ms ต่อบล็อก"""
        while self.is_running:
            raw_block = None

            # 1. อ่านข้อมูลจาก Serial Hardware หรือ Simulation
            if self.source_mode == "Serial" and self.serial_port and self.serial_port.is_open:
                try:
                    raw_block = self._sync_and_read_serial(self.serial_port)
                except Exception as e:
                    print(f"[Serial Read Error]: {e}")
                    time.sleep(0.05)
            else:
                # โหมดจำลอง Demo Simulation
                raw_block = self.simulator.generate_block()
                time.sleep(BLOCK_SIZE / FS)  # หน่วงเวลา 64 ms ให้ตรงกับเวลาจริง

            if raw_block is None or len(raw_block) != BLOCK_SIZE:
                continue

            # 2. ประมวลผลผ่านสายพาน DSP
            x_zero, y_enhanced, rms, attenuation, is_clipping = self._process_dsp_block(raw_block)

            # 3. เลือกสัญญาณที่จะส่งออกลำโพง (A/B Bypass Switch)
            audio_out = x_zero if self.bypass_mode else y_enhanced

            # 4. ส่งข้อมูลเสียงออกลำโพงแบบเวลาจริง (sounddevice)
            if HAS_SOUNDDEVICE and self.audio_stream and self.audio_stream.active and not self.is_muted:
                try:
                    self.audio_stream.write(audio_out.reshape(-1, 1))
                except Exception as e:
                    # ป้องกัน buffer underflow กระตุก
                    pass

            # 5. บันทึกข้อมูลลงไฟล์ .wav (เมื่อเปิดโหมดบันทึก)
            if self.is_recording and self.wav_file:
                try:
                    self.wav_file.writeframes(y_enhanced.tobytes())
                except Exception as e:
                    print(f"[WAV Write Error]: {e}")

            # 6. ส่งข้อมูลเข้าคิวเพื่อให้ Main GUI Thread นำไปวาดกราฟ
            if not self.plot_queue.full():
                try:
                    self.plot_queue.put_nowait((x_zero, y_enhanced, rms, attenuation, is_clipping))
                except queue.Full:
                    pass

    # -------------------------------------------------------------------------
    # ตรวจจับ Header Sync และอ่านไบนารีจาก Serial (ESP32)
    # -------------------------------------------------------------------------
    def _sync_and_read_serial(self, ser: serial.Serial) -> Optional[np.ndarray]:
        """
        ตรวจจับ Header Sync 2 ไบต์ (0xAA 0x55)
        แล้วอ่าน Payload ขนาด 2,048 ไบต์ (1024 ตัวอย่าง 16-bit PCM little-endian)
        """
        # ค้นหา Header Sync
        while self.is_running and ser.is_open:
            b1 = ser.read(1)
            if b1 == b"\xAA":
                b2 = ser.read(1)
                if b2 == b"\x55":
                    # พบ Header Sync แล้ว! อ่าน Payload ครบ 2048 ไบต์
                    payload = ser.read(PAYLOAD_BYTES)
                    if len(payload) == PAYLOAD_BYTES:
                        return np.frombuffer(payload, dtype="<i2")
        return None

    # -------------------------------------------------------------------------
    # Main GUI Loop: อัปเดตหน้าจอและกราฟวิเคราะห์สัญญาณ
    # -------------------------------------------------------------------------
    def _update_gui_loop(self):
        """เรียกซ้ำอัตโนมัติด้วย root.after() เพื่อดึงข้อมูลล่าสุดจาก Queue มาวาดกราฟ"""
        if not self.is_running:
            return

        latest_data = None
        # ดึงเฟรมข้อมูลล่าสุด (ทิ้งเฟรมเก่าหากคิวดอง เพื่อรักษาความลื่นไหลแบบ Real-Time)
        while not self.plot_queue.empty():
            try:
                latest_data = self.plot_queue.get_nowait()
            except queue.Empty:
                break

        if latest_data is not None:
            x_zero, y_enh, rms, atten, is_clip = latest_data

            # 1. อัปเดตพล็อตโดเมนเวลา
            self.line_time_raw.set_ydata(x_zero)
            self.line_time_enh.set_ydata(y_enh)

            # 2. คำนวณและอัปเดตพล็อต FFT สเปกตรัม (Hann Window)
            raw_win = x_zero * self.hann_window
            enh_win = y_enh * self.hann_window

            raw_fft = np.abs(np.fft.rfft(raw_win))
            enh_fft = np.abs(np.fft.rfft(enh_win))

            # สเกลเป็นเดซิเบล (dB) พร้อมป้องกัน log(0)
            raw_db = 20 * np.log10(np.maximum(raw_fft, 1e-4))
            enh_db = 20 * np.log10(np.maximum(enh_fft, 1e-4))

            self.line_freq_raw.set_ydata(raw_db)
            self.line_freq_enh.set_ydata(enh_db)

            # วาดใหม่
            self.canvas.draw_idle()

            # 3. อัปเดตข้อมูล Telemetry
            self.lbl_telem_rms.config(text=f"{rms:.1f}")

            if atten >= 0.99:
                self.lbl_telem_gate.config(text="OPEN (100%)", foreground="#00e676")
            else:
                pct = int(atten * 100)
                self.lbl_telem_gate.config(text=f"ATTEN ({pct}%)", foreground="#ffb74d")

            if is_clip:
                self.lbl_telem_clip.config(text="⚠️ CLIPPING!", foreground="#ff1744")
            else:
                self.lbl_telem_clip.config(text="NORMAL", foreground="#00e676")

        # วนรอบถัดไป (~28 FPS)
        self.root.after(35, self._update_gui_loop)

    # -------------------------------------------------------------------------
    # Callbacks สำหรับแถบเลื่อนสไลเดอร์ (Sliders)
    # -------------------------------------------------------------------------
    def _on_flow_change(self, val):
        self.f_low = float(val)
        self.lbl_flow_val.config(text=f"High-Pass Cutoff (f_low): {int(self.f_low)} Hz")
        self.line_f_low.set_xdata([self.f_low, self.f_low])
        self.sos = self._design_bandpass_sos(self.f_low, self.f_high)

    def _on_fhigh_change(self, val):
        self.f_high = float(val)
        self.lbl_fhigh_val.config(text=f"Low-Pass Cutoff (f_high): {int(self.f_high)} Hz")
        self.line_f_high.set_xdata([self.f_high, self.f_high])
        self.sos = self._design_bandpass_sos(self.f_low, self.f_high)

    def _on_threshold_change(self, val):
        self.threshold = float(val)
        self.lbl_th_val.config(text=f"Noise Gate Threshold: {int(self.threshold)}")
        self.line_th_pos.set_ydata([self.threshold, self.threshold])
        self.line_th_neg.set_ydata([-self.threshold, -self.threshold])

    def _on_gain_change(self, val):
        self.gain_boost = float(val)
        self.lbl_gain_val.config(text=f"Enhance Gain Boost: {self.gain_boost:.1f}x")

    # -------------------------------------------------------------------------
    # Callbacks สำหรับปุ่มควบคุม (Buttons)
    # -------------------------------------------------------------------------
    def _toggle_bypass_mode(self):
        self.bypass_mode = not self.bypass_mode
        if self.bypass_mode:
            self.btn_bypass.config(text="Filter: BYPASS (Hear Raw)", style="Record.TButton")
            self.lbl_status_msg.config(text="Bypass Mode ON: Listening to Raw Unfiltered Audio.")
        else:
            self.btn_bypass.config(text="Filter: ENHANCED (Hear Filtered)", style="Accent.TButton")
            self.lbl_status_msg.config(text="Filter Active: Listening to Enhanced DSP Audio.")

    def _toggle_mute(self):
        self.is_muted = not self.is_muted
        if self.is_muted:
            self.btn_mute.config(text="Speaker Output: MUTED")
        else:
            self.btn_mute.config(text="Speaker Output: UNMUTED")

    def _toggle_source_mode(self):
        if self.source_mode == "Simulation":
            self.source_mode = "Serial"
            self.btn_source.config(text="Source: HARDWARE SERIAL", style="TButton")
            self.lbl_status_msg.config(text="Switched to Hardware Serial Mode. Please connect COM Port.")
        else:
            self.source_mode = "Simulation"
            self.btn_source.config(text="Source: DEMO SIMULATION", style="Accent.TButton")
            self.lbl_status_msg.config(text="Switched to Synthetic Demo Simulation Mode.")

    def _refresh_serial_ports(self):
        if not HAS_SERIAL:
            self.cbo_port.config(values=["No PySerial"])
            return
        ports = [port.device for port in serial.tools.list_ports.comports()]
        if ports:
            self.cbo_port.config(values=ports)
            self.cbo_port.set(ports[0])
        else:
            self.cbo_port.config(values=["No COM"])
            self.cbo_port.set("No COM")

    def _toggle_serial_connection(self):
        if not HAS_SERIAL:
            messagebox.showwarning("Missing Library", "PySerial is not installed. Please run:\npip install pyserial")
            return

        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
            self.serial_port = None
            self.btn_connect_serial.config(text="Connect Hardware Serial")
            self.lbl_status_msg.config(text="Serial disconnected.")
        else:
            port_name = self.cbo_port.get()
            baud_val = int(self.cbo_baud.get())
            if not port_name or "No" in port_name:
                messagebox.showerror("Error", "No valid COM port selected!")
                return
            try:
                self.serial_port = serial.Serial(port_name, baudrate=baud_val, timeout=0.2)
                self.btn_connect_serial.config(text=f"Disconnect ({port_name})")
                self.source_mode = "Serial"
                self.btn_source.config(text="Source: HARDWARE SERIAL", style="TButton")
                self.lbl_status_msg.config(text=f"Connected to {port_name} at {baud_val} bps.")
            except Exception as e:
                messagebox.showerror("Connection Failed", f"Cannot open {port_name}:\n{e}")

    def _toggle_recording(self):
        if not self.is_recording:
            # เริ่มการบันทึกไฟล์ .wav
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.record_filename = os.path.join(self.record_dir, f"enhanced_record_{timestamp}.wav")
            try:
                self.wav_file = wave.open(self.record_filename, "wb")
                self.wav_file.setnchannels(1)        # Mono
                self.wav_file.setsampwidth(2)        # 16-bit (2 bytes)
                self.wav_file.setframerate(FS)       # 16000 Hz
                self.is_recording = True
                self.btn_record.config(text="⏹ Stop Recording", style="Record.TButton")
                self.lbl_status_msg.config(text=f"Recording to {os.path.basename(self.record_filename)}...")
            except Exception as e:
                messagebox.showerror("Recording Error", f"Cannot create WAV file:\n{e}")
        else:
            # หยุดบันทึกและปิดไฟล์
            self.is_recording = False
            if self.wav_file:
                self.wav_file.close()
                self.wav_file = None
            self.btn_record.config(text="⏺ Start Recording (.wav)", style="TButton")
            self.lbl_status_msg.config(text=f"Saved recording: {os.path.basename(self.record_filename)}")

    def _init_audio_output(self):
        """กำหนดค่าและเริ่มสตรีมเสียงออกลำโพงแบบเวลาจริง (sounddevice)"""
        if not HAS_SOUNDDEVICE:
            print("[Warning] sounddevice library not found. Live audio output disabled.")
            return
        try:
            self.audio_stream = sd.OutputStream(
                samplerate=FS,
                blocksize=BLOCK_SIZE,
                channels=1,
                dtype="int16"
            )
            self.audio_stream.start()
        except Exception as e:
            print(f"[Warning] Audio device initialization notice: {e}")
            self.audio_stream = None

    def on_close(self):
        """ปิดโปรแกรมอย่างปลอดภัย: ปิดเธรด, Serial, ไฟล์ WAV และ Audio Stream"""
        self.is_running = False
        time.sleep(0.1)

        if self.wav_file:
            try:
                self.wav_file.close()
            except Exception:
                pass

        if self.serial_port and self.serial_port.is_open:
            try:
                self.serial_port.close()
            except Exception:
                pass

        if self.audio_stream:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            except Exception:
                pass

        self.root.destroy()


# =============================================================================
# จุดเริ่มต้นโปรแกรม (Main Entry Point)
# =============================================================================
if __name__ == "__main__":
    root = tk.Tk()
    app = AudioEnhancerGUI(root)
    root.mainloop()
