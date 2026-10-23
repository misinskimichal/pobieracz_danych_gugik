"""Discover source resolutions; never present resampling as a new source accuracy."""
from dataclasses import dataclass
from math import isclose

from .core import SOURCES, ServiceError

HEIGHTS = ('PL-EVRF2007-NH', 'PL-KRON86-NH')
EXTRA_SOURCES = {'NMT': ['https://mapy.geoportal.gov.pl/wss/service/PZGIK/NMT/GRID5/WCS/DigitalTerrainModel']}


@dataclass(frozen=True)
class Variant:
    resource: str
    height: str
    resolution: float
    endpoint: str
    coverage: str

    def as_dict(self):
        return dict(resource=self.resource, height=self.height, resolution=self.resolution,
                    endpoint=self.endpoint, coverage=self.coverage)


def endpoints(resource):
    primary = SOURCES[resource][0]
    # Local test services and custom endpoints are kept local.
    extra = EXTRA_SOURCES.get(resource, []) if 'mapy.geoportal.gov.pl/' in primary else []
    return [primary, *extra]


def choose_variants(variants, requested, preferred_height, strict=False, alternate_height=False):
    choices = [v for v in variants if alternate_height or v.height == preferred_height]
    if requested and strict:
        choices = [v for v in choices if isclose(v.resolution, requested, abs_tol=1e-6)]
    if not choices:
        raise ServiceError('Brak dostępnego wariantu zgodnego z wybraną rozdzielczością i układem wysokościowym')

    def order(variant):
        distance = abs(variant.resolution - requested) if requested else variant.resolution
        return variant.height != preferred_height, distance, variant.resolution, variant.endpoint
    return sorted(choices, key=order)
