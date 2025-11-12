# -*- coding: utf-8 -*-
import os
import sys
import re
import json
import time
import threading
import ctypes
from ctypes import wintypes
from pathlib import Path
from typing import Dict, Tuple, Optional, List

# ===== 相依套件 =====
# pip install mss opencv-python numpy
import mss
import cv2
import numpy as np

# ====== GUI ======
try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except Exception:
    tk = None  # 若打包時無 tkinter，仍可用命令列模式

# ===== 參數 =====
REQUIRE_ADMIN = True   # 需要與遊戲同等權限時設 True
TEMPLATE_DIR = "templates"          # 內含多組解析度樣板，例如 1920x1080/win.png 等
DETECT_THRESHOLD = 0.85
MONITOR_INDEX = 1                   # 預設目標螢幕（1 起算）
POLL_INTERVAL_SEC = 0.03

# 觸發條件
CONFIRM_FRAMES = 6                  # 同一標籤連續命中幀數才觸發
POST_TRIGGER_COOLDOWN_SEC = 1       # 很短的冷卻，只為避免同一批幀重複觸發

# ★ 場景變化後才重武裝（避免同一張結果畫面連續觸發）
CHANGE_REARM_HAMMING = 6
CHANGE_REARM_TIMEOUT_SEC = 4.0

DRAW_STOP_AT = 30

# ★ 可選：自動搶回焦點（填你的遊戲視窗關鍵字；留空則不做）
FOCUS_WINDOW_SUBSTR = ""  # 例如 "BlueStacks" 或 遊戲標題的一段（大小寫不敏感）

# ===== 停止鍵 (F12) =====
VK_F12 = 0x7B
user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32

# ===== 自動校準開關與參數 =====
AUTO_CALIBRATE_ON_START = False                 # 有 GUI 的情況下，通常由按鈕決定
SCALES = [round(s, 2) for s in np.linspace(0.75, 1.35, 13)]  # 多尺度比對（解析度正確時只需微調）
EARLY_STOP_SCORE = 0.95                        # 命中分數高於此值即提前結束校準
ROI_EXPAND = 1.6                               # ROI 相對命中模板的放大倍數
CALIB_MIN_SCORE = 0.80                         # 低於此分數視為校準失敗（避免 ~0.6 假命中）
ASPECT_TOL = 0.02                              # 解析度包選擇時，允許的長寬比差距

# ===== 設定與檔案路徑 =====
APP_NAME = "AutoROIExample"
CONFIG_DIR = os.path.join(os.getenv("APPDATA") or str(Path.home()), APP_NAME)
os.makedirs(CONFIG_DIR, exist_ok=True)
ROI_JSON_PATH = os.path.join(CONFIG_DIR, "roi.json")

