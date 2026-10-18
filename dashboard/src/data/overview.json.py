"""Overview page data: 28-day KPIs, highlights, the days and nights of the window."""

from apple_health.dashboard import Warehouse, emit, overview

emit(overview.build(Warehouse.locate()))
