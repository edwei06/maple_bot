import os
import json


def load_profiles():
    """載入所有設定檔，如果檔案不存在則建立一個預設的"""
    profiles_filename = 'profiles.json'
    if not os.path.exists(profiles_filename):
        print(f"[警告] 找不到 {profiles_filename}，將建立預設設定檔。")
        default_profiles = {
            # ——— 範例1：一般地圖 ─ 預設策略（清怪 + 機率跑圖） ———
            "預設設定": {
                "profile_comment": "這是一個預設的設定檔",
                "strategy": "default",              # ← 新增：策略名稱
                "layer_count": 2,
                "summon_skills": {"place_on_layer": 2, "keys": ["2", "4"]},

                # 移動/戰鬥參數（供 movement/combat 使用）
                "turn_duration_min": 0.1, "turn_duration_max": 0.25,
                "attack_count_min": 2, "attack_count_max": 4,
                "attack_delay_min": 0.4, "attack_delay_max": 0.7,
                "action_delay_min": 0.5, "action_delay_max": 1.0,
                "landing_delay_min": 1.5, "landing_delay_max": 1.8,
                "roaming_delay_min": 0.4, "roaming_delay_max": 0.5,
                "aoe_skill_probability": 0.15, "dash_attack_probability": 0.40,

                # 跑圖機率與路線（供 default 策略用）
                "roam_map_probability": 0.25,
                "roaming_path": [
                    {"direction": "right", "dashes": [1, 2]},
                    {"direction": "left",  "dashes": [1, 2]},
                ],
            },

            # ——— 範例2：小型地圖 ─ Dash Loop 策略（左右來回衝刺清怪） ———
            "小圖-來回衝刺": {
                "profile_comment": "小地圖，只靠 double dash 來回清怪，不跑圖與清怪流程。",
                "strategy": "dash_loop",             # ← 使用 ping-pong 雙衝策略
                "layer_count": 1,

                # 仍可選擇是否在特定樓層放置召喚物（只有 1 樓時可設 -1 代表不放）
                "summon_skills": {"place_on_layer": 1, "keys": ["2"]},

                # Dash Loop 參數（雙衝次數 X / Y 與節奏）
                "dash_loop": {
                    "cycles": 6,                          # 來回循環次數
                    "right_double_dashes": [2, 3],        # 往右連續 double_dash 次數（範圍或整數）
                    "left_double_dashes":  [2, 3],        # 往左連續 double_dash 次數（範圍或整數）
                    "between_double_dashes_delay": [0.35, 0.55], # 每次 double_dash 間的延遲
                    "between_sides_delay": [0.3, 0.5],     # 左右切換之間的延遲

                    # 新增：在 dash 之間隨機插入「放置物/技能鍵」
                    "deployables": {
                        "keys": ["2", "4"],            # 可用的放置鍵（必須在 SCAN_CODE_MAP 中）
                        "chance": 0.25,                 # 每個 double_dash 後觸發的機率（0~1）
                        "min_interval_dashes": 2,       # 兩次觸發之間至少間隔幾個 double_dash
                        "press_delay": [0.15, 0.25]     # 觸發後按鍵的延遲區間
                    }
                },

                # turn() 與落地等待等仍沿用共用參數
                "turn_duration_min": 0.08, "turn_duration_max": 0.18,
                "action_delay_min": 0.45, "action_delay_max": 0.7,
                "landing_delay_min": 0.9,  "landing_delay_max": 1.2,
            },
        }
        with open(profiles_filename, 'w', encoding='utf-8') as f:
            json.dump(default_profiles, f, indent=2, ensure_ascii=False)
        return default_profiles
    else:
        with open(profiles_filename, 'r', encoding='utf-8') as f:
            print(f"[資訊] 已成功載入 {profiles_filename}")
            return json.load(f)


def select_profile(profiles):
    """提供選單讓使用者選擇要使用的 Profile，回傳 (name, config)"""
    print("請選擇要使用的地圖設定 (Profile):")
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
    return chosen_profile_name, config