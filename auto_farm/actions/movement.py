import time
import random

from ..core.input_win import hold_key, release_key, press_key
from ..core.timing import random_sleep, sleep_quick
from ..core.keys import (
    SCAN_CODE_LEFT, SCAN_CODE_RIGHT, SCAN_CODE_DOWN, SCAN_CODE_SPACE, SCAN_CODE_D
)


def turn(direction_scancode: int, config: dict, is_extended: bool = False):
    duration = random.uniform(config['turn_duration_min'], config['turn_duration_max'])
    end_time = time.time() + duration
    while time.time() < end_time:
        hold_key(direction_scancode, is_extended)
        sleep_quick(0.05)
    release_key(direction_scancode, is_extended)


def double_dash():
    # 起手普攻，延長按壓
    press_key(SCAN_CODE_D, sleep_min=0.2, sleep_max=1.0)
    random_sleep(0.1, 0.2)
    # 必按 Space #1（短按）
    press_key(SCAN_CODE_SPACE, sleep_min=0.05, sleep_max=0.2)
    random_sleep(0.05, 0.15)
    # 必按 Space #2
    press_key(SCAN_CODE_SPACE)
    random_sleep(0.1, 0.2)
    # 50% 機率 Space #3
    if random.random() < 0.5:
        press_key(SCAN_CODE_SPACE, sleep_min=0.1, sleep_max=0.25)
        random_sleep(0.1, 0.2)
    # 33% 機率 Space #4
    if random.random() < 0.33:
        press_key(SCAN_CODE_SPACE)
        random_sleep(0.1, 0.2)
    # 收尾普攻
    press_key(SCAN_CODE_D, sleep_min=0.2, sleep_max=0.5)
    random_sleep(0.1, 0.2)
    # 最後補一發位移
    press_key(SCAN_CODE_SPACE)
    press_key(SCAN_CODE_D)


def drop_down():
    print("    - 動作: 向下跳層")
    end_time = time.time() + 0.5
    while time.time() < end_time:
        hold_key(SCAN_CODE_DOWN, is_extended=True)
        sleep_quick(0.05)
    press_key(SCAN_CODE_SPACE)
    release_key(SCAN_CODE_DOWN, is_extended=True)