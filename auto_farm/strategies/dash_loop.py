import random
from typing import Tuple, Union, List

from ..core.timing import random_sleep
from ..core.input_win import press_key
from ..core.keys import SCAN_CODE_LEFT, SCAN_CODE_RIGHT, SCAN_CODE_MAP
from ..actions.movement import turn, double_dash
from .base import BaseStrategy

CountSpec = Union[int, List[int]]


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
    小型地圖：基於 roam 思路做左右往返。
    規則：向某方向連續 **double_dash X 次**，再向反方向 **double_dash Y 次**，如此往復。
    支援在 double_dash 之間「隨機放置放置物/技能鍵」。
    參數於 profiles.json 的 `dash_loop` 區塊設定。
    """

    def run(self, config: dict, current_layer: int) -> Tuple[bool, int]:
        dl = config.get('dash_loop', {})

        # 來回循環數（一次包含右段與左段）
        cycles = int(dl.get('cycles', 4))

        # 每側 double_dash 次數（左右可各自設定；相容 per_side_dashes 作為左右共用）
        right_spec = dl.get('right_double_dashes', dl.get('per_side_dashes', [2, 3]))
        left_spec  = dl.get('left_double_dashes',  dl.get('per_side_dashes', [2, 3]))

        # 節奏控制
        between_dd = dl.get('between_double_dashes_delay', [
            config.get('roaming_delay_min', 0.35),
            config.get('roaming_delay_max', 0.55),
        ])
        between_sides = dl.get('between_sides_delay', [0.3, 0.5])

        # 在 dash 之間隨機放置放置物（可選）
        deploy_cfg = dl.get('deployables')  # 例如 {"keys": ["2","4"], "chance": 0.25, "min_interval_dashes": 2, "press_delay": [0.15,0.25]}
        deploy_cd = 0  # 冷卻（以「double_dash 次數」為單位）

        def maybe_place_deployable():
            nonlocal deploy_cd
            if not deploy_cfg:
                return
            # 讀參數
            keys = [k for k in deploy_cfg.get('keys', []) if k in SCAN_CODE_MAP]
            if not keys:
                return
            chance = float(deploy_cfg.get('chance', 0.0))
            press_delay = deploy_cfg.get('press_delay', [config.get('action_delay_min', 0.4), config.get('action_delay_max', 0.7)])
            min_interval = int(deploy_cfg.get('min_interval_dashes', 0))

            # 冷卻處理
            if deploy_cd > 0:
                deploy_cd -= 1
                return

            # 機率觸發
            if random.random() < chance:
                key = random.choice(keys)
                sc = SCAN_CODE_MAP[key]
                random_sleep(press_delay[0], press_delay[1])
                print(f"    - 在 dash 間插入放置物鍵 '{key}'")
                press_key(sc)
                random_sleep(press_delay[0], press_delay[1])
                deploy_cd = max(min_interval, 0)
            if random.random() < 0.75:
                sc = SCAN_CODE_MAP['I']
                press_key(sc)
                random_sleep(press_delay[0], press_delay[1])
            if random.random() < 0.65:
                sc = SCAN_CODE_MAP['shift']
                press_key(sc)
                random_sleep(press_delay[0], press_delay[1])

        for _ in range(cycles):
            # → 方向
            turn(SCAN_CODE_RIGHT, config, is_extended=True)
            r_times = _count_from(right_spec)
            for _ in range(r_times):
                double_dash()
                maybe_place_deployable()
                random_sleep(between_dd[0], between_dd[1])
            random_sleep(between_sides[0], between_sides[1])

            # ← 方向
            turn(SCAN_CODE_LEFT, config, is_extended=True)
            l_times = _count_from(left_spec)
            for _ in range(l_times):
                double_dash()
                maybe_place_deployable()
                random_sleep(between_dd[0], between_dd[1])
            random_sleep(between_sides[0], between_sides[1])

        # 不變更樓層，也不觸發跑圖
        return False, current_layer