"""Registro de adaptadores por portal."""
from .adondevivir import AdaptadorAdondeVivir
from .base import ESQUEMA, Adaptador
from .tiktok import AdaptadorTikTok
from .urbania import AdaptadorUrbania
from .babilonia import AdaptadorBabilonia
from .social import AdaptadorSocial

ADAPTADORES: dict[str, type[Adaptador]] = {
    "urbania": AdaptadorUrbania,
    "adondevivir": AdaptadorAdondeVivir,
    "tiktok": AdaptadorTikTok,
    "babilonia": AdaptadorBabilonia,
    "social": AdaptadorSocial,
}

__all__ = ["ADAPTADORES", "ESQUEMA", "Adaptador"]