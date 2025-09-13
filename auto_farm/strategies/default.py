import random
from typing import Tuple

from ..actions.combat import clear_mobs_routine
from ..actions.roaming import handle_roaming_chance
from .base import BaseStrategy


class DefaultStrategy(BaseStrategy):
    """舊行為：清怪後，以機率跑圖。"""

    def run(self, config: dict, current_layer: int) -> Tuple[bool, int]:
        clear_mobs_routine(config)
        roamed, new_layer = handle_roaming_chance(config, current_layer)
        return roamed, new_layer