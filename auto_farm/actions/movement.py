import time
import random

from ..core.input_win import hold_key, release_key, press_key
from ..core.timing import random_sleep
from ..core.keys import (
    SCAN_CODE_LEFT, SCAN_CODE_RIGHT, SCAN_CODE_DOWN, SCAN_CODE_SPACE, SCAN_CODE_D
)


def turn(direction_scancode: int, config: dict, is_extended: bool = False):
    duration = random.uniform(config['turn_duration_min'], config['turn_duration_max'])
    end_time = time.time() + duration
    while time.time() < end_time:
        hold_key(direction_scancode, is_extended)
        time.sleep(0.05)
    release_key(direction_scancode, is_extended)


def double_dash():
    # 多段衝刺（沿用原先節奏）
    press_key(SCAN_CODE_D)
    random_sleep(0.1, 0.2)
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