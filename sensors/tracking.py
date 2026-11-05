"""Optional geometry helper for an explicitly measured object bearing and distance.

This utility does not identify a person, infer life, or locate a rescue target. The
SEN0395 serial reader currently exposes raw text and does not provide these inputs.
"""

from __future__ import annotations

import math


def estimate_object_gps(
    origin_lat: float,
    origin_lon: float,
    distance_meters: float,
    bearing_degrees: float,
) -> tuple[float, float]:
    """Estimate an object's coordinate from measured range and bearing only."""
    if not -90 <= origin_lat <= 90 or not -180 <= origin_lon <= 180:
        raise ValueError("Origin coordinates are outside valid latitude/longitude ranges")
    if not math.isfinite(distance_meters) or distance_meters < 0:
        raise ValueError("Distance must be a finite, non-negative measurement")
    if not math.isfinite(bearing_degrees):
        raise ValueError("Bearing must be a finite measurement")

    earth_radius = 6_378_137.0
    lat_rad = math.radians(origin_lat)
    lon_rad = math.radians(origin_lon)
    bearing_rad = math.radians(bearing_degrees % 360)
    angular_distance = distance_meters / earth_radius
    target_lat = math.asin(
        math.sin(lat_rad) * math.cos(angular_distance)
        + math.cos(lat_rad) * math.sin(angular_distance) * math.cos(bearing_rad)
    )
    target_lon = lon_rad + math.atan2(
        math.sin(bearing_rad) * math.sin(angular_distance) * math.cos(lat_rad),
        math.cos(angular_distance) - math.sin(lat_rad) * math.sin(target_lat),
    )
    return round(math.degrees(target_lat), 6), round(math.degrees(target_lon), 6)
