from abc import ABC, abstractmethod
from typing import Tuple

class BaseStrategy(ABC):
    """所有策略皆需實作 run()，回傳 (roamed, new_layer)。"""

    @abstractmethod
    def run(self, config: dict, current_layer: int) -> Tuple[bool, int]:
        raise NotImplementedError