from .console import Console, Feature
from .behringerx32 import BehringerX32
from .behringerxair import BehringerXAir
from .digico import DiGiCo
from .studervista import StuderVista
from .yamaha import Yamaha

CONSOLES = {
    "Behringer X32": BehringerX32,
    "Behringer X Air": BehringerXAir,
    "DiGiCo": DiGiCo,
    "Studer Vista": StuderVista,
    "Yamaha": Yamaha,
}

__all__ = [
    "Console",
    "CONSOLES",
    "Feature",
    "BehringerX32",
    "BehringerXAir",
    "DiGiCo",
    "StuderVista",
    "Yamaha",
]
