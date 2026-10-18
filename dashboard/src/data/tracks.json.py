"""Map tracks: one encoded polyline per route."""

from apple_health.dashboard import Warehouse, emit, places

emit(places.tracks(Warehouse.locate()))
