import time
import random
from .hotkeys import ensure_not_stopped


def _sleep_with_poll(seconds: float, *, poll_interval: float = 0.05):
    """睡眠並以固定頻率輪詢停止鍵 (F12)。"""
    end = time.time() + seconds
    while True:
        ensure_not_stopped()
        remaining = end - time.time()
        if remaining <= 0:
            break
        time.sleep(min(poll_interval, remaining))


def random_sleep(min_s: float, max_s: float, *, poll_interval: float = 0.05):
    """在每次隨機睡眠期間輪詢 F12 以允許隨時停止。"""
    total = random.uniform(min_s, max_s)
    _sleep_with_poll(total, poll_interval=poll_interval)


def sleep_quick(seconds: float, *, poll_interval: float = 0.05):
    """一般睡眠（非隨機），同樣支援 F12 停止輪詢。"""
    _sleep_with_poll(seconds, poll_interval=poll_interval)