import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import time
import sys
import ctypes
import math
import os
import json
import tempfile
# Third-party imports
import keyboard
import mss
import numpy as np
import win32api
import win32con
from pynput import mouse as pynput_mouse
from pynput import keyboard as pynput_keyboard
# New imports
import winsound # для звуков (Windows)
import requests # для Telegram API (проверьте, что установлен)
# ==========================================
# Constants
# ==========================================
# Color Detection (RGB)
COLOR_BAR_CONTAINER = (85, 170, 255)
COLOR_SAFE_ZONE_BACKGROUND = (25, 25, 25)
COLOR_MOVING_INDICATOR = (255, 255, 255)
COLOR_TOLERANCE = 25
CFG_FILE = "cfg.json"
LOGS_DIR = "logs"
class ModernGPOBot:
    def __init__(self, root):
        self.root = root
        self.root.title('telergam - @saved_messenges')
        self.root.attributes('-topmost', True)
        self.root.protocol('WM_DELETE_WINDOW', self.exit_app)
        self.colors = {
            'bg': '#1e1e1e', 'panel': '#252526', 'fg': '#cccccc',
            'accent': '#007acc', 'accent_hover': '#0098ff',
            'danger': '#f44336', 'success': '#4caf50', 'warning': '#ff9800'
        }
        self.root.configure(bg=self.colors['bg'])
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except:
            pass
        # State
        self.main_loop_active = False
        self.overlay_active = False
        self.overlay_window = None
        self.recording_hotkey = None
        self.is_clicking = False
        self.purchase_counter = 0
        # New stats
        self.total_purchases = 0
        self.total_cycles = 0
        self.start_time = None
        self.dpi_scale = self.get_dpi_scale()
        # Overlay Geometry
        base_width = 250
        base_height = 500
        self.overlay_area = {
            'x': int(100 * self.dpi_scale),
            'y': int(100 * self.dpi_scale),
            'width': int(base_width * self.dpi_scale),
            'height': int(base_height * self.dpi_scale)
        }
        self.previous_error = 0
        self.point_coords = {1: None, 2: None, 3: None, 4: None}
        self.hotkeys = {'toggle_loop': 'f1', 'toggle_overlay': 'f2', 'exit': 'f3'}
        # UI reference holders
        self.point_buttons = {}
        self.hotkey_labels = {}
        # sound files names (without extension) - user will place 1.wav and 2.wav in working dir
        self.start_sound_name = "1"
        self.stop_sound_name = "2"
        # Cooldown for toggle hotkey
        self.last_toggle_time = 0.0
        self.toggle_cooldown = 7.0 # seconds
        # Cooldown for /restart
        self.last_restart_time = 0.0
        self.restart_cooldown = 7.0 # seconds
        # Telegram / TgHook state
        self.telegram_token = ""
        self.telegram_chat_id = None # integer
        self.telegram_running = False
        self.telegram_offset = 0
        self.telegram_thread = None
        self.setup_styles()
        self.setup_ui()
        # Load config (if exists) and apply
        self.load_config()
        # Hotkeys should be registered after load (so they reflect cfg)
        self.register_hotkeys()
        self.root.update_idletasks()
        self.root.minsize(440, 720)
        # Ensure logs directory exists
        try:
            os.makedirs(LOGS_DIR, exist_ok=True)
        except:
            pass
    def get_dpi_scale(self):
        try:
            return self.root.winfo_fpixels('1i') / 96.0
        except:
            return 1.0
    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TFrame', background=self.colors['bg'])
        style.configure('Card.TFrame', background=self.colors['panel'], relief='flat')
        style.configure('TLabel', background=self.colors['bg'], foreground=self.colors['fg'], font=('Segoe UI', 10))
        style.configure('Card.TLabel', background=self.colors['panel'], foreground=self.colors['fg'], font=('Segoe UI', 10))
        style.configure('Header.TLabel', font=('Segoe UI', 18, 'bold'), foreground=self.colors['accent'])
        style.configure('SubHeader.TLabel', background=self.colors['panel'], font=('Segoe UI', 11, 'bold'), foreground=self.colors['fg'])
        style.configure('TButton', background=self.colors['panel'], foreground=self.colors['fg'], borderwidth=0, font=('Segoe UI', 9))
        style.map('TButton', background=[('active', self.colors['accent'])], foreground=[('active', 'white')])
        style.configure('Accent.TButton', background=self.colors['accent'], foreground='white', font=('Segoe UI', 9, 'bold'))
        style.map('Accent.TButton', background=[('active', self.colors['accent_hover'])])
    def setup_ui(self):
        main_container = ttk.Frame(self.root, padding=12)
        main_container.pack(fill=tk.BOTH, expand=True)
        header_frame = ttk.Frame(main_container)
        header_frame.pack(fill='x', pady=(0, 12))
        ttk.Label(header_frame, text='PIDORI GPO FISH MACRO', style='Header.TLabel').pack(side='left')
        self.status_indicator = tk.Label(header_frame, text="STOPPED", bg=self.colors['danger'], fg='white', font=('Segoe UI', 8, 'bold'), padx=8, pady=2)
        self.status_indicator.pack(side='right')
        top_info = ttk.Frame(main_container)
        top_info.pack(fill='x', pady=(0,8))
        # Overlay label + lock
        self.overlay_label = ttk.Label(top_info, text='Overlay: HIDDEN', foreground='#666666')
        self.overlay_label.pack(side='right', padx=(8,0))
        # TgHook button (вверху)
        ttk.Button(top_info, text="TgHook", width=8, command=self.open_tghook_window).pack(side='left', padx=(0,8))
        # Stats card (purchases, cycles, uptime)
        stats_card = ttk.Frame(main_container, style='Card.TFrame', padding=8)
        stats_card.pack(fill='x', pady=(0,8))
        ttk.Label(stats_card, text='Stats', style='SubHeader.TLabel').grid(row=0, column=0, sticky='w')
        self.purchases_label = ttk.Label(stats_card, text='Purchases: 0', style='Card.TLabel')
        self.purchases_label.grid(row=1, column=0, sticky='w', padx=4, pady=2)
        self.cycles_label = ttk.Label(stats_card, text='Cycles: 0', style='Card.TLabel')
        self.cycles_label.grid(row=1, column=1, sticky='w', padx=4, pady=2)
        self.uptime_label = ttk.Label(stats_card, text='Uptime: 00:00:00', style='Card.TLabel')
        self.uptime_label.grid(row=1, column=2, sticky='w', padx=4, pady=2)
        # Split area: left controls, right logs
        split = ttk.Frame(main_container)
        split.pack(fill='both', expand=True)
        left_col = ttk.Frame(split)
        left_col.pack(side='left', fill='both', expand=True)
        right_col = ttk.Frame(split)
        right_col.pack(side='right', fill='both', expand=True, padx=(8,0))
        self.create_card(left_col, "Auto Purchase", self.setup_auto_buy_content)
        self.create_card(left_col, "Mechanics & Timing", self.setup_mechanics_content)
        self.create_card(left_col, "Hotkeys", self.setup_hotkeys_content)
        # Logs panel (right)
        log_card = ttk.Frame(right_col, style='Card.TFrame', padding=8)
        log_card.pack(fill='both', expand=True)
        header_f = ttk.Frame(log_card)
        header_f.pack(fill='x')
        ttk.Label(header_f, text='Logs', style='SubHeader.TLabel').pack(side='left', anchor='w')
        ttk.Button(header_f, text="Clear", width=8, command=self.clear_logs).pack(side='right')
        ttk.Button(header_f, text="Save cfg", width=8, command=self.save_config).pack(side='right', padx=(4,0))
        # NEW: Save Logs button (manual save)
        ttk.Button(header_f, text="Save Logs", width=10, command=self.save_logs_button).pack(side='right', padx=(4,0))
        self.log_box = scrolledtext.ScrolledText(log_card, height=20, bg='#111111', fg='#e6e6e6', state='disabled', wrap='word', font=('Consolas', 9))
        self.log_box.pack(fill='both', expand=True, pady=(6,0))
    def create_card(self, parent, title, content_func):
        card = ttk.Frame(parent, style='Card.TFrame', padding=10)
        card.pack(fill='x', pady=5)
        ttk.Label(card, text=title, style='SubHeader.TLabel').pack(anchor='w', pady=(0, 10))
        content_func(card)
    def setup_auto_buy_content(self, parent):
        self.auto_purchase_var = tk.BooleanVar(value=True)
        cb = tk.Checkbutton(parent, text="Enable Auto Buy", variable=self.auto_purchase_var,
                            bg=self.colors['panel'], fg=self.colors['fg'],
                            selectcolor=self.colors['bg'], activebackground=self.colors['panel'], activeforeground='white')
        cb.pack(anchor='w', pady=(0, 5))
        grid = ttk.Frame(parent, style='Card.TFrame')
        grid.pack(fill='x')
        ttk.Label(grid, text="Amount:", style='Card.TLabel').grid(row=0, column=0, sticky='w', padx=5, pady=2)
        self.amount_var = tk.IntVar(value=10)
        tk.Spinbox(grid, from_=0, to=9999, textvariable=self.amount_var, width=8, bg=self.colors['bg'], fg='white', relief='flat').grid(row=0, column=1, pady=2)
        ttk.Label(grid, text="Loops/Buy:", style='Card.TLabel').grid(row=0, column=2, sticky='w', padx=15, pady=2)
        self.loops_var = tk.IntVar(value=15)
        tk.Spinbox(grid, from_=1, to=9999, textvariable=self.loops_var, width=8, bg=self.colors['bg'], fg='white', relief='flat').grid(row=0, column=3, pady=2)
        ttk.Label(grid, text="Interact Delay (s):", style='Card.TLabel').grid(row=1, column=0, sticky='w', padx=5, pady=2)
        self.interact_delay_var = tk.DoubleVar(value=2.0)
        tk.Spinbox(grid, from_=0.1, to=10.0, increment=0.1, textvariable=self.interact_delay_var, width=8, bg=self.colors['bg'], fg='white', relief='flat').grid(row=1, column=1, pady=2)
        btn_grid = ttk.Frame(parent, style='Card.TFrame')
        btn_grid.pack(fill='x', pady=5)
        for i in range(1, 5):
            r, c = divmod(i-1, 2)
            btn = ttk.Button(btn_grid, text=f"Set Pt {i}", command=lambda x=i: self.capture_mouse_click(x))
            btn.grid(row=r, column=c, sticky='ew', padx=2, pady=2)
            btn_grid.columnconfigure(c, weight=1)
            self.point_buttons[i] = btn
    def setup_mechanics_content(self, parent):
        grid = ttk.Frame(parent, style='Card.TFrame')
        grid.pack(fill='x')
        ttk.Label(grid, text="Kp (Strength):", style='Card.TLabel').grid(row=0, column=0, sticky='w', padx=5)
        self.kp_var = tk.DoubleVar(value=0.1)
        tk.Scale(grid, from_=0.0, to=2.0, resolution=0.01, variable=self.kp_var, orient='horizontal', bg=self.colors['panel'], fg='white', highlightthickness=0, length=120).grid(row=0, column=1)
        ttk.Label(grid, text="Kd (Stability):", style='Card.TLabel').grid(row=1, column=0, sticky='w', padx=5)
        self.kd_var = tk.DoubleVar(value=0.5)
        tk.Scale(grid, from_=0.0, to=2.0, resolution=0.01, variable=self.kd_var, orient='horizontal', bg=self.colors['panel'], fg='white', highlightthickness=0, length=120).grid(row=1, column=1)
        ttk.Label(grid, text="Rod Reset (s):", style='Card.TLabel').grid(row=0, column=2, sticky='w', padx=15)
        self.rod_reset_var = tk.DoubleVar(value=3.0)
        tk.Spinbox(grid, from_=0.0, to=10.0, increment=0.1, textvariable=self.rod_reset_var, width=6, bg=self.colors['bg'], fg='white', relief='flat').grid(row=0, column=3)
        ttk.Label(grid, text="Timeout (s):", style='Card.TLabel').grid(row=1, column=2, sticky='w', padx=15)
        self.timeout_var = tk.DoubleVar(value=15.0)
        tk.Spinbox(grid, from_=1.0, to=120.0, increment=1.0, textvariable=self.timeout_var, width=6, bg=self.colors['bg'], fg='white', relief='flat').grid(row=1, column=3)
    def setup_hotkeys_content(self, parent):
        for i, (key_id, label_text) in enumerate([('toggle_loop', 'Start/Stop'), ('toggle_overlay', 'Overlay'), ('exit', 'Exit App')]):
            f = ttk.Frame(parent, style='Card.TFrame')
            f.pack(fill='x', pady=1)
            ttk.Label(f, text=label_text, style='Card.TLabel', width=15).pack(side='left')
            lbl = tk.Label(f, text=self.hotkeys[key_id].upper(), bg=self.colors['bg'], fg='white', width=10, relief='flat')
            lbl.pack(side='left', padx=10)
            ttk.Button(f, text="Bind", width=6, command=lambda k=key_id, l=lbl: self.start_rebind(k, l)).pack(side='right')
            self.hotkey_labels[key_id] = lbl
    # ================= Logging helper =================
    def log(self, *parts):
        """Thread-safe append to GUI logs only (no console prints)."""
        try:
            text = " ".join(str(p) for p in parts)
            timestamped = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {text}\n"
            def append():
                try:
                    self.log_box.configure(state='normal')
                    self.log_box.insert(tk.END, timestamped)
                    self.log_box.yview_moveto(1.0)
                    self.log_box.configure(state='disabled')
                except Exception:
                    pass
            self.root.after(0, append)
        except Exception:
            pass
    def clear_logs(self):
        try:
            self.log_box.configure(state='normal')
            self.log_box.delete('1.0', tk.END)
            self.log_box.configure(state='disabled')
        except Exception:
            pass
    def save_logs_to_file(self):
        try:
            txt = self.log_box.get('1.0', tk.END).strip()
            if not txt:
                return None
            ts = time.strftime('%Y%m%d_%H%M%S')
            fname = os.path.join(LOGS_DIR, f"logs_{ts}.txt")
            with open(fname, 'w', encoding='utf-8') as f:
                f.write(txt)
            return fname
        except Exception as e:
            # if saving logs fails - still ignore but note it in GUI
            self.log("Failed to save logs:", e)
            return None
    def save_logs_button(self):
        """Button handler: сохранить логи вручную"""
        saved = self.save_logs_to_file()
        if saved:
            self.log(f"Logs saved to: {saved}")
            messagebox.showinfo("Saved", f"Logs saved to: {saved}")
        else:
            messagebox.showinfo("Save Logs", "No logs to save.")
    # ================= Click & Input Logic =================
    def capture_mouse_click(self, idx):
        self.log(f"Click anywhere to set Point {idx}...")
        self.log(f"Waiting for mouse click to set point {idx}...")
        def on_click(x, y, button, pressed):
            if pressed:
                self.point_coords[idx] = (x, y)
                self.root.after(0, lambda: self.finish_capture(idx))
                return False
        listener = pynput_mouse.Listener(on_click=on_click)
        listener.daemon = True
        listener.start()
    def finish_capture(self, idx):
        try:
            self.point_buttons[idx].config(text=f"Pt {idx} Set")
        except:
            pass
        self.log(f"Point {idx} set to {self.point_coords[idx]}")
    def start_rebind(self, key_id, label_widget):
        self.log(f"Press key for {key_id}...")
        self.recording_hotkey = (key_id, label_widget)
        self.rebind_listener = pynput_keyboard.Listener(on_press=self.on_rebind_press)
        self.rebind_listener.daemon = True
        self.rebind_listener.start()
    def on_rebind_press(self, key):
        try:
            k_str = key.char if hasattr(key, 'char') and key.char else str(key).replace('Key.', '')
            action, label = self.recording_hotkey
            self.hotkeys[action] = k_str
            self.root.after(0, lambda: label.config(text=k_str.upper()))
            self.root.after(0, lambda: self.log(f"Bound {action} to {k_str}"))
            self.root.after(0, self.register_hotkeys)
            return False
        except Exception as e:
            self.log("Rebind error", e)
            return False
    def register_hotkeys(self):
        try:
            keyboard.unhook_all()
            # IMPORTANT: use wrapper for toggle to enforce cooldown
            keyboard.add_hotkey(self.hotkeys['toggle_loop'], self.hotkey_toggle_wrapper)
            keyboard.add_hotkey(self.hotkeys['toggle_overlay'], self.toggle_overlay)
            keyboard.add_hotkey(self.hotkeys['exit'], self.exit_app)
            self.log("Hotkeys registered:", self.hotkeys)
        except Exception as e:
            self.log("Hotkey registration failed:", e)
    def hotkey_toggle_wrapper(self):
        """Wrapper called by hotkey: enforces cooldown."""
        now = time.time()
        if now - self.last_toggle_time < self.toggle_cooldown:
            self.log(f"Toggle cooldown active ({self.toggle_cooldown}s). Ignoring.")
            return
        self.last_toggle_time = now
        # Play start/stop sounds inside toggle_main_loop (it already handles which to play)
        self.toggle_main_loop()
    # ================= Overlay Logic =================
    def toggle_overlay(self):
        if self.overlay_active:
            if self.overlay_window:
                try:
                    self.overlay_window.destroy()
                except:
                    pass
            self.overlay_active = False
            self.overlay_label.config(text="Overlay: HIDDEN", foreground='#666666')
            self.log("Overlay hidden")
        else:
            self.overlay_active = True
            self.overlay_label.config(text="Overlay: VISIBLE", foreground=self.colors['accent'])
            self.create_overlay()
            self.log("Overlay created")
    def create_overlay(self):
        self.overlay_window = tk.Toplevel(self.root)
        # allow alpha and topmost; keep minimal visuals
        self.overlay_window.attributes('-topmost', True, '-alpha', 0.45)
        self.overlay_window.overrideredirect(True)
        # changed color to blue per request
        self.overlay_window.configure(bg='#55AAFF')
        g = f"{self.overlay_area['width']}x{self.overlay_area['height']}+{self.overlay_area['x']}+{self.overlay_area['y']}"
        self.overlay_window.geometry(g)
        self.overlay_window.bind('<ButtonPress-1>', self._overlay_start_drag)
        self.overlay_window.bind('<B1-Motion>', self._overlay_on_drag)
        self.overlay_window.bind('<ButtonRelease-1>', self._overlay_stop_drag)
        self.overlay_window.bind('<Motion>', self._overlay_update_cursor)
        self._drag_data = {"x": 0, "y": 0, "mode": None}
    def _get_resize_mode(self, x, y, w, h):
        edge_size = 15
        if x < edge_size and y < edge_size: return 'nw'
        if x > w - edge_size and y > h - edge_size: return 'se'
        if x < edge_size and y > h - edge_size: return 'sw'
        if x > w - edge_size and y < edge_size: return 'ne'
        return 'move'
    def _overlay_update_cursor(self, event):
        try:
            w = self.overlay_window.winfo_width()
            h = self.overlay_window.winfo_height()
            mode = self._get_resize_mode(event.x, event.y, w, h)
            cursor_map = {'nw': 'size_nw_se', 'se': 'size_nw_se', 'sw': 'size_ne_sw', 'ne': 'size_ne_sw', 'move': 'fleur'}
            self.overlay_window.config(cursor=cursor_map.get(mode, 'arrow'))
        except Exception:
            pass
    def _overlay_start_drag(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y
        try:
            w = self.overlay_window.winfo_width()
            h = self.overlay_window.winfo_height()
            self._drag_data["mode"] = self._get_resize_mode(event.x, event.y, w, h)
        except Exception:
            self._drag_data["mode"] = 'move'
    def _overlay_on_drag(self, event):
        try:
            dx = event.x - self._drag_data["x"]
            dy = event.y - self._drag_data["y"]
            cur_x = self.overlay_window.winfo_x()
            cur_y = self.overlay_window.winfo_y()
            cur_w = self.overlay_window.winfo_width()
            cur_h = self.overlay_window.winfo_height()
            mode = self._drag_data["mode"]
            if mode == 'move':
                new_x = cur_x + dx
                new_y = cur_y + dy
                self.overlay_window.geometry(f"{cur_w}x{cur_h}+{new_x}+{new_y}")
                self.overlay_area['x'] = new_x
                self.overlay_area['y'] = new_y
            elif mode == 'se':
                new_w = max(50, cur_w + dx)
                new_h = max(50, cur_h + dy)
                self.overlay_window.geometry(f"{new_w}x{new_h}+{cur_x}+{cur_y}")
                self._drag_data["x"] = event.x
                self._drag_data["y"] = event.y
                self.overlay_area['width'] = new_w
                self.overlay_area['height'] = new_h
        except Exception as e:
            self.log("Overlay drag error:", e)
    def _overlay_stop_drag(self, event):
        self._drag_data["mode"] = None
    # ================= Automation Primitives =================
    def click_at(self, coords):
        if not coords: return
        try:
            x, y = int(coords[0]), int(coords[1])
            win32api.SetCursorPos((x, y))
            time.sleep(0.05)
            # Wiggle
            win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, 1, 1, 0, 0)
            time.sleep(0.02)
            win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, -1, -1, 0, 0)
            time.sleep(0.02)
            # Click
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.1)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            self.log(f"Clicked at {coords}")
        except Exception as e:
            self.log("click_at error:", e)
    def move_and_wiggle(self, coords):
        if not coords: return
        try:
            x, y = int(coords[0]), int(coords[1])
            win32api.SetCursorPos((x, y))
            time.sleep(0.05)
            win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, 1, 1, 0, 0)
            time.sleep(0.02)
            win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, -1, -1, 0, 0)
            self.log(f"Moved (wiggle) to {coords}")
        except Exception as e:
            self.log("move_and_wiggle error:", e)
    def _move_to(self, coords):
        if not coords: return
        try:
            x, y = int(coords[0]), int(coords[1])
            win32api.SetCursorPos((x, y))
            time.sleep(0.05)
        except Exception as e:
            self.log("_move_to error:", e)
    def press_key(self, k, duration=0.3):
        try:
            vk = win32api.VkKeyScan(k)
            scan = win32api.MapVirtualKey(vk & 0xFF, 0)
            win32api.keybd_event(vk, scan, 0, 0)
            time.sleep(duration)
            win32api.keybd_event(vk, scan, win32con.KEYEVENTF_KEYUP, 0)
            self.log(f"Pressed key '{k}' for {duration}s")
        except Exception as e:
            self.log("press_key error:", e)
    def type_text(self, text):
        for char in str(text):
            self.press_key(char, 0.02)
            time.sleep(0.02)
    def cast_line(self):
        try:
            self.log("Casting...")
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(1.0)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            self.is_clicking = False
            self.total_cycles += 1
            self.root.after(0, self._update_stats_labels)
            self.log("Cast Complete.")
        except Exception as e:
            self.log("cast_line error:", e)
    def run_auto_purchase(self):
        self.log("Starting Auto Purchase...")
        pts = self.point_coords
        if not all([pts[1], pts[2], pts[3], pts[4]]):
            self.log("Points not set! Auto purchase aborted.")
            return
        try:
            self.log("Pressing E...")
            self.press_key('e', duration=0.5)
            time.sleep(self.interact_delay_var.get())
            # Sequence: 1 -> 2 -> 1 -> 3 -> 2 -> 4 (Move + Wiggle)
            self.click_at(pts[1])
            time.sleep(0.5)
            self.click_at(pts[2])
            time.sleep(0.5)
            self.type_text(self.amount_var.get())
            time.sleep(0.5)
            self.click_at(pts[1])
            time.sleep(0.5)
            self.click_at(pts[3])
            time.sleep(0.5)
            self.click_at(pts[2])
            time.sleep(0.5)
            # Point 4: Move + Wiggle (No Click)
            self.move_and_wiggle(pts[4])
            time.sleep(1.0)
            # update purchase counters
            self.total_purchases += 1
            self.root.after(0, self._update_stats_labels)
            self.log("Auto purchase completed. Total purchases:", self.total_purchases)
        except Exception as e:
            self.log(f"Purchase Error: {e}")
    def _update_stats_labels(self):
        try:
            self.purchases_label.config(text=f"Purchases: {self.total_purchases}")
            self.cycles_label.config(text=f"Cycles: {self.total_cycles}")
        except Exception:
            pass
    def _update_uptime(self):
        if self.main_loop_active and self.start_time is not None:
            elapsed = int(time.time() - self.start_time)
            h = elapsed // 3600
            m = (elapsed % 3600) // 60
            s = elapsed % 60
            self.uptime_label.config(text=f"Uptime: {h:02d}:{m:02d}:{s:02d}")
            self.root.after(1000, self._update_uptime)
        else:
            if not self.main_loop_active:
                self.uptime_label.config(text="Uptime: 00:00:00")
    # ================= Sound helper =================
    def play_sound(self, name):
        """Play a wav file named name.wav asynchronously. Swallow exceptions."""
        try:
            path = f"{name}.wav"
            if os.path.exists(path):
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                self.log(f"Sound file not found: {path}")
        except Exception as e:
            self.log("play_sound error:", e)
    # ================= Main Worker Loop =================
    def toggle_main_loop(self):
        self.main_loop_active = not self.main_loop_active
        if self.main_loop_active:
            # on start — reset counters/time as requested
            self.total_purchases = 0
            self.total_cycles = 0
            self.purchase_counter = 0
            self.start_time = time.time()
            self._update_stats_labels()
            self._update_uptime()
            if self.auto_purchase_var.get():
                if not all(self.point_coords.values()):
                    messagebox.showwarning("Setup", "Please set all 4 points first.")
                    self.main_loop_active = False
                    # reset uptime as start was aborted
                    self.start_time = None
                    return
            self.status_indicator.config(text="RUNNING", bg=self.colors['success'])
            # play start sound
            try:
                self.play_sound(self.start_sound_name)
            except:
                pass
            threading.Thread(target=self.worker, daemon=True).start()
            self.log("Main loop started")
        else:
            self.status_indicator.config(text="STOPPED", bg=self.colors['danger'])
            # play stop sound
            try:
                self.play_sound(self.stop_sound_name)
            except:
                pass
            self.log("Main loop stopped")
            # IMPORTANT: removed auto-saving logs here (user wanted manual Save Logs)
            # reset uptime start_time
            self.start_time = None
            self.uptime_label.config(text="Uptime: 00:00:00")
    def worker(self):
        sct = mss.mss()
        time.sleep(1.0) # Safety delay
        if self.auto_purchase_var.get():
            self.run_auto_purchase()
        self.cast_line()
        time.sleep(self.rod_reset_var.get())
        last_detection_time = time.time()
        was_detecting = False
        last_known_white_y = 0
        white_bar_lost_time = 0
        while self.main_loop_active:
            try:
                monitor = {
                    'left': self.overlay_area['x'], 'top': self.overlay_area['y'],
                    'width': self.overlay_area['width'], 'height': self.overlay_area['height']
                }
                img = np.array(sct.grab(monitor))
                blue_mask = (
                    (np.abs(img[:,:,2] - COLOR_BAR_CONTAINER[0]) < COLOR_TOLERANCE) &
                    (np.abs(img[:,:,1] - COLOR_BAR_CONTAINER[1]) < COLOR_TOLERANCE) &
                    (np.abs(img[:,:,0] - COLOR_BAR_CONTAINER[2]) < COLOR_TOLERANCE)
                )
                col_counts = np.sum(blue_mask, axis=0)
                valid_cols = np.where(col_counts > 100)[0]
                if valid_cols.size == 0:
                    if was_detecting and (time.time() - last_detection_time > 1.0):
                        self.log("Bar lost completely. Cycle finished/Resetting.")
                        was_detecting = False
                        if self.auto_purchase_var.get():
                            self.purchase_counter += 1
                            if self.purchase_counter >= self.loops_var.get():
                                self.run_auto_purchase()
                                self.purchase_counter = 0
                        self.cast_line()
                        time.sleep(self.rod_reset_var.get())
                        last_detection_time = time.time()
                    if time.time() - last_detection_time > self.timeout_var.get():
                        self.log("Timeout. Recasting.")
                        self.cast_line()
                        time.sleep(self.rod_reset_var.get())
                        last_detection_time = time.time()
                    time.sleep(0.1)
                    continue
                min_x, max_x = valid_cols[0], valid_cols[-1]
                col_slice = blue_mask[:, min_x:max_x]
                row_counts = np.sum(col_slice, axis=1)
                valid_rows = np.where(row_counts > 5)[0]
                if valid_rows.size == 0:
                    time.sleep(0.01)
                    continue
                min_y, max_y = valid_rows[0], valid_rows[-1]
                bar_height = max_y - min_y
                crop = img[min_y:max_y, min_x:max_x, :]
                was_detecting = True
                last_detection_time = time.time()
                dark_mask = (
                    (np.abs(crop[:,:,2] - COLOR_SAFE_ZONE_BACKGROUND[0]) < 10) &
                    (np.abs(crop[:,:,1] - COLOR_SAFE_ZONE_BACKGROUND[1]) < 10) &
                    (np.abs(crop[:,:,0] - COLOR_SAFE_ZONE_BACKGROUND[2]) < 10)
                )
                dark_indices = np.where(np.any(dark_mask, axis=1))[0]
                target_y = bar_height / 2
                if dark_indices.size > 0:
                    diffs_d = np.diff(dark_indices)
                    splits_d = np.where(diffs_d > 5)[0] + 1
                    sections_d = np.split(dark_indices, splits_d)
                    longest_d = max(sections_d, key=len)
                    if len(longest_d) > 0:
                        target_y = (longest_d[0] + longest_d[-1]) // 2
                white_mask = (
                    (np.abs(crop[:,:,2] - COLOR_MOVING_INDICATOR[0]) < 10) &
                    (np.abs(crop[:,:,1] - COLOR_MOVING_INDICATOR[1]) < 10) &
                    (np.abs(crop[:,:,0] - COLOR_MOVING_INDICATOR[2]) < 10)
                )
                white_coords = np.argwhere(white_mask)
                indicator_y = 0
                if white_coords.size == 0:
                    current_time = time.time()
                    if white_bar_lost_time == 0:
                        white_bar_lost_time = current_time
                    if current_time - white_bar_lost_time > 0.2:
                        self.log("Stuck! Attempting recovery clicks...")
                        if last_known_white_y > (bar_height / 2):
                            for _ in range(2):
                                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0,0,0,0)
                                time.sleep(0.1)
                                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0,0,0,0)
                                time.sleep(0.1)
                        else:
                            if self.is_clicking:
                                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0,0,0,0)
                                self.is_clicking = False
                        continue
                else:
                    white_bar_lost_time = 0
                    indicator_y = white_coords[:, 0].min()
                    last_known_white_y = indicator_y
                if bar_height == 0:
                    time.sleep(0.01)
                    continue
                error = target_y - indicator_y
                norm_error = error / bar_height
                derivative = norm_error - self.previous_error
                self.previous_error = norm_error
                output = (self.kp_var.get() * norm_error) + (self.kd_var.get() * derivative)
                if output > 0 and not self.is_clicking:
                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0,0,0,0)
                    self.is_clicking = True
                elif output <= 0 and self.is_clicking:
                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0,0,0,0)
                    self.is_clicking = False
                time.sleep(0.01)
            except Exception as e:
                self.log(f"Error in worker loop: {e}")
                time.sleep(1)
        if self.is_clicking:
            try:
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0,0,0,0)
            except Exception:
                pass
            self.is_clicking = False
    def exit_app(self):
        # Stop loop
        self.main_loop_active = False
        # IMPORTANT: removed auto-saving logs on exit; user wants manual save
        if self.overlay_window:
            try:
                self.overlay_window.destroy()
            except:
                pass
        try:
            keyboard.unhook_all()
        except:
            pass
        # stop telegram bot if running
        self.stop_telegram_bot()
        self.log("Exiting app...")
        try:
            self.root.destroy()
        except:
            pass
        try:
            sys.exit(0)
        except:
            pass
    # ================= Config Save/Load =================
    def save_config(self):
        try:
            cfg = {
                'hotkeys': self.hotkeys,
                'points': {k: self.point_coords[k] for k in self.point_coords},
                'amount': int(self.amount_var.get()),
                'loops': int(self.loops_var.get()),
                'interact_delay': float(self.interact_delay_var.get()),
                'kp': float(self.kp_var.get()),
                'kd': float(self.kd_var.get()),
                'rod_reset': float(self.rod_reset_var.get()),
                'timeout': float(self.timeout_var.get()),
                'overlay_area': self.overlay_area,
                'running': bool(self.main_loop_active),
                'telegram': {
                    'token': self.telegram_token,
                    'chat_id': int(self.telegram_chat_id) if self.telegram_chat_id else None
                }
            }
            with open(CFG_FILE, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, indent=2)
            self.log("Configuration saved.")
        except Exception as e:
            self.log("Failed to save config:", e)
    def load_config(self):
        try:
            if not os.path.exists(CFG_FILE):
                return
            with open(CFG_FILE, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            # Apply values carefully
            if 'hotkeys' in cfg:
                self.hotkeys.update(cfg['hotkeys'])
            if 'points' in cfg:
                for k, v in cfg['points'].items():
                    try:
                        idx = int(k)
                        self.point_coords[idx] = tuple(v) if v else None
                    except:
                        pass
            # simple scalar settings
            try:
                self.amount_var.set(int(cfg.get('amount', self.amount_var.get())))
                self.loops_var.set(int(cfg.get('loops', self.loops_var.get())))
                self.interact_delay_var.set(float(cfg.get('interact_delay', self.interact_delay_var.get())))
                self.kp_var.set(float(cfg.get('kp', self.kp_var.get())))
                self.kd_var.set(float(cfg.get('kd', self.kd_var.get())))
                self.rod_reset_var.set(float(cfg.get('rod_reset', self.rod_reset_var.get())))
                self.timeout_var.set(float(cfg.get('timeout', self.timeout_var.get())))
            except Exception:
                pass
            if 'overlay_area' in cfg:
                try:
                    self.overlay_area.update(cfg['overlay_area'])
                except:
                    pass
            if 'telegram' in cfg:
                try:
                    tg = cfg['telegram']
                    self.telegram_token = tg.get('token', '') or ''
                    self.telegram_chat_id = int(tg['chat_id']) if tg.get('chat_id') else None
                except:
                    pass
            # Update UI labels for points and hotkeys (if widgets exist)
            for idx, btn in self.point_buttons.items():
                if self.point_coords.get(idx):
                    try:
                        btn.config(text=f"Pt {idx} Set")
                    except:
                        pass
            for key_id, lbl in self.hotkey_labels.items():
                try:
                    lbl.config(text=self.hotkeys.get(key_id, '').upper())
                except:
                    pass
            self.log("Configuration loaded.")
            # Auto-start if saved as running
            if cfg.get('running', False):
                self.toggle_main_loop()
        except Exception as e:
            self.log("Failed to load config:", e)
    # ================= Telegram / TgHook UI & Worker =================
    def open_tghook_window(self):
        """Open a small window to enter bot token and chat_id, start/stop bot."""
        w = tk.Toplevel(self.root)
        w.title("TgHook")
        w.attributes('-topmost', True)
        w.geometry("360x180")
        ttk.Label(w, text="Telegram Bot Token:").pack(anchor='w', padx=10, pady=(10,2))
        token_entry = tk.Entry(w, width=48)
        token_entry.pack(padx=10)
        token_entry.insert(0, self.telegram_token or "")
        ttk.Label(w, text="Chat ID (user/chat to accept /check):").pack(anchor='w', padx=10, pady=(10,2))
        chat_entry = tk.Entry(w, width=24)
        chat_entry.pack(padx=10)
        chat_entry.insert(0, str(self.telegram_chat_id) if self.telegram_chat_id else "")
        btn_frame = ttk.Frame(w)
        btn_frame.pack(fill='x', pady=12, padx=10)
        def save_and_start():
            self.telegram_token = token_entry.get().strip()
            chat_text = chat_entry.get().strip()
            self.telegram_chat_id = int(chat_text) if chat_text else None
            self.save_config()
            self.log("Telegram settings saved.")
            # start bot automatically when settings provided
            if self.telegram_token:
                self.start_telegram_bot()
            messagebox.showinfo("TgHook", "Settings saved.")
            w.destroy()
        ttk.Button(btn_frame, text="Save", command=save_and_start).pack(side='left')
        ttk.Button(btn_frame, text="Start", command=lambda: (setattr(self, 'telegram_token', token_entry.get().strip()), setattr(self, 'telegram_chat_id', int(chat_entry.get().strip()) if chat_entry.get().strip() else None), self.start_telegram_bot(), self.save_config(), w.destroy())).pack(side='left', padx=6)
        ttk.Button(btn_frame, text="Stop", command=lambda: (self.stop_telegram_bot(), messagebox.showinfo("TgHook","Bot stopped."))).pack(side='right')
    def start_telegram_bot(self):
        if not self.telegram_token:
            self.log("Telegram token not set; cannot start bot.")
            return
        if self.telegram_running:
            self.log("Telegram bot already running.")
            return
        self.telegram_running = True
        self.telegram_offset = 0
        self.telegram_thread = threading.Thread(target=self.telegram_worker, daemon=True)
        self.telegram_thread.start()
        self.log("Telegram bot started (polling).")
        # Send notification
        if self.telegram_chat_id:
            pc_name = os.environ.get('COMPUTERNAME', 'Unknown PC')
            self.send_telegram_message(self.telegram_chat_id, f"Макрос запущен с ПК {pc_name}")
    def stop_telegram_bot(self):
        if not self.telegram_running:
            return
        self.telegram_running = False
        self.log("Stopping Telegram bot...")
        # thread is daemon; it will exit automatically when loop sees flag
    def telegram_worker(self):
        """Simple long-polling worker checking for /check command and responding."""
        token = self.telegram_token
        base = f"https://api.telegram.org/bot{token}"
        while self.telegram_running:
            try:
                resp = requests.get(f"{base}/getUpdates", params={'offset': self.telegram_offset, 'timeout': 10}, timeout=15)
                if resp.status_code != 200:
                    self.log("Telegram getUpdates failed:", resp.status_code)
                    time.sleep(5)
                    continue
                data = resp.json()
                if not data.get('ok'):
                    time.sleep(2)
                    continue
                for upd in data.get('result', []):
                    self.telegram_offset = max(self.telegram_offset, upd['update_id'] + 1)
                    msg = upd.get('message') or upd.get('edited_message') or {}
                    text = msg.get('text', '')
                    from_id = msg.get('from', {}).get('id')
                    chat_id = msg.get('chat', {}).get('id')
                    # check command
                    if text and text.strip().startswith('/check'):
                        # if chat restriction is set, allow only that chat
                        if self.telegram_chat_id and int(chat_id) != int(self.telegram_chat_id):
                            self.send_telegram_message(chat_id, "Unauthorized.")
                        else:
                            # send status message and screenshot
                            status_text = f"Purchases: {self.total_purchases}\nCycles: {self.total_cycles}\nUptime: {self.uptime_label.cget('text')}"
                            self.send_telegram_message(chat_id, status_text)
                            # take hidden screenshot of overlay area and send
                            try:
                                sct = mss.mss()
                                mon = {
                                    'left': self.overlay_area['x'], 'top': self.overlay_area['y'],
                                    'width': self.overlay_area['width'], 'height': self.overlay_area['height']
                                }
                                img = sct.grab(mon)
                                tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
                                mss.tools.to_png(img.rgb, img.size, output=tmp.name)
                                tmp.close()
                                self.send_telegram_photo(chat_id, tmp.name)
                                try:
                                    os.unlink(tmp.name)
                                except:
                                    pass
                                # Additional: full screen screenshot
                                full_mon = sct.monitors[1]  # Primary monitor
                                full_img = sct.grab(full_mon)
                                full_tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
                                mss.tools.to_png(full_img.rgb, full_img.size, output=full_tmp.name)
                                full_tmp.close()
                                self.send_telegram_photo(chat_id, full_tmp.name)
                                try:
                                    os.unlink(full_tmp.name)
                                except:
                                    pass
                            except Exception as e:
                                self.log("Failed to send screenshot:", e)
                    elif text and text.strip().startswith('/restart'):
                        if self.telegram_chat_id and int(chat_id) != int(self.telegram_chat_id):
                            self.send_telegram_message(chat_аid, "Unauthorized.")
                        else:
                            now = time.time()
                            if now - self.last_restart_time < self.restart_cooldown:
                                self.send_telegram_message(chat_id, f"Restart cooldown active ({self.restart_cooldown}s). Ignoring.")
                                continue
                            self.last_restart_time = now
                            self.log("Received /restart from Telegram.")
                            self.send_telegram_message(chat_id, "Restarting macro...")
                            self.hotkey_toggle_wrapper()
                            time.sleep(2)
                            self.hotkey_toggle_wrapper()
                            self.send_telegram_message(chat_id, "Macro restarted.")
                # small sleep to avoid hammering on errors
            except Exception as e:
                self.log("Telegram worker error:", e)
                time.sleep(3)
    def send_telegram_message(self, chat_id, text):
        """Send text message via Telegram bot."""
        try:
            token = self.telegram_token
            base = f"https://api.telegram.org/bot{token}"
            requests.post(f"{base}/sendMessage", data={'chat_id': chat_id, 'text': text}, timeout=10)
        except Exception as e:
            self.log("send_telegram_message error:", e)
    def send_telegram_photo(self, chat_id, filepath):
        """Send photo via Telegram bot (multipart)."""
        try:
            token = self.telegram_token
            base = f"https://api.telegram.org/bot{token}"
            with open(filepath, 'rb') as f:
                files = {'photo': f}
                data = {'chat_id': chat_id}
                requests.post(f"{base}/sendPhoto", data=data, files=files, timeout=20)
        except Exception as e:
            self.log("send_telegram_photo error:", e)
if __name__ == '__main__':
    root = tk.Tk()
    app = ModernGPOBot(root)
    root.mainloop()