from .default import DefaultStrategy
from .dash_loop import DashLoopStrategy

_STRATEGIES = {
    'default': DefaultStrategy(),
    'dash_loop': DashLoopStrategy(),
}


def get_strategy(name: str):
    return _STRATEGIES.get(name, DefaultStrategy())