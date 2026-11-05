"""Registro de adaptadores por portal. Para sumar una fuente nueva (Babilonia, etc.):
crear su módulo con una subclase de Adaptador y registrarla aquí."""
from .adondevivir import AdaptadorAdondeVivir
from .base import ESQUEMA, Adaptador
from .urbania import AdaptadorUrbania

ADAPTADORES: dict[str, type[Adaptador]] = {
    "urbania": AdaptadorUrbania,
    "adondevivir": AdaptadorAdondeVivir,
}

__all__ = ["ADAPTADORES", "ESQUEMA", "Adaptador"]
