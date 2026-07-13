from .habitaclia import HabitacliaScraper
from .pisos import PisosScraper
from .idealista import IdealistaScraper
from .fotocasa import FotocasaScraper
from .mercadona import MercadonaScraper, build_shopping_consolidado

__all__ = [
    "HabitacliaScraper", "PisosScraper", "IdealistaScraper",
    "FotocasaScraper", "MercadonaScraper", "build_shopping_consolidado",
]
