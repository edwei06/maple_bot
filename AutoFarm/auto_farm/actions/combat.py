import random

from ..core.timing import random_sleep
from ..core.input_win import press_key
from ..core.keys import SCAN_CODE_A, SCAN_CODE_G, SCAN_CODE_SPACE, SCAN_CODE_D, SCAN_CODE_LEFT, SCAN_CODE_RIGHT
from .movement import turn


def attempt_aoe_skill(config: dict):
    if random.random() < config['aoe_skill_probability']:
        skill_to_use = random.choice([SCAN_CODE_A, SCAN_CODE_G])
        skill_char = 'A' if skill_to_use == SCAN_CODE_A else 'G'
        print(f"    - 隨機技能: 嘗試使用技能 {skill_char}")
        press_key(skill_to_use)
        random_sleep(config['action_delay_min'], config['action_delay_max'])


def clear_mobs_routine(config: dict):
    print("  -> 開始執行清怪流程...")

    first_direction = random.choice([(SCAN_CODE_LEFT, True), (SCAN_CODE_RIGHT, True)])
    second_direction = (SCAN_CODE_RIGHT, True) if first_direction[0] == SCAN_CODE_LEFT else (SCAN_CODE_LEFT, True)

    # 第一次攻擊
    print(f"    - 轉向 {'左' if first_direction[0] == SCAN_CODE_LEFT else '右'}")
    turn(first_direction[0], config, is_extended=first_direction[1])

    attack_count = random.randint(config['attack_count_min'], config['attack_count_max'])
    print(f"    - 進行 {attack_count} 次攻擊")
    for _ in range(attack_count):
        if random.random() < config['dash_attack_probability']:
            print("      - 隨機動作: 衝刺攻擊!")
            press_key(SCAN_CODE_SPACE)
            random_sleep(0.1, 0.2)
        press_key(SCAN_CODE_D)
        random_sleep(config['attack_delay_min'], config['attack_delay_max'])
        attempt_aoe_skill(config)
        random_sleep(config['attack_delay_min'], config['attack_delay_max'])

    # 第二次攻擊
    print(f"    - 轉向 {'左' if second_direction[0] == SCAN_CODE_LEFT else '右'}")
    turn(second_direction[0], config, is_extended=second_direction[1])

    attack_count = random.randint(config['attack_count_min'], config['attack_count_max'])
    print(f"    - 進行 {attack_count} 次攻擊")
    for _ in range(attack_count):
        if random.random() < config['dash_attack_probability']:
            print("      - 隨機動作: 衝刺攻擊!")
            press_key(SCAN_CODE_SPACE)
            random_sleep(0.2, 0.4)
        press_key(SCAN_CODE_D)
        attempt_aoe_skill(config)
        random_sleep(config['attack_delay_min'], config['attack_delay_max'])

    print("  -> 清怪流程結束")