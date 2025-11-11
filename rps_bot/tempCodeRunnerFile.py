import os
import sys
import json
import time
import random
import ctypes
from typing import Dict, Tuple, Optional

# ===== 相依套件 =====
# pip install mss opencv-python numpy
import mss
import cv2
import numpy as np

# ===== 參數 =====
TEMPLATE_DIR = "templates"
ROI_JSON = "roi.json"
DETECT_THRESHOLD = 0.85
MONITOR_INDEX = 1
POLL_INTERVAL_SEC = 0.03

# 觸發條件
CONFIRM_FRAMES = 6                 # 同一標籤連續命中幀數才觸發
POST_TRIGGER_COOLDOWN_SEC = 1   # 很短的冷卻，只為避免同一批幀重複觸發

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
kernel32 = ctypes.windll.kernel32

class StopRequested(Exception):
    pass

_STOP_LATCHED = False
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
    if is_stop_pressed():
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
            print("[警告] 嘗試提權失敗，將以目前權限繼續。")
    except Exception:
        print("[警告] 提權過程出錯，將以目前權限繼續。")

# =================================================================================
# 1) 底層 SendInput 結構與函式定義
# =================================================================================
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
    """按一下指定鍵名（使用掃描碼）；key 例如 'c','enter','left','down'。"""
    key_l = key.lower()
    if key_l not in SCAN_CODE_MAP:
        print(f"[警告] 未知鍵名：{key}")
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
    """可中斷等待（支援 F12 停止）。"""
    deadline = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < deadline:
        ensure_not_stopped()
        time.sleep(0.01)

# =================================================================================
# 2) 視窗焦點搶回（可選）
# =================================================================================
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
                # 置前顯示
                user32.ShowWindow(hwnd, 5)  # SW_SHOW
                user32.SetForegroundWindow(hwnd)
                # 輔助 BringToTop
                user32.BringWindowToTop(hwnd)
                print(f"[焦點] 已嘗試聚焦視窗：{title}")
                return
    except Exception as e:
        print(f"[焦點] 聚焦失敗：{e}")

# =================================================================================
# 3) 影像偵測（模板比對）
# =================================================================================
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

    def detect(self, gray: np.ndarray) -> Tuple[str, float]:
        best_label, best_score = "", -1.0
        for label, tpl in self.templates.items():
            th, tw = tpl.shape[:2]
            H, W = gray.shape[:2]
            if H < th or W < tw:
                continue
            res = cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            if max_val > best_score:
                best_score = float(max_val)
                best_label = label
        if best_score >= self.threshold:
            return best_label, best_score
        return "", best_score

# =================================================================================
# 4) ROI 雜湊/場景變化判定
# =================================================================================
def roi_ahash(gray: np.ndarray) -> np.ndarray:
    """8x8 平均雜湊，回傳 64 個 boolean 的一維陣列。"""
    small = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA)
    avg = small.mean()
    bits = (small > avg).astype(np.uint8).reshape(-1)
    return bits

def hamming(a: np.ndarray, b: np.ndarray) -> int:
    if a is None or b is None:
        return 9999
    return int(np.bitwise_xor(a, b).sum())

# =================================================================================
# 5) 三種腳本（使用 press/press_times）
# =================================================================================
def script_draw():
    focus_target_window_if_needed()
    wait_with_cancel(2.0); press('c')

def script_loss():
    focus_target_window_if_needed()
    wait_with_cancel(1.0); press('c')
    wait_with_cancel(0.8); press('c')
    wait_with_cancel(1); press('down')
    wait_with_cancel(0.8); press('c')
    wait_with_cancel(0.8); press_times('left', 2)
    wait_with_cancel(0.8); press('enter')
    wait_with_cancel(0.8); press('c')

def script_win():
    focus_target_window_if_needed()
    wait_with_cancel(1.0); press('down')
    wait_with_cancel(0.8); press('c')
    wait_with_cancel(0.8); press_times('left', 2)
    wait_with_cancel(0.8); press('enter')
    wait_with_cancel(0.8); press('c')
    wait_with_cancel(0.8); press('c')
    wait_with_cancel(1); press('down')
    wait_with_cancel(0.8); press('c')
    wait_with_cancel(0.8); press_times('left', 2)
    wait_with_cancel(0.8); press('enter')
    wait_with_cancel(0.8); press('c')

def run_script(label: str):
    if label == 'draw':
        script_draw()
    elif label == 'loss':
        script_loss()
    elif label == 'win':
        script_win()

