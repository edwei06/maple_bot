import ctypes

# Windows 虛擬鍵值
VK_F12 = 0x7B

user32 = ctypes.windll.user32

class StopRequested(Exception):
    """在任意輪詢點偵測到停止鍵（F12）時丟出以中止主流程。"""
    pass

# 觸發一次即鎖存，避免誤觸後又繼續執行
_STOP_LATCHED = False

def is_stop_pressed() -> bool:
    global _STOP_LATCHED
    if _STOP_LATCHED:
        return True
    # 高位元 (0x8000) 代表鍵目前為按下狀態
    try:
        state = user32.GetAsyncKeyState(VK_F12)
        if state & 0x8000:
            _STOP_LATCHED = True
            return True
    except Exception:
        # 在極少數環境呼叫失敗時，當作未按下避免誤停
        return False
    return False

def ensure_not_stopped():
    if is_stop_pressed():
        raise StopRequested()