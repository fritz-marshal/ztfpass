"""ztfpass — minimal SkyPortal → ZTF scheduler queue passthrough."""

from .app import create_app

__all__ = ["create_app"]
__version__ = "0.1.0"
