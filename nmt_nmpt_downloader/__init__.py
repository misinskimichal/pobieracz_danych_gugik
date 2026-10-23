"""Pobieranie numerycznych modeli wysokościowych GUGiK."""


def classFactory(iface):
    from .plugin import TerrainPlugin
    return TerrainPlugin(iface)