# =================================================================================
# 6) 主流程
# =================================================================================
def load_roi_from_json() -> Dict[str, int]:
    if not os.path.exists(ROI_JSON):
        raise FileNotFoundError(f"找不到 {ROI_JSON}，請先用校準工具產生。")
    with open(ROI_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {
        "left": int(data["left"]),
        "top": int(data["top"]),
        "width": int(data["width"]),
        "height": int(data["height"]),
    }

def main():
    ensure_admin_or_elevate()

    roi_rel = load_roi_from_json()
    print(f"[ROI] {roi_rel}")

    sct = mss.mss()
    if MONITOR_INDEX >= len(sct.monitors):
        print(f"[警告] MONITOR_INDEX={MONITOR_INDEX} 超出範圍，改用 1")
    mon = sct.monitors[MONITOR_INDEX if MONITOR_INDEX < len(sct.monitors) else 1]
    mon_left, mon_top = mon["left"], mon["top"]

    roi_abs = {
        "left":   mon_left + roi_rel["left"],
        "top":    mon_top  + roi_rel["top"],
        "width":  roi_rel["width"],
        "height": roi_rel["height"],
    }
    print(f"[ROI abs] {roi_abs} (monitor#{MONITOR_INDEX} offset=({mon_left},{mon_top}))")

    detector = TemplateDetector(TEMPLATE_DIR, DETECT_THRESHOLD)

    # 連續幀確認
    streak = {'win': 0, 'loss': 0, 'draw': 0}
    cooldown_until = 0.0
    draw_count = 0

    # ★ 場景變化 rearm 狀態
    rearm_ref_hash: Optional[np.ndarray] = None
    rearm_label: Optional[str] = None
    rearm_deadline = 0.0

    print("啟動完成。F12 可隨時停止。偵測中…")
    try:
        while True:
            ensure_not_stopped()

            # 觸發後短冷卻
            if time.monotonic() < cooldown_until:
                time.sleep(POLL_INTERVAL_SEC)
                continue

            frame_bgra = np.array(sct.grab(roi_abs))
            gray = cv2.cvtColor(frame_bgra, cv2.COLOR_BGRA2GRAY)

            # ★ 若尚未重武裝，檢查是否達成場景變化條件
            if rearm_label is not None:
                cur_hash = roi_ahash(gray)
                # 只要標籤改變或雜湊差異達標，或超時，就重武裝
                label_now, score_now = detector.detect(gray)
                changed = (label_now != rearm_label) or (hamming(cur_hash, rearm_ref_hash) >= CHANGE_REARM_HAMMING)
                timeout = time.monotonic() >= rearm_deadline
                if changed or timeout:
                    print(f"[重武裝] changed={changed} timeout={timeout} label_now={label_now} score={score_now:.3f}")
                    rearm_label = None
                    rearm_ref_hash = None
                else:
                    time.sleep(POLL_INTERVAL_SEC)
                    continue  # 還沒變化 -> 不觸發、不計數

            # 正常偵測流程
            label, score = detector.detect(gray)

            if label:
                for k in streak.keys():
                    streak[k] = streak[k] + 1 if k == label else 0

                if streak[label] >= CONFIRM_FRAMES:
                    print(f"[觸發] {label} | score={score:.3f} | streak={streak[label]}")
                    # 觸發前記錄參考雜湊，用於「場景變化 rearm」
                    rearm_ref_hash = roi_ahash(gray.copy())
                    rearm_label = label
                    rearm_deadline = time.monotonic() + CHANGE_REARM_TIMEOUT_SEC

                    run_script(label)

                    if label == 'draw':
                        draw_count += 1
                        print(f"[DRAW 累計] {draw_count}/{DRAW_STOP_AT}")
                        if draw_count >= DRAW_STOP_AT:
                            print(f"[完成] 已達 {DRAW_STOP_AT} 次 draw，結束程式。")
                            break

                    # 重置連續幀計數並進入短冷卻
                    for k in streak.keys():
                        streak[k] = 0
                    cooldown_until = time.monotonic() + POST_TRIGGER_COOLDOWN_SEC

            else:
                for k in streak.keys():
                    streak[k] = 0

            time.sleep(POLL_INTERVAL_SEC)

    except StopRequested:
        print("偵測到 F12，中止。")
    except KeyboardInterrupt:
        print("收到 Ctrl+C，中止。")
    finally:
        sct.close()
        print(f"本次統計：draw = {draw_count}")
        print("已結束。")

if __name__ == "__main__":
    main()
