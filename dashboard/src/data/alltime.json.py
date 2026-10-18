"""All time page data: monthly series, years, then and now, records, seasonality."""

from apple_health.dashboard import Warehouse, alltime, emit

emit(alltime.build(Warehouse.locate()))
