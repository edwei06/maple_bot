import random
from typing import Tuple, Union

from ..core.timing import random_sleep
from ..core.keys import SCAN_CODE_LEFT, SCAN_CODE_RIGHT
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
    參數在 profiles.json 的 `dash_loop` 區塊設定。
    """

    def run(self, config: dict, current_layer: int) -> Tuple[bool, int]:
        dl = config.get('dash_loop', {})

        # 迭代次數（一次包含→方向與←方向各一段）
        cycles = int(dl.get('cycles', 4))

        # 每側 double_dash 次數（可分別設定，也相容舊版 per_side_dashes）
        right_spec = dl.get('right_double_dashes', dl.get('per_side_dashes', [2, 3]))
        left_spec  = dl.get('left_double_dashes',  dl.get('per_side_dashes', [2, 3]))

        # 每次 double_dash 之間的等待；預設沿用 roaming 的 delay 當作直覺落點
        between_dd = dl.get('between_double_dashes_delay', [
            config.get('roaming_delay_min', 0.35),
            config.get('roaming_delay_max', 0.55),
        ])
        # 左右切換之間的等待
        between_sides = dl.get('between_sides_delay', [0.3, 0.5])

        for _ in range(cycles):
            # → 方向
            turn(SCAN_CODE_RIGHT, config, is_extended=True)
            r_times = _count_from(right_spec)
            for _ in range(r_times):
                double_dash()
                random_sleep(between_dd[0], between_dd[1])
            random_sleep(between_sides[0], between_sides[1])

            # ← 方向
            turn(SCAN_CODE_LEFT, config, is_extended=True)
            l_times = _count_from(left_spec)
            for _ in range(l_times):
                double_dash()
                random_sleep(between_dd[0], between_dd[1])
            random_sleep(between_sides[0], between_sides[1])

        # 不變更樓層，也不觸發跑圖
        return False, current_layer