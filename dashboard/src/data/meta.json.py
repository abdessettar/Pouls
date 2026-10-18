"""Site metadata (data-through date, windows, first days)."""

from apple_health.dashboard import Warehouse, emit, meta

emit(meta.build(Warehouse.locate()))
