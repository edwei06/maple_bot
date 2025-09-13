import ctypes
import time
import random
import json
import os
import sys

# =================================================================================
# 0. 載入與選擇設定檔 (全新架構)
# =================================================================================
def load_profiles():
    """載入所有設定檔，如果檔案不存在則建立一個預設的"""
    profiles_filename = 'profiles.json'
    if not os.path.exists(profiles_filename):
        print(f"[警告] 找不到 {profiles_filename}，將建立預設設定檔。")
        default_profiles = {
          "預設設定": {
            "profile_comment": "這是一個預設的設定檔",
            "layer_count": 2,
            "summon_skills": {"place_on_layer": 2, "keys": ["2", "4"]}, # <--- 新增
            "turn_duration_min": 0.1, "turn_duration_max": 0.25,
            "attack_count_min": 2, "attack_count_max": 4,
            "attack_delay_min": 0.4, "attack_delay_max": 0.7,
            "action_delay_min": 0.5, "action_delay_max": 1.0,
            "landing_delay_min": 1.5, "landing_delay_max": 1.8,
            "roaming_delay_min": 0.4, "roaming_delay_max": 0.5,
            "aoe_skill_probability": 0.15, "dash_attack_probability": 0.40,
            "roam_map_probability": 0.25,
            "roaming_path": [{"direction": "right", "dashes": [1, 2]}, {"direction": "left", "dashes": [1, 2]}]
          }
        }
        with open(profiles_filename, 'w', encoding='utf-8') as f:
            json.dump(default_profiles, f, indent=2, ensure_ascii=False)
        return default_profiles
    else:
        with open(profiles_filename, 'r', encoding='utf-8') as f:
            print(f"[資訊] 已成功載入 {profiles_filename}")
            return json.load(f)

def select_profile(profiles):
    """提供選單讓使用者選擇要使用的 Profile"""
    print("\n請選擇要使用的地圖設定 (Profile):")
    profile_names = list(profiles.keys())
    for i, name in enumerate(profile_names):
        print(f"  [{i+1}] {name} ({profiles[name].get('profile_comment', '')})")
    
    choice = -1
    while choice < 1 or choice > len(profile_names):
        try:
            choice = int(input(f"請輸入選擇 [1-{len(profile_names)}]: "))
        except ValueError:
            print("輸入無效，請輸入數字。")
    
    chosen_profile_name = profile_names[choice - 1]
    config = profiles[chosen_profile_name]
    print(f"您已選擇: 【{chosen_profile_name}】")
    return config

