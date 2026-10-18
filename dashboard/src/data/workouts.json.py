"""Workouts page data: kinds of workout and every counted session."""

from apple_health.dashboard import Warehouse, emit, workouts

emit(workouts.build(Warehouse.locate()))
