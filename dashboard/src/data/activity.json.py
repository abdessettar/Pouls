"""Activity page data."""

from apple_health.dashboard import Warehouse, activity, emit

emit(activity.build(Warehouse.locate()))