# ============ DPI & 資源路徑 ============
def set_dpi_awareness():
    """避免 Windows 縮放導致座標錯位。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor v2
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

def resource_path(rel: str) -> str:
    """PyInstaller 相容：在 onefile 模式下，資料會解壓在 sys._MEIPASS。"""
    try:
        base = sys._MEIPASS  # pyinstaller 一檔模式的臨時解壓路徑
    except Exception:
        base = os.path.abspath(".")
    return os.path.join(base, rel)

# ============ 停止鍵/例外處理 ============
class StopRequested(Exception):
    pass

_STOP_LATCHED = False
_STOP_EVENT = threading.Event()

def is_stop_pressed() -> bool:
    global _STOP_LATCHED
    if _STOP_LATCHED:
        return True
    try:
        state = user32.GetAsyncKeyState(VK_F12)
        if state & 0x8000:
            _STOP_LATCHED = True
            return True
    except Exception:
        return False
    return False

def ensure_not_stopped():
    if _STOP_EVENT.is_set() or is_stop_pressed():
        raise StopRequested()

# ===== 提權（可選）=====
def ensure_admin_or_elevate():
    try:
        if shell32.IsUserAnAdmin():
            return
    except Exception:
        return
    try:
        params = " ".join([f'"{p}"' if " " in p else p for p in sys.argv])
        ret = shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        if int(ret) > 32:
            sys.exit(0)  # 已另起提權行程
        else:
            gui_log("[警告] 嘗試提權失敗，將以目前權限繼續。")
    except Exception:
        gui_log("[警告] 提權過程出錯，將以目前權限繼續。")

# ============ SendInput & 鍵盤 ============
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP       = 0x0002
KEYEVENTF_SCANCODE    = 0x0008

PUL = ctypes.POINTER(ctypes.c_ulong)

class KeyBdInput(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", PUL)]

class HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong),
                ("wParamL", ctypes.c_short),
                ("wParamH", ctypes.c_ushort)]

class MouseInput(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", PUL)]

class Input_I(ctypes.Union):
    _fields_ = [("ki", KeyBdInput),
                ("mi", MouseInput),
                ("hi", HardwareInput)]

class Input(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong),
                ("ii", Input_I)]

# 常用掃描碼
SCAN_CODE_LEFT  = 0x4B
SCAN_CODE_RIGHT = 0x4D
SCAN_CODE_UP    = 0x48
SCAN_CODE_DOWN  = 0x50

# 鍵名 -> 掃描碼（US 鍵盤）
SCAN_CODE_MAP = {
    # 數字列
    '1': 0x02, '2': 0x03, '3': 0x04, '4': 0x05, '5': 0x06,
    '6': 0x07, '7': 0x08, '8': 0x09, '9': 0x0A, '0': 0x0B,
    # 字母
    'a': 0x1E, 'b': 0x30, 'c': 0x2E, 'd': 0x20, 'e': 0x12,
    'f': 0x21, 'g': 0x22, 'h': 0x23, 'i': 0x17, 'j': 0x24,
    'k': 0x25, 'l': 0x26, 'm': 0x32, 'n': 0x31, 'o': 0x18,
    'p': 0x19, 'q': 0x10, 'r': 0x13, 's': 0x1F, 't': 0x14,
    'u': 0x16, 'v': 0x2F, 'w': 0x11, 'x': 0x2D, 'y': 0x15, 'z': 0x2C,
    # 控制鍵
    'space': 0x39, 'tab': 0x0F, 'enter': 0x1C, 'esc': 0x01, 'backspace': 0x0E,
    'shift': 0x2A, 'ctrl': 0x1D, 'alt': 0x38,
    # 方向鍵
    'left': SCAN_CODE_LEFT, 'right': SCAN_CODE_RIGHT, 'up': SCAN_CODE_UP, 'down': SCAN_CODE_DOWN,
}

# 需要 EXTENDED 標誌的鍵
EXTENDED_KEYS = {'left', 'right', 'up', 'down', 'insert', 'delete', 'home', 'end', 'pageup', 'pagedown'}

def hold_key(scan_code: int, is_extended: bool = False):
    flags = KEYEVENTF_SCANCODE
    if is_extended:
        flags |= KEYEVENTF_EXTENDEDKEY
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    ii_.ki = KeyBdInput(0, scan_code, flags, 0, ctypes.pointer(extra))
    x = Input(ctypes.c_ulong(1), ii_)
    ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))

def release_key(scan_code: int, is_extended: bool = False):
    flags = KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP
    if is_extended:
        flags |= KEYEVENTF_EXTENDEDKEY
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    ii_.ki = KeyBdInput(0, scan_code, flags, 0, ctypes.pointer(extra))
    x = Input(ctypes.c_ulong(1), ii_)
    ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))

def press(key: str, hold_ms: int = 30):
    key_l = key.lower()
    if key_l not in SCAN_CODE_MAP:
        gui_log(f"[警告] 未知鍵名：{key}")
        return
    scan = SCAN_CODE_MAP[key_l]
    ext = key_l in EXTENDED_KEYS
    hold_key(scan, ext)
    time.sleep(max(0, hold_ms) / 1000.0)
    release_key(scan, ext)

def press_times(key: str, times: int, gap_sec: float = 0.2, hold_ms: int = 30):
    for _ in range(max(0, times)):
        ensure_not_stopped()
        press(key, hold_ms=hold_ms)
        time.sleep(gap_sec)

def wait_with_cancel(seconds: float):
    deadline = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < deadline:
        ensure_not_stopped()
        time.sleep(0.01)

# ============ 視窗焦點＆定位 ============
def _enum_windows():
    hwnds = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def callback(hwnd, lParam):
        if user32.IsWindowVisible(hwnd):
            hwnds.append(hwnd)
        return True

    user32.EnumWindows(callback, 0)
    return hwnds

def _get_window_text(hwnd) -> str:
    length = user32.GetWindowTextLengthW(hwnd) + 1
    buf = ctypes.create_unicode_buffer(length)
    user32.GetWindowTextW(hwnd, buf, length)
    return buf.value

def focus_target_window_if_needed():
    if not FOCUS_WINDOW_SUBSTR:
        return
    target = FOCUS_WINDOW_SUBSTR.lower()
    try:
        for hwnd in _enum_windows():
            title = _get_window_text(hwnd).lower()
            if target in title and len(title.strip()) > 0:
                user32.ShowWindow(hwnd, 5)  # SW_SHOW
                user32.SetForegroundWindow(hwnd)
                user32.BringWindowToTop(hwnd)
                gui_log(f"[焦點] 已嘗試聚焦視窗：{title}")
                return
    except Exception as e:
        gui_log(f"[焦點] 聚焦失敗：{e}")

def _get_window_rect_by_title(substr: str) -> Optional[Tuple[int,int,int,int]]:
    if not substr:
        return None
    target = substr.lower()
    result = [None]

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def enum_cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd) + 1
            buf = ctypes.create_unicode_buffer(length)
            user32.GetWindowTextW(hwnd, buf, length)
            title = buf.value
            if title and target in title.lower():
                rect = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                result[0] = (rect.left, rect.top, rect.right, rect.bottom)
                return False
        return True

    user32.EnumWindows(enum_cb, 0)
    return result[0]

def _get_foreground_client_bbox() -> Optional[Dict[str, int]]:
    """取得目前前景視窗的 Client 區域轉為螢幕座標的 bbox（left/top/width/height）。"""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    pt = wintypes.POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(pt)):
        return None
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    return {"left": pt.x, "top": pt.y, "width": width, "height": height}

# ============ 樣板解析度包（重點新增） ============
_PACK_REGEX = re.compile(r"^(\d+)[xX](\d+)$")

def _list_template_packs(root: str) -> List[Tuple[str, int, int]]:
    """列出 templates 根目錄下可用的解析度包 (name, w, h)。"""
    packs = []
    if not os.path.isdir(root):
        return packs
    for name in os.listdir(root):
        path = os.path.join(root, name)
        if not os.path.isdir(path):
            continue
        m = _PACK_REGEX.match(name.strip())
        if m:
            w, h = int(m.group(1)), int(m.group(2))
            packs.append((name, w, h))
    return packs

def _select_template_pack(root: str, w: int, h: int) -> Tuple[str, str]:
    """
    挑選最適合的樣板資料夾：
      1) 先找完全相同解析度的資料夾 "<w>x<h>"
      2) 再找長寬比最接近且尺寸最接近者（aspect diff <= ASPECT_TOL）
      3) 退回 default/ 或 root
    回傳 (abs_dir, pack_name)。pack_name 可能為 "default" 或 ""(根目錄)。
    """
    packs = _list_template_packs(root)
    exact_name = f"{w}x{h}"

    # 完全符合
    for name, pw, ph in packs:
        if name == exact_name:
            return os.path.join(root, name), name

    # 找最接近比例者
    if w > 0 and h > 0 and packs:
        target_ar = w / h
        best = None
        best_key = None
        for name, pw, ph in packs:
            ar = pw / ph
            ar_diff = abs(ar - target_ar)
            if ar_diff > ASPECT_TOL:
                continue
            # 統一度量（比例差 + 尺寸差比重）
            size_diff = abs(pw - w) + abs(ph - h)
            key = (ar_diff, size_diff)
            if (best is None) or (key < best_key):
                best = (name, pw, ph)
                best_key = key
        if best:
            sel = best[0]
            return os.path.join(root, sel), sel

    # default/ 或根目錄
    default_dir = os.path.join(root, "default")
    if os.path.isdir(default_dir):
        return default_dir, "default"
    return root, ""  # root 直接放 win.png/loss.png/draw.png

# ============ 影像偵測（模板比對） ============
class TemplateDetector:
    def __init__(self, templates_dir: str, threshold: float):
        self.dir = templates_dir
        self.threshold = threshold
        self.templates = self._load()

    def _load(self):
        names = ["win", "loss", "draw"]
        tpls = {}
        for n in names:
            p = os.path.join(self.dir, f"{n}.png")
            if not os.path.exists(p):
                raise FileNotFoundError(f"找不到範本：{p}")
            img = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
            if img is None:
                raise RuntimeError(f"讀取範本失敗：{p}")
            tpls[n] = img
        return tpls

    @staticmethod
    def _preprocess(gray: np.ndarray) -> np.ndarray:
        # 自適應對比度等化
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(gray)

    @staticmethod
    def _edges(gray: np.ndarray) -> np.ndarray:
        v = np.median(gray)
        low = int(max(0, 0.66 * v))
        high = int(min(255, 1.33 * v))
        return cv2.Canny(gray, low, high)

    def _match_best(self, src_gray: np.ndarray, tpl_gray: np.ndarray) -> Tuple[float, Tuple[int, int]]:
        src_eq = self._preprocess(src_gray)
        tpl_eq = self._preprocess(tpl_gray)
        res1 = cv2.matchTemplate(src_eq, tpl_eq, cv2.TM_CCOEFF_NORMED)
        _, max1, _, loc1 = cv2.minMaxLoc(res1)

        src_e = self._edges(src_gray)
        tpl_e = self._edges(tpl_gray)
        res2 = cv2.matchTemplate(src_e, tpl_e, cv2.TM_CCOEFF_NORMED)
        _, max2, _, loc2 = cv2.minMaxLoc(res2)

        if max2 > max1:
            return float(max2), loc2
        return float(max1), loc1

    def detect(self, gray: np.ndarray) -> Tuple[str, float]:
        best_label, best_score = "", -1.0
        for label, tpl in self.templates.items():
            th, tw = tpl.shape[:2]
            H, W = gray.shape[:2]
            if H < th or W < tw:
                continue
            score, _ = self._match_best(gray, tpl)
            if score > best_score:
                best_score = float(score)
                best_label = label
        if best_score >= self.threshold:
            return best_label, best_score
        return "", best_score

# ============ ROI 雜湊/場景變化 ============
def roi_ahash(gray: np.ndarray) -> np.ndarray:
    small = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA)
    avg = small.mean()
    bits = (small > avg).astype(np.uint8).reshape(-1)
    return bits

def hamming(a: np.ndarray, b: np.ndarray) -> int:
    if a is None or b is None:
        return 9999
    return int(np.bitwise_xor(a, b).sum())

# ============ 三種腳本（第一階段邏輯） ============
def script_draw():
    """第一階段：draw 後快速繼續。"""
    focus_target_window_if_needed()
    wait_with_cancel(2.0); press('c')

def script_loss():
    """第一階段：loss 後的一連串操作。"""
    focus_target_window_if_needed()
    wait_with_cancel(1.0); press('c')
    wait_with_cancel(1); press('c')
    wait_with_cancel(1); press('down')
    wait_with_cancel(1); press('c')
    wait_with_cancel(1); press_times('left', 2)
    wait_with_cancel(1); press('enter')
    wait_with_cancel(1); press('c')

def script_win():
    """第一階段：win 後的一連串操作。"""
    focus_target_window_if_needed()
    wait_with_cancel(1.0); press('down')
    wait_with_cancel(1); press('c')
    wait_with_cancel(1); press_times('left', 2)
    wait_with_cancel(1); press('enter')
    wait_with_cancel(1); press('c')
    wait_with_cancel(1); press('c')
    wait_with_cancel(1); press('down')
    wait_with_cancel(1); press('c')
    wait_with_cancel(1); press_times('left', 2)
    wait_with_cancel(1); press('enter')
    wait_with_cancel(1); press('c')

def run_script(label: str):
    if label == 'draw':
        script_draw()
    elif label == 'loss':
        script_loss()
    elif label == 'win':
        script_win()

# ============ 第二階段腳本（預留 placeholder，可自行改） ============
def script_phase2_draw():
    """
    第二階段：若是 draw，要做一些動作後繼續玩。
    這裡預設沿用第一階段的 draw 處理；你可自行調整。
    """
    gui_log("[第二階段] draw → 繼續玩（可自行改動動作）")
    script_draw()  # 如需不同操作可改寫

def script_phase2_win_end():
    """
    第二階段：若是 win，做一些動作然後結束。
    你可以把下面 press 流程改成你要的收尾動作。
    """
    gui_log("[第二階段] win → 收尾並結束")
    focus_target_window_if_needed()
    # === 在此自訂你的收尾動作 ===
    # 範例：按下確認並回到主畫面
    wait_with_cancel(1.0); press('down')
    wait_with_cancel(1); press('c')
    wait_with_cancel(1); press_times('left', 2)
    wait_with_cancel(1); press('enter')
    wait_with_cancel(1); press('c')
    # 從炎魔開始按
    wait_with_cancel(1); press('c')
    wait_with_cancel(1.0); press('down')
    wait_with_cancel(1.0); press('down')
    wait_with_cancel(1); press('c')
    wait_with_cancel(1.0); press('down')
    wait_with_cancel(1); press('c')
    wait_with_cancel(1.0); press('down')
    wait_with_cancel(1); press('c')
    wait_with_cancel(1); press('c')
    wait_with_cancel(1.0); press('down')
    wait_with_cancel(1.0); press('down')
    wait_with_cancel(1); press('c')
    wait_with_cancel(1); press('c')
    wait_with_cancel(1.0); press('down')
    wait_with_cancel(1.0); press('down')
    wait_with_cancel(1.0); press('down')
    wait_with_cancel(1); press('c')
    wait_with_cancel(1); press('c')

def script_phase2_loss_end():
    """
    第二階段：若是 loss，做一些動作然後結束。
    你可以把下面 press 流程改成你要的收尾動作。
    """
    gui_log("[第二階段] loss → 收尾並結束（Placeholder）")
    focus_target_window_if_needed()
    # === 在此自訂你的收尾動作 ===
    # 範例：按下確認並回到主畫面
    wait_with_cancel(1); press('c')
    wait_with_cancel(1); press('c')
    wait_with_cancel(1.0); press('down')
    wait_with_cancel(1.0); press('down')
    wait_with_cancel(1); press('c')
    wait_with_cancel(1.0); press('down')
    wait_with_cancel(1); press('c')
    wait_with_cancel(1.0); press('down')
    wait_with_cancel(1); press('c')
    wait_with_cancel(1); press('c')
    wait_with_cancel(1.0); press('down')
    wait_with_cancel(1.0); press('down')
    wait_with_cancel(1); press('c')
    wait_with_cancel(1); press('c')
    wait_with_cancel(1.0); press('down')
    wait_with_cancel(1.0); press('down')
    wait_with_cancel(1.0); press('down')
    wait_with_cancel(1); press('c')
    wait_with_cancel(1); press('c')

# ============ ROI 讀寫 ============
def save_roi_to_json(data: Dict[str, int], path: str = ROI_JSON_PATH):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_roi_and_monitor_from_json(path: str = ROI_JSON_PATH) -> Tuple[Dict[str,int], int, str]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"找不到 {path}，請先校準。")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    roi = {
        "left": int(data["left"]),
        "top": int(data["top"]),
        "width": int(data["width"]),
        "height": int(data["height"]),
    }
    mon_index = int(data.get("monitor_index", MONITOR_INDEX))
    pack = str(data.get("template_pack", ""))
    return roi, mon_index, pack

# ============ 自動校準（套用解析度包） ============
def auto_calibrate_roi(
    sct: mss.mss,
    templates_root: str,
    prefer_monitor_index: int = 1,
    focus_substr: str = "",
    forced_bbox: Optional[Dict[str, int]] = None
) -> Tuple[int, Dict[str,int]]:
    """
    回傳 (monitor_index, roi_rel)
      - 優先用 forced_bbox（建議給「前景視窗 Client 區域」）
      - 否則若提供 focus_substr，先在該視窗矩形內尋找
      - 否則在每個螢幕搜索
    會根據「當前搜尋區域的寬高」自動選擇樣板解析度包。
    """
    best = {
        "score": -1.0,
        "mon_idx": None,
        "label": "",
        "rect_abs": None,   # (left, top, width, height)
        "pack": ""          # 解析度包名稱
    }

    # 準備搜尋區域
    search_spaces = []
    if forced_bbox:
        search_spaces.append({"type": "bbox", "bbox": forced_bbox, "index": None})
    else:
        win_rect = _get_window_rect_by_title(focus_substr) if focus_substr else None
        if win_rect:
            L, T, R, B = win_rect
            search_spaces.append({"type": "window",
                                  "bbox": {"left": L, "top": T, "width": R-L, "height": B-T},
                                  "index": None})
        else:
            for idx in range(1, len(sct.monitors)):
                m = sct.monitors[idx]
                search_spaces.append({
                    "type": "monitor",
                    "index": idx,
                    "bbox": {"left": m["left"], "top": m["top"], "width": m["width"], "height": m["height"]}
                })

    # 逐區域搜尋
    for space in search_spaces:
        box = space["bbox"]
        frame = np.array(sct.grab(box))
        gray = cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
        H, W = gray.shape[:2]

        # **核心：依目前搜尋區域解析度挑樣板包**
        pack_dir, pack_name = _select_template_pack(templates_root, W, H)
        detector = TemplateDetector(pack_dir, DETECT_THRESHOLD)
        templates = detector.templates

        gui_log(f"[校準] 使用樣板包：{os.path.basename(pack_dir) or pack_name or '(root)'} ；搜尋區域 {W}x{H}")

        for label, tpl0 in templates.items():
            th0, tw0 = tpl0.shape[:2]
            for s in SCALES:
                th = int(max(1, round(th0 * s)))
                tw = int(max(1, round(tw0 * s)))
                if th >= H or tw >= W:
                    continue
                tpl = cv2.resize(
                    tpl0, (tw, th),
                    interpolation=cv2.INTER_AREA if s < 1.0 else cv2.INTER_CUBIC
                )
                score, maxLoc = detector._match_best(gray, tpl)
                if score > best["score"]:
                    x, y = maxLoc
                    cx, cy = x + tw // 2, y + th // 2
                    roi_w = int(tw * ROI_EXPAND)
                    roi_h = int(th * ROI_EXPAND)
                    l = max(0, cx - roi_w // 2)
                    t = max(0, cy - roi_h // 2)
                    r = min(W, l + roi_w)
                    b = min(H, t + roi_h)
                    l, t, roi_w, roi_h = int(l), int(t), int(r - l), int(b - t)

                    # 轉回全域座標
                    L_abs = box["left"] + l
                    T_abs = box["top"] + t

                    # 所在螢幕
                    mon_idx = space.get("index")
                    if mon_idx is None:
                        mon_idx = prefer_monitor_index if (1 <= prefer_monitor_index < len(sct.monitors)) else 1

                    best.update({
                        "score": float(score),
                        "mon_idx": mon_idx,
                        "label": label,
                        "rect_abs": (L_abs, T_abs, roi_w, roi_h),
                        "pack": pack_name,
                    })
                    if best["score"] >= EARLY_STOP_SCORE:
                        break
            if best["score"] >= EARLY_STOP_SCORE:
                break

    if best["rect_abs"] is None or best["score"] < CALIB_MIN_SCORE:
        raise RuntimeError(
            f"自動校準失敗：最高分={best['score']:.3f}，低於門檻 {CALIB_MIN_SCORE:.2f}，"
            "請切到有結果畫面的遊戲視窗後再試（或放入對應解析度樣板）。"
        )

    # 轉成該螢幕的相對 ROI
    mon = sct.monitors[best["mon_idx"]]
    L_abs, T_abs, W_roi, H_roi = best["rect_abs"]
    roi_rel = {
        "left":   L_abs - mon["left"],
        "top":    T_abs - mon["top"],
        "width":  W_roi,
        "height": H_roi,
        "monitor_index": best["mon_idx"],
        "score": best["score"],
        "anchor_label": best["label"],
        "template_pack": best["pack"],  # 記錄使用的樣板包
    }
    return best["mon_idx"], roi_rel

# ============ 主循環（使用校準到的樣板包） ============
def detection_loop(roi_rel: Dict[str, int], mon_index: int, templates_root_abs: str):
    sct = mss.mss()
    try:
        if mon_index >= len(sct.monitors):
            gui_log(f"[警告] 設定的 monitor_index={mon_index} 超出範圍，改用 1")
            mon_index = 1
        mon = sct.monitors[mon_index]
        mon_left, mon_top = mon["left"], mon["top"]

        roi_abs = {
            "left":   mon_left + int(roi_rel["left"]),
            "top":    mon_top  + int(roi_rel["top"]),
            "width":  int(roi_rel["width"]),
            "height": int(roi_rel["height"]),
        }
        gui_log(f"[ROI abs] {roi_abs} (monitor#{mon_index} offset=({mon_left},{mon_top}))")

        # 依 roi.json 指定的 template_pack 決定樣板資料夾
        pack_name = str(roi_rel.get("template_pack", "")).strip()
        if pack_name:
            tpl_dir_abs = os.path.join(templates_root_abs, pack_name)
        else:
            # 無 pack 記錄就用目前 ROI 區域大小挑選
            W, H = roi_abs["width"], roi_abs["height"]
            tpl_dir_abs, _ = _select_template_pack(templates_root_abs, W, H)

        gui_log(f"[偵測] 使用樣板包：{os.path.basename(tpl_dir_abs) or '(root)'}")
        detector = TemplateDetector(tpl_dir_abs, DETECT_THRESHOLD)

        streak = {'win': 0, 'loss': 0, 'draw': 0}
        cooldown_until = 0.0
        draw_count = 0

        # 重武裝控制
        rearm_ref_hash: Optional[np.ndarray] = None
        rearm_label: Optional[str] = None
        rearm_deadline = 0.0

        # === 新增：兩階段狀態 ===
        phase = 1  # 1：累計 draw；2：遇 win/loss 結束，draw 繼續
        gui_log("啟動完成。F12 或 按鈕可隨時停止。偵測中…（第一階段）")

        while True:
            ensure_not_stopped()

            if time.monotonic() < cooldown_until:
                time.sleep(POLL_INTERVAL_SEC)
                continue

            frame_bgra = np.array(sct.grab(roi_abs))
            gray = cv2.cvtColor(frame_bgra, cv2.COLOR_BGRA2GRAY)

            # 尚未重武裝：檢查是否達成場景變化條件
            if rearm_label is not None:
                cur_hash = roi_ahash(gray)
                label_now, score_now = detector.detect(gray)
                changed = (label_now != rearm_label) or (hamming(cur_hash, rearm_ref_hash) >= CHANGE_REARM_HAMMING)
                timeout = time.monotonic() >= rearm_deadline
                if changed or timeout:
                    gui_log(f"[重武裝] changed={changed} timeout={timeout} label_now={label_now} score={score_now:.3f}")
                    rearm_label = None
                    rearm_ref_hash = None
                else:
                    time.sleep(POLL_INTERVAL_SEC)
                    continue

            # 正常偵測
            label, score = detector.detect(gray)

            if label:
                for k in streak.keys():
                    streak[k] = streak[k] + 1 if k == label else 0

                if streak[label] >= CONFIRM_FRAMES:
                    gui_log(f"[觸發] {label} | score={score:.3f} | streak={streak[label]}")
                    rearm_ref_hash = roi_ahash(gray.copy())
                    rearm_label = label
                    rearm_deadline = time.monotonic() + CHANGE_REARM_TIMEOUT_SEC

                    # === 第一階段邏輯：一律執行原本對應腳本；draw 累計，達標後切換第二階段 ===
                    if phase == 1:
                        run_script(label)

                        if label == 'draw':
                            draw_count += 1
                            gui_log(f"[DRAW 累計] {draw_count}/{DRAW_STOP_AT}")
                            if draw_count >= DRAW_STOP_AT:
                                gui_log(f"[完成] 已達 {DRAW_STOP_AT} 次 draw，切換到『第二階段』。")
                                phase = 2
                                # 可視需要，稍微等待結果畫面退場再繼續
                                cooldown_until = time.monotonic() + max(POST_TRIGGER_COOLDOWN_SEC, 1.0)
                        # 第一階段不會因 win/loss 結束；持續偵測

                    else:
                        # === 第二階段邏輯 ===
                        if label == 'win':
                            script_phase2_win_end()
                            gui_log("已在第二階段遇到 WIN，流程結束。")
                            break
                        elif label == 'loss':
                            script_phase2_loss_end()
                            gui_log("已在第二階段遇到 LOSS，流程結束。")
                            break
                        else:  # draw
                            script_phase2_draw()
                            gui_log("第二階段 draw → 繼續偵測直到出現 win/loss。")

                    # 觸發後統一清 streak 與冷卻
                    for k in streak.keys():
                        streak[k] = 0
                    cooldown_until = time.monotonic() + POST_TRIGGER_COOLDOWN_SEC
            else:
                for k in streak.keys():
                    streak[k] = 0

            time.sleep(POLL_INTERVAL_SEC)

        gui_log(f"本次統計：draw（第一階段） = {draw_count}")
        gui_log("已結束。")

    except StopRequested:
        gui_log("偵測到停止請求，中止。")
    except KeyboardInterrupt:
        gui_log("收到 Ctrl+C，中止。")
    finally:
        sct.close()

# ============ GUI ============
_GUI_APP = None

def gui_log(msg: str):
    print(msg)
    if _GUI_APP is not None:
        _GUI_APP.log(msg)

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Auto ROI Detector")
        self.geometry("780x540")
        self.resizable(False, False)

        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        # 控制列
        frm = ttk.Frame(self, padding=10)
        frm.pack(side=tk.TOP, fill=tk.X)

        self.btn_start = ttk.Button(frm, text="開始 (5s)", command=self.on_start)
        self.btn_start.pack(side=tk.LEFT, padx=5)

        self.btn_calib = ttk.Button(frm, text="只校準 (5s)", command=self.on_calibrate_only)
        self.btn_calib.pack(side=tk.LEFT, padx=5)

        self.btn_stop = ttk.Button(frm, text="停止", command=self.on_stop, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        self.lbl_status = ttk.Label(frm, text="狀態：待機")
        self.lbl_status.pack(side=tk.LEFT, padx=12)

        # 參數列
        frm2 = ttk.Frame(self, padding=(10, 0))
        frm2.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(frm2, text="視窗標題包含：").pack(side=tk.LEFT)
        self.entry_title = ttk.Entry(frm2, width=28)
        self.entry_title.insert(0, FOCUS_WINDOW_SUBSTR)
        self.entry_title.pack(side=tk.LEFT, padx=6)

        ttk.Label(frm2, text="最低校準分數：").pack(side=tk.LEFT, padx=(12, 0))
        self.entry_min_score = ttk.Entry(frm2, width=6)
        self.entry_min_score.insert(0, f"{CALIB_MIN_SCORE:.2f}")
        self.entry_min_score.pack(side=tk.LEFT, padx=6)

        # 日誌視窗
        frm3 = ttk.Frame(self, padding=10)
        frm3.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.txt = tk.Text(frm3, height=22, wrap="word")
        self.txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(frm3, command=self.txt.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt.config(yscrollcommand=scroll.set)

        # 工作執行緒
        self.worker = None
        self.mode = None  # "start" or "calib"
        self.countdown_job = None

    def log(self, msg: str):
        def _append():
            self.txt.insert(tk.END, msg + "\n")
            self.txt.see(tk.END)
        self.after(0, _append)

    def set_status(self, text: str):
        self.lbl_status.config(text=f"狀態：{text}")

    def _read_params(self):
        global CALIB_MIN_SCORE
        title = self.entry_title.get().strip()
        try:
            CALIB_MIN_SCORE = float(self.entry_min_score.get().strip())
        except Exception:
            pass
        return title

    def on_start(self):
        if self.worker and self.worker.is_alive():
            return
        _STOP_EVENT.clear()
        self.btn_start.config(state=tk.DISABLED)
        self.btn_calib.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.mode = "start"
        self.set_status("倒數中，請切到遊戲視窗")
        title = self._read_params()
        self.start_with_countdown(title, seconds=5)

    def on_calibrate_only(self):
        if self.worker and self.worker.is_alive():
            return
        _STOP_EVENT.clear()
        self.btn_start.config(state=tk.DISABLED)
        self.btn_calib.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.mode = "calib"
        self.set_status("倒數中，請切到遊戲視窗")
        title = self._read_params()
        self.start_with_countdown(title, seconds=5)

    def on_stop(self):
        _STOP_EVENT.set()
        self.set_status("停止中…")
        self.btn_stop.config(state=tk.DISABLED)

    def start_with_countdown(self, title_filter: str, seconds: int = 5):
        self._countdown(seconds, title_filter)

    def _countdown(self, remain: int, title_filter: str):
        if remain <= 0:
            self.set_status("執行中…")
            self._launch_worker(title_filter)
            return
        self.set_status(f"倒數 {remain}s，請切到遊戲視窗")
        self.countdown_job = self.after(1000, self._countdown, remain - 1, title_filter)

    def _launch_worker(self, title_filter: str):
        def target():
            try:
                set_dpi_awareness()
                templates_root_abs = resource_path(TEMPLATE_DIR)
                sct = mss.mss()

                # 取得前景視窗 Client 區域（視窗模式最準）
                bbox = _get_foreground_client_bbox()
                if bbox:
                    gui_log(f"[校準] 前景視窗 Client 區域：{bbox}")
                else:
                    gui_log("[校準] 取不到前景視窗 Client 區域，將嘗試以標題或全螢幕搜尋。")

                # 若使用者輸入標題，優先用標題鎖定；否則用前景 Client 區域
                forced = None if title_filter else bbox

                # 校準（內部自動選樣板包）
                mon_index, roi_rel = auto_calibrate_roi(
                    sct,
                    templates_root=templates_root_abs,
                    prefer_monitor_index=MONITOR_INDEX,
                    focus_substr=title_filter,
                    forced_bbox=forced
                )
                save_roi_to_json(roi_rel, ROI_JSON_PATH)
                pack_logged = roi_rel.get("template_pack") or "(root/default)"
                gui_log(f"[校準] 完成（monitor #{mon_index}，score={roi_rel['score']:.3f}，anchor={roi_rel['anchor_label']}，pack={pack_logged}）已寫入 {ROI_JSON_PATH}")

                if self.mode == "calib":
                    self.set_status("校準完成")
                    return

                # 進入偵測循環（固定使用同一樣板包）
                detection_loop(roi_rel, mon_index, templates_root_abs)
                self.set_status("已結束")

            except StopRequested:
                gui_log("收到停止，已中止。")
                self.set_status("已停止")
            except Exception as e:
                gui_log(f"[錯誤] {e}")
                self.set_status("錯誤")
                try:
                    # 若失敗且有舊檔則退回舊 roi
                    if os.path.exists(ROI_JSON_PATH) and self.mode != "calib":
                        gui_log("[嘗試] 改用既有 roi.json")
                        roi_rel, mon_index, _ = load_roi_and_monitor_from_json(ROI_JSON_PATH)
                        templates_root_abs = resource_path(TEMPLATE_DIR)
                        detection_loop(roi_rel, mon_index, templates_root_abs)
                        self.set_status("已結束")
                except Exception as e2:
                    gui_log(f"[二次錯誤] {e2}")
            finally:
                self.after(0, self._finish_buttons)

        self.worker = threading.Thread(target=target, daemon=True)
        self.worker.start()

    def _finish_buttons(self):
        self.btn_start.config(state=tk.NORMAL)
        self.btn_calib.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.mode = None

# ============ Console / GUI 入口 ============
def console_main():
    set_dpi_awareness()
    ensure_admin_or_elevate()

    templates_root_abs = resource_path(TEMPLATE_DIR)

    sct = mss.mss()
    try:
        gui_log("[校準] 5 秒後抓取前景視窗 Client 區域，請切到遊戲視窗…")
        for t in range(5, 0, -1):
            gui_log(f"  {t}…")
            time.sleep(1)

        bbox = _get_foreground_client_bbox()
        if bbox:
            gui_log(f"[校準] 前景視窗 Client 區域：{bbox}")
        else:
            gui_log("[校準] 取不到前景視窗 Client 區域，將嘗試以標題或全螢幕搜尋。")

        forced = None if FOCUS_WINDOW_SUBSTR else bbox

        mon_index, roi_rel = auto_calibrate_roi(
            sct,
            templates_root=templates_root_abs,
            prefer_monitor_index=MONITOR_INDEX,
            focus_substr=FOCUS_WINDOW_SUBSTR,
            forced_bbox=forced
        )
        save_roi_to_json(roi_rel, ROI_JSON_PATH)
        pack_logged = roi_rel.get("template_pack") or "(root/default)"
        gui_log(f"[校準] 完成（monitor #{mon_index}，score={roi_rel['score']:.3f}，anchor={roi_rel['anchor_label']}，pack={pack_logged}）已寫入 {ROI_JSON_PATH}")

        detection_loop(roi_rel, mon_index, templates_root_abs)

    except StopRequested:
        gui_log("收到停止，中止。")
    except Exception as e:
        gui_log(f"[錯誤] {e}")
    finally:
        sct.close()

if __name__ == "__main__":
    use_gui = (tk is not None) and ("--nogui" not in sys.argv)

    set_dpi_awareness()
    if REQUIRE_ADMIN:
        ensure_admin_or_elevate()   # ← 先升權，再進入 GUI/Console

    if use_gui:
        _GUI_APP = App()
        gui_log("提示：按下『開始 (5s)』後，切到遊戲視窗。樣板請按視窗解析度放在 templates/寬x高/ 下。")
        _GUI_APP.mainloop()
    else:
        console_main()
