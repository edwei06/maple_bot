# 常用掃描碼（Set 1）
SCAN_CODE_LEFT   = 0x4B
SCAN_CODE_RIGHT  = 0x4D
SCAN_CODE_DOWN   = 0x50
SCAN_CODE_V      = 0x2F
SCAN_CODE_SPACE  = 0x39
SCAN_CODE_D      = 0x20
SCAN_CODE_G      = 0x22
SCAN_CODE_A      = 0x1E

# 字串鍵位對照表（可擴充；**以小寫為準**）
SCAN_CODE_MAP = {
    # 數字鍵 1~0（上排）
    '1': 0x02, '2': 0x03, '3': 0x04, '4': 0x05, '5': 0x06,
    '6': 0x07, '7': 0x08, '8': 0x09, '9': 0x0A, '0': 0x0B,

    # 字母鍵（小寫對應；是否大寫取決於 Shift 狀態）
    'a': 0x1E, 'b': 0x30, 'c': 0x2E, 'd': 0x20, 'e': 0x12,
    'f': 0x21, 'g': 0x22, 'h': 0x23, 'i': 0x17, 'j': 0x24,
    'k': 0x25, 'l': 0x26, 'm': 0x32, 'n': 0x31, 'o': 0x18,
    'p': 0x19, 'q': 0x10, 'r': 0x13, 's': 0x1F, 't': 0x14,
    'u': 0x16, 'v': 0x2F, 'w': 0x11, 'x': 0x2D, 'y': 0x15, 'z': 0x2C,

    # 控制鍵
    'space': 0x39,
    'tab': 0x0F,
    'enter': 0x1C,
    'esc': 0x01,
    'backspace': 0x0E,
    'shift': 0x2A,
    'ctrl': 0x1D,
    'alt': 0x38,
}


def get_scan_code(key: str) -> int:
    """將任意字串鍵名解析為掃描碼（大小寫不敏感）。
    - 單一英文字母會自動轉為小寫去查表。
    - ' ' 會被視為 'space'。
    解析失敗會拋出 KeyError。
    """
    if key is None:
        raise KeyError("None")
    k = str(key)
    if k == ' ':
        k = 'space'
    k_l = k.lower()
    # 單一字母：大小寫統一
    if len(k) == 1 and k.isalpha():
        k_l = k.lower()
    if k_l in SCAN_CODE_MAP:
        return SCAN_CODE_MAP[k_l]
    raise KeyError(k)