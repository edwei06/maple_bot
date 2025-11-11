import time
import random
import json
import copy

from .config.profiles import load_profiles, select_profile
from .core.keys import (
    SCAN_CODE_LEFT, SCAN_CODE_RIGHT, SCAN_CODE_DOWN, SCAN_CODE_V,
    SCAN_CODE_SPACE, SCAN_CODE_D, SCAN_CODE_G, SCAN_CODE_A,
    SCAN_CODE_MAP,
)
from .core.timing import random_sleep, sleep_quick
from .core.input_win import press_key
from .actions.movement import drop_down
from .core.hotkeys import StopRequested
from .strategies import get_strategy  # 新增：策略注入點


def main():
    # 1) 載入與選擇 Profile
    profiles = load_profiles()
    chosen_profile_name, config = select_profile(profiles)

    # 2) 保留一份「預設副本」供重置用（避免在執行中汙染設定）
    config_defaults = json.loads(json.dumps(config))  # 深拷貝

    # 3) 初始化策略（依設定檔動態選擇）
    strategy_name = config.get('strategy', 'default')
    strategy = get_strategy(strategy_name)
    print(f"[策略] 使用: {strategy_name}")

    current_layer = 1
    layer_count = config.get('layer_count', 1)

    print("" + "=" * 40)
    print(" 全自動掛機腳本已啟動 (v6 - 策略化 | 模組化 | F12 即時停止)")
    print("=" * 40)
    for i in range(5, 0, -1):
        print(f"{i}...")
        sleep_quick(1)

    cycle_count = 0
    while True:
        try:
            cycle_count += 1
            print(f"===== 第 {cycle_count} 輪循環 | 當前樓層: {current_layer}/{layer_count} =====")

            # — A) 依樓層放置召喚物（若設定有啟用）
            summon_info = config.get("summon_skills")
            if summon_info and summon_info.get("place_on_layer") == current_layer:
                print("  -> 執行放置召喚物流程...")
                keys_to_press = summon_info.get("keys", [])
                for key_char in keys_to_press:
                    if key_char in SCAN_CODE_MAP:
                        print(f"    - 放置召喚物: 按下按鍵 '{key_char}'")
                        press_key(SCAN_CODE_MAP[key_char])
                        random_sleep(config['action_delay_min'], config['action_delay_max'])
                    else:
                        print(f"    - [警告] 設定中的按鍵 '{key_char}' 未在 SCAN_CODE_MAP 找到。")
                # 避免同輪重複放置
                summon_info["place_on_layer"] = -1

            # — B) 【策略】清怪/跑圖/來回衝刺等客製化流程
            roamed, new_layer = strategy.run(config, current_layer)
            if roamed:
                current_layer = new_layer  # 跑圖結束回到 1 樓
                # 重置召喚物放置樓層回預設
                if config.get("summon_skills") and config_defaults.get("summon_skills"):
                    config["summon_skills"]["place_on_layer"] = config_defaults["summon_skills"].get("place_on_layer", -1)
                random_sleep(1.0, 1.5)
                continue

            # — C) 依樓層移動（上/下樓）
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

            # — D) 落地/動畫等待
            random_sleep(config['landing_delay_min'], config['landing_delay_max'])

            # — E) 回到第一層時重置召喚物放置樓層
            if current_layer == 1 and config.get("summon_skills") and config_defaults.get("summon_skills"):
                config["summon_skills"]["place_on_layer"] = config_defaults["summon_skills"].get("place_on_layer", -1)

        except KeyboardInterrupt:
            print("[!] 偵測到 CTRL+C，腳本已安全停止。")
            break
        except StopRequested:
            print("[!] 偵測到 F12 即時停止，腳本已安全停止。")
            break
        except Exception as e:
            print(f"[!] 腳本因錯誤或安全機制停止: {e}")
            break


if __name__ == "__main__":
    main()