# =================================================================================
# 1. 底層 SendInput 結構與函式定義 (保持不變)
# =================================================================================
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
PUL = ctypes.POINTER(ctypes.c_ulong)
class KeyBdInput(ctypes.Structure): _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", PUL)]
class HardwareInput(ctypes.Structure): _fields_ = [("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_short), ("wParamH", ctypes.c_ushort)]
class MouseInput(ctypes.Structure): _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", PUL)]
class Input_I(ctypes.Union): _fields_ = [("ki", KeyBdInput), ("mi", MouseInput), ("hi", HardwareInput)]
class Input(ctypes.Structure): _fields_ = [("type", ctypes.c_ulong), ("ii", Input_I)]
# ... 您原有的 SCAN_CODE_... = 0x... 定義 ...
SCAN_CODE_LEFT=0x4B;SCAN_CODE_RIGHT=0x4D;SCAN_CODE_DOWN=0x50;SCAN_CODE_V=0x2F;SCAN_CODE_SPACE=0x39;SCAN_CODE_D=0x20;SCAN_CODE_G=0x22;SCAN_CODE_A=0x1E;SCAN_CODE_2=0x03;SCAN_CODE_4=0x05

# <--- 更新: 按鍵字串與掃描碼的對照字典 (更完整，含常用數字與字母) ---
SCAN_CODE_MAP = {
    # 數字鍵 1~0（上排）
    '1': 0x02, '2': 0x03, '3': 0x04, '4': 0x05, '5': 0x06,
    '6': 0x07, '7': 0x08, '8': 0x09, '9': 0x0A, '0': 0x0B,

    # 字母鍵（皆為小寫對應；是否大寫由 Shift 狀態決定）
    'a': 0x1E, 'b': 0x30, 'c': 0x2E, 'd': 0x20, 'e': 0x12,
    'f': 0x21, 'g': 0x22, 'h': 0x23, 'i': 0x17, 'j': 0x24,
    'k': 0x25, 'l': 0x26, 'm': 0x32, 'n': 0x31, 'o': 0x18,
    'p': 0x19, 'q': 0x10, 'r': 0x13, 's': 0x1F, 't': 0x14,
    'u': 0x16, 'v': 0x2F, 'w': 0x11, 'x': 0x2D, 'y': 0x15, 'z': 0x2C,

    # 常用控制鍵（保留原有常數若存在；若無以掃描碼直寫）
    'space': 0x39,
    'tab': 0x0F,
    'enter': 0x1C,
    'esc': 0x01,
    'backspace': 0x0E,
    'shift': 0x2A,   # Left Shift
    'ctrl': 0x1D,    # Left Ctrl
    'alt': 0x38,     # Left Alt

    # 為保相容，保留原本使用到的鍵
    '2': 0x03,
    '4': 0x05,
    'v': 0x2F,
    'd': 0x20,
    'g': 0x22,
    'a': 0x1E,
}

def hold_key(scan_code, is_extended=False):
    flags = KEYEVENTF_SCANCODE
    if is_extended: flags |= KEYEVENTF_EXTENDEDKEY
    extra = ctypes.c_ulong(0); ii_ = Input_I(); ii_.ki = KeyBdInput(0, scan_code, flags, 0, ctypes.pointer(extra)); x = Input(ctypes.c_ulong(1), ii_); ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))
def release_key(scan_code, is_extended=False):
    flags = KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP
    if is_extended: flags |= KEYEVENTF_EXTENDEDKEY
    extra = ctypes.c_ulong(0); ii_ = Input_I(); ii_.ki = KeyBdInput(0, scan_code, flags, 0, ctypes.pointer(extra)); x = Input(ctypes.c_ulong(1), ii_); ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))
# =================================================================================
# 2. 組合好的高階動作函式
# =================================================================================

def random_sleep(min_s, max_s):
    time.sleep(random.uniform(min_s, max_s))

def press_key(scan_code, is_extended=False):
    hold_key(scan_code, is_extended)
    random_sleep(0.05, 0.09)
    release_key(scan_code, is_extended)

def turn(direction_scancode, is_extended=False):
    duration = random.uniform(config['turn_duration_min'], config['turn_duration_max'])
    end_time = time.time() + duration
    while time.time() < end_time:
        hold_key(direction_scancode, is_extended)
        time.sleep(0.05)
    release_key(direction_scancode, is_extended)

def double_dash():
    # <--- 新增: 一個獨立的 double_dash 函式，因為跑圖需要重複使用
    press_key(SCAN_CODE_SPACE)
    random_sleep(0.1, 0.2)
    press_key(SCAN_CODE_SPACE)
    random_sleep(0.1, 0.2)
    press_key(SCAN_CODE_SPACE)
    random_sleep(0.1, 0.2)
    press_key(SCAN_CODE_D)
    random_sleep(0.1, 0.2)
    press_key(SCAN_CODE_SPACE)
    random_sleep(0.1, 0.2)

def drop_down():
    print("    - 動作: 向下跳層")
    end_time = time.time() + 0.5
    while time.time() < end_time:
        hold_key(SCAN_CODE_DOWN, is_extended=True)
        time.sleep(0.05)
    press_key(SCAN_CODE_SPACE)
    release_key(SCAN_CODE_DOWN, is_extended=True)

def attempt_aoe_skill():
    if random.random() < config['aoe_skill_probability']:
        skill_to_use = random.choice([SCAN_CODE_A, SCAN_CODE_G])
        skill_char = 'A' if skill_to_use == SCAN_CODE_A else 'G'
        print(f"    - 隨機技能: 嘗試使用技能 {skill_char}")
        press_key(skill_to_use)
        random_sleep(config['action_delay_min'], config['action_delay_max'])

