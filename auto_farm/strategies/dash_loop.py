import random
from typing import Tuple, Union, List, Dict

from ..core.timing import random_sleep
from ..core.keys import SCAN_CODE_LEFT, SCAN_CODE_RIGHT, get_scan_code
from ..core.input_win import press_key
from ..actions.movement import turn, double_dash
from .base import BaseStrategy

CountSpec = Union[int, list]


def _count_from(spec: CountSpec, default_min: int = 2, default_max: int = 3) -> int:
    """將整數或 [min, max] 轉換為實際次數。"""
    if isinstance(spec, list) and len(spec) == 2:
        return random.randint(int(spec[0]), int(spec[1]))
    try:
        return int(spec)
    except Exception:
        return random.randint(default_min, default_max)


class DashLoopStrategy(BaseStrategy):
    """
    小型地圖用：**以 roam_the_map 的思路**做左右往返，但不做下落與跑圖。
    規則：向某方向連續 **double_dash X 次**，再向反方向 **double_dash Y 次**，如此往復。
    並在 double_dash 之後，依設定機率插入「放置物/額外鍵」。
    """

    def __init__(self):
        # 追蹤 deployables 的間隔冷卻：以 double_dash 次數計
        self._dd_since_last_deploy = 9999

    def run(self, config: dict, current_layer: int) -> Tuple[bool, int]:
        dl = config.get('dash_loop', {})

        cycles = int(dl.get('cycles', 4))
        right_spec = dl.get('right_double_dashes', dl.get('per_side_dashes', [2, 3]))
        left_spec  = dl.get('left_double_dashes',  dl.get('per_side_dashes', [2, 3]))

        between_dd = dl.get('between_double_dashes_delay', [
            config.get('roaming_delay_min', 0.35),
            config.get('roaming_delay_max', 0.55),
        ])
        between_sides = dl.get('between_sides_delay', [0.3, 0.5])

        for _ in range(cycles):
            # → 方向
            turn(SCAN_CODE_RIGHT, config, is_extended=True)
            r_times = _count_from(right_spec)
            for _ in range(r_times):
                double_dash()
                self.maybe_place_deployable(config)
                random_sleep(between_dd[0], between_dd[1])
            random_sleep(between_sides[0], between_sides[1])

            # ← 方向
            turn(SCAN_CODE_LEFT, config, is_extended=True)
            l_times = _count_from(left_spec)
            for _ in range(l_times):
                double_dash()
                self.maybe_place_deployable(config)
                random_sleep(between_dd[0], between_dd[1])
            random_sleep(between_sides[0], between_sides[1])

        # 不變更樓層，也不觸發跑圖
        return False, current_layer

    # —— 新增：在 double_dash 之後，隨機放置物或按自訂鍵 ——
    def maybe_place_deployable(self, config: dict):
        dl = config.get('dash_loop', {})
        deploy = dl.get('deployables')  # {keys: [...], chance: 0.25, min_interval_dashes: 2, press_delay: [0.15,0.25]}
        rand_keys: List[Dict] = dl.get('random_keys', [])  # 可選：[{"key":"i","chance":0.75}]

        # 1) deployables：以 double_dash 次數為冷卻單位
        if deploy:
            keys = deploy.get('keys', [])
            chance = float(deploy.get('chance', 0.0))
            min_gap = int(deploy.get('min_interval_dashes', 0))
            press_delay = deploy.get('press_delay', [0.15, 0.25])

            if self._dd_since_last_deploy >= min_gap and keys:
                if random.random() < chance:
                    key = random.choice(keys)
                    try:
                        sc = get_scan_code(key)
                        press_key(sc)
                        random_sleep(press_delay[0], press_delay[1])
                        self._dd_since_last_deploy = 0
                    except Exception as e:
                        print(f"[deployables] 忽略未知鍵 '{key}': {e}")
                else:
                    self._dd_since_last_deploy += 1
            else:
                self._dd_since_last_deploy += 1
        else:
            # 若未設定 deployables，計數器持續遞增即可
            self._dd_since_last_deploy += 1

        # 2) 額外隨機鍵（不受 deploy 冷卻限制；逐鍵獨立機率）
        for item in rand_keys:
            try:
                key = item.get('key')
                prob = float(item.get('chance', 0))
                if prob > 0 and random.random() < prob:
                    sc = get_scan_code(key)
                    press_key(sc)
                    # 若 item 內含自定延遲使用之；否則沿用 deployables 的 press_delay 或預設
                    pd = item.get('press_delay') or deploy.get('press_delay') if deploy else [0.12, 0.2]
                    random_sleep(pd[0], pd[1])
            except Exception as e:
                print(f"[random_keys] 忽略未知鍵 '{item}': {e}")