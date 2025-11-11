import random

from ..core.timing import random_sleep
from ..core.keys import SCAN_CODE_LEFT, SCAN_CODE_RIGHT
from .movement import turn, double_dash, drop_down


def roam_the_map(config: dict, current_layer: int) -> int:
    """執行跑圖路徑，並根據起始樓層決定後續動作；結束後回到第 1 層"""
    print("  -> 開始執行【可客製化】的跑圖流程...")
    path = config.get('roaming_path', [])

    for i, step in enumerate(path):
        direction = step.get('direction', 'right')
        dashes_config = step.get('dashes', 0)

        if isinstance(dashes_config, list) and len(dashes_config) == 2:
            min_dashes, max_dashes = dashes_config
            dashes_to_perform = random.randint(min_dashes, max_dashes)
            print(f"    - 跑圖步驟 {i+1}: 向 {direction} 執行 {dashes_to_perform} 次衝刺 (隨機自 {dashes_config})")
        elif isinstance(dashes_config, int):
            dashes_to_perform = dashes_config
            print(f"    - 跑圖步驟 {i+1}: 向 {direction} 執行 {dashes_to_perform} 次衝刺 (固定)")
        else:
            dashes_to_perform = 0

        if direction == 'left':
            turn(SCAN_CODE_LEFT, config, is_extended=True)
        else:
            turn(SCAN_CODE_RIGHT, config, is_extended=True)

        for _ in range(dashes_to_perform):
            random_sleep(config['roaming_delay_min'], config['roaming_delay_max'])
            double_dash()

        # 多次落層與落地等待（沿用原行為）
        drop_down()
        random_sleep(config['landing_delay_min'], config['landing_delay_max'])
        drop_down()
        random_sleep(config['landing_delay_min'], config['landing_delay_max'])
        drop_down()
        random_sleep(config['landing_delay_min'], config['landing_delay_max'])

    print("  -> 跑圖流程結束，角色已返回第一層。")
    return 1


def handle_roaming_chance(config: dict, current_layer: int):
    """依機率決定是否跑圖。返回 (是否跑圖, 新的樓層)"""
    if random.random() < config.get('roam_map_probability', 0):
        new_layer = roam_the_map(config, current_layer)
        return True, new_layer
    return False, current_layer