def clear_mobs_routine():
    print("  -> 開始執行清怪流程...")
    first_direction = random.choice([(SCAN_CODE_LEFT, True), (SCAN_CODE_RIGHT, True)])
    second_direction = (SCAN_CODE_RIGHT, True) if first_direction[0] == SCAN_CODE_LEFT else (SCAN_CODE_LEFT, True)
    
    # --- 第一次攻擊 ---
    print(f"    - 轉向 {'左' if first_direction[0] == SCAN_CODE_LEFT else '右'}")
    turn(first_direction[0], first_direction[1])
    # <--- 變更: 攻擊次數改回從設定檔讀取，方便統一管理
    attack_count = random.randint(config['attack_count_min'], config['attack_count_max'])
    print(f"    - 進行 {attack_count} 次攻擊")
    for _ in range(attack_count):
        if random.random() < config['dash_attack_probability']:
            print("      - 隨機動作: 衝刺攻擊!")
            press_key(SCAN_CODE_SPACE)
            random_sleep(0.1, 0.2) # 等待衝刺動畫
        press_key(SCAN_CODE_D)
        random_sleep(config['attack_delay_min'], config['attack_delay_max'])
        attempt_aoe_skill()
        random_sleep(config['attack_delay_min'], config['attack_delay_max'])
        
    # --- 第二次攻擊 ---
    print(f"    - 轉向 {'左' if second_direction[0] == SCAN_CODE_LEFT else '右'}")
    turn(second_direction[0], second_direction[1])
    attack_count = random.randint(config['attack_count_min'], config['attack_count_max'])
    print(f"    - 進行 {attack_count} 次攻擊")
    for _ in range(attack_count):
        if random.random() < config['dash_attack_probability']:
            print("      - 隨機動作: 衝刺攻擊!")
            press_key(SCAN_CODE_SPACE)
            random_sleep(0.2, 0.4)
        press_key(SCAN_CODE_D)
        attempt_aoe_skill()
        random_sleep(config['attack_delay_min'], config['attack_delay_max'])
    print("  -> 清怪流程結束")
# <--- 變更: roam_the_map 現在需要知道當前樓層 ---
def roam_the_map(current_layer):
    """執行跑圖路徑，並根據起始樓層決定後續動作"""
    print("  -> 開始執行【可客製化】的跑圖流程...")
    path = config.get('roaming_path', [])
    
    for i, step in enumerate(path):
        direction = step.get('direction', 'right')
        dashes_config = step.get('dashes', 0)
        dashes_to_perform = 0
        
        if isinstance(dashes_config, list) and len(dashes_config) == 2:
            min_dashes, max_dashes = dashes_config
            dashes_to_perform = random.randint(min_dashes, max_dashes)
            print(f"    - 跑圖步驟 {i+1}: 向 {direction} 執行 {dashes_to_perform} 次衝刺 (隨機自 {dashes_config})")
        elif isinstance(dashes_config, int):
            dashes_to_perform = dashes_config
            print(f"    - 跑圖步驟 {i+1}: 向 {direction} 執行 {dashes_to_perform} 次衝刺 (固定)")

        if direction == 'left':
            turn(SCAN_CODE_LEFT, is_extended=True)
        else:
            turn(SCAN_CODE_RIGHT, is_extended=True)
            
        for _ in range(dashes_to_perform):
            random_sleep(config['roaming_delay_min'], config['roaming_delay_max'])
            double_dash()
        drop_down()
        random_sleep(config['landing_delay_min'], config['landing_delay_max'])
        drop_down()
        random_sleep(config['landing_delay_min'], config['landing_delay_max'])
        drop_down()
        random_sleep(config['landing_delay_min'], config['landing_delay_max'])

    print("  -> 跑圖流程結束，角色已返回第一層。")
    return 1 # 跑圖結束後，角色必定在第一層
def handle_roaming_chance(current_layer): # <--- 關鍵在於這裡增加了 current_layer 參數
    """依機率決定是否跑圖。返回元組 (是否跑圖, 新的樓層)"""
    if random.random() < config.get('roam_map_probability', 0):
        new_layer = roam_the_map(current_layer)
        return (True, new_layer) # 跑圖了，返回 True 和新樓層 1
    return (False, current_layer) # 沒跑圖，返回 False 和原樓層

