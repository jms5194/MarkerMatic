from .console import Console, Feature
from .behringerx32 import BehringerX32
from .behringerxair import BehringerXAir
from .digico import DiGiCo
from .studervista import StuderVista
from .theatremix import TheatreMix
from .yamaha import Yamaha
from .dmitri import DMitri
from .nadia import Nadia

CONSOLES = {
    "Behringer X32": BehringerX32,
    "Behringer X Air": BehringerXAir,
    "DiGiCo": DiGiCo,
    "Studer Vista": StuderVista,
    "TheatreMix": TheatreMix,
    "Yamaha": Yamaha,
    "Meyer Sound NADIA": Nadia,
    "Meyer Sound D-Mitri": DMitri,
}

__all__ = [
    "Console",
    "CONSOLES",
    "Feature",
    "BehringerX32",
    "BehringerXAir",
    "DiGiCo",
    "StuderVista",
    "TheatreMix",
    "Yamaha",
    "Nadia",
    "DMitri",
]