# =================================================================================
# 3. 主邏輯：三層地圖的無限循環
# =================================================================================


def main():
    global config # 讓 config 成為全域變數，方便各函式取用
    
    # --- 啟動設定 ---
    profiles = load_profiles()
    config = select_profile(profiles)
    current_layer = 1
    layer_count = config.get('layer_count', 1)
    
    print("\n" + "="*40)
    print(" 全自動掛機腳本已啟動 (v5 - 可配置召喚物)")
    # ... (其餘啟動訊息不變) ...
    print("="*40)
    for i in range(5, 0, -1):
        print(f"{i}...")
        time.sleep(1)

    cycle_count = 0
    while True:
        try:
            cycle_count += 1
            print(f"\n===== 第 {cycle_count} 輪循環 | 當前樓層: {current_layer}/{layer_count} =====")
            
            # <--- 新增: 檢查是否要在當前樓層放置召喚物 ---
            summon_info = config.get("summon_skills")
            if summon_info and summon_info.get("place_on_layer") == current_layer:
                print("  -> 執行放置召喚物流程...")
                keys_to_press = summon_info.get("keys", [])
                for key_char in keys_to_press:
                    if key_char in SCAN_CODE_MAP:
                        print(f"    - 放置召喚物: 按下按鍵 '{key_char}'")
                        press_key(SCAN_CODE_MAP[key_char])
                        # 每次按鍵後都加入延遲
                        random_sleep(config['action_delay_min'], config['action_delay_max'])
                    else:
                        print(f"    - [警告] 在設定中找到按鍵 '{key_char}'，但在 SCAN_CODE_MAP 中找不到對應的掃描碼。")
                
                # 放置完畢後，將 place_on_layer 設為一個不可能的值，避免在同一輪循環中重複放置
                # 也可以設計成有冷卻時間的邏輯，但此方法較簡單
                summon_info["place_on_layer"] = -1 


            # --- 通用清怪與跑圖 ---
            clear_mobs_routine()
            roamed, new_layer = handle_roaming_chance(current_layer)
            if roamed:
                current_layer = new_layer
                # 跑圖後，重設召喚物邏輯，以便下一輪可以正常放置
                if config.get("summon_skills"):
                    config["summon_skills"]["place_on_layer"] = profiles[list(profiles.keys())[list(profiles.values()).index(config)]]["summon_skills"]["place_on_layer"]
                random_sleep(1.0, 1.5)
                continue 

            # --- 根據當前樓層決定換層動作 ---
            if current_layer == 1:
                if layer_count > 1:
                    print("  -> [1樓->2樓] 向上跳躍...")
                    press_key(SCAN_CODE_V)
                    current_layer += 1
            elif current_layer == 2:
                if layer_count > 2:
                    print("  -> [2樓->3樓] 向上跳躍...")
                    press_key(SCAN_CODE_V)
                    current_layer += 1
                else: 
                    print("  -> [2樓->1樓] 向下跳躍...")
                    drop_down()
                    current_layer -= 1
            elif current_layer == 3:
                print("  -> [3樓->1樓] 連續向下跳躍...")
                drop_down()
                random_sleep(config['landing_delay_min'], config['landing_delay_max'])
                drop_down()
                current_layer = 1
            
            # 等待角色換層後的落地/動畫時間
            random_sleep(config['landing_delay_min'], config['landing_delay_max'])
            
            # 如果回到了第一層，重設召喚物邏輯
            if current_layer == 1:
                 if config.get("summon_skills"):
                    # 重新從原始 profiles 讀取設定，避免汙染
                    chosen_profile_name = list(profiles.keys())[list(profiles.values()).index(config)]
                    config["summon_skills"]["place_on_layer"] = profiles[chosen_profile_name]["summon_skills"]["place_on_layer"]


        except KeyboardInterrupt:
            print("\n[!] 偵測到 CTRL+C，腳本已安全停止。")
            break
        except Exception as e:
            print(f"\n[!] 腳本因錯誤或安全機制停止: {e}")
            break
if __name__ == "__main__":
    # 為了方便函式取用，將 config 設為全域
    config = {}
    main()