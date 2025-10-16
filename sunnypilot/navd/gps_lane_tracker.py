"""
GPS-based lane position tracking for validation and testing.

This module provides an alternative lane position estimation method using GPS
and map data, intended for testing and validation against model-based detection.

IMPORTANT: This is currently in OBSERVATION MODE ONLY. The GPS tracker runs in
parallel with the model but does NOT control lane positioning decisions.
"""

from __future__ import annotations
import math
import numpy as np
from typing import Optional, Tuple, List
from dataclasses import dataclass

from openpilot.common.swaglog import cloudlog
from openpilot.sunnypilot.navd.helpers import Coordinate, LanePosition


# Standard lane width assumptions (meters)
LANE_WIDTH_HIGHWAY_US = 3.7  # 12 feet - US Interstate/Highway
LANE_WIDTH_URBAN_US = 3.3    # 11 feet - US Urban arterial
LANE_WIDTH_DEFAULT = 3.5      # Default assumption

# GPS accuracy thresholds for confidence calculation
GPS_ACCURACY_EXCELLENT = 2.0  # <2m: High confidence
GPS_ACCURACY_GOOD = 5.0       # 2-5m: Medium confidence
GPS_ACCURACY_POOR = 10.0      # 5-10m: Low confidence
# >10m: Very low confidence


@dataclass
class RoadSegment:
    """Represents a segment of the route with geometry and lane info."""
    start: Coordinate
    end: Coordinate
    lane_count: int
    road_classes: List[str]

    def length(self) -> float:
        """Calculate segment length."""
        return self.start.distance_to(self.end)

    def is_highway(self) -> bool:
        """Check if segment is a highway/freeway."""
        highway_classes = {"motorway", "trunk", "highway", "freeway"}
        return bool(set(self.road_classes) & highway_classes)


class GPSLaneTracker:
    """
    Track lane position using GPS + map data.

    This tracker calculates lateral offset from the road centerline and
    estimates which lane the vehicle is in based on that offset and the
    number of lanes on the road.

    NOTE: Currently in OBSERVATION MODE - does not control lane positioning.
    """

    def __init__(self):
        self.route_segments: List[RoadSegment] = []
        self.observation_mode = True  # LOCKED for testing phase
        self.last_segment_index = 0  # Cache for faster segment lookup

        cloudlog.info("navd: GPS lane tracker initialized (OBSERVATION MODE)")

    def update_from_route(self, route_manager) -> None:
        """
        Extract route geometry and lane data from route manager.

        Args:
            route_manager: RouteManager instance with active route
        """
        if not route_manager.active or not route_manager.geometry:
            self.route_segments = []
            return

        # Build segments from route geometry
        self.route_segments = []
        geometry = route_manager.geometry

        # Extract lane count from maneuvers (with fallback to estimation)
        for i in range(len(geometry) - 1):
            # Get lane count and road classes from nearest maneuver
            lane_count, road_classes = self._get_lane_data_from_maneuvers(route_manager, i)

            segment = RoadSegment(
                start=geometry[i],
                end=geometry[i + 1],
                lane_count=lane_count,
                road_classes=road_classes
            )
            self.route_segments.append(segment)

    def _get_lane_data_from_maneuvers(self, route_manager, segment_idx: int) -> Tuple[int, List[str]]:
        """
        Get lane count and road classes from maneuvers for a route segment.

        Extracts actual lane count from Mapbox intersection data when available,
        falls back to estimation based on road type.

        Args:
            route_manager: RouteManager instance with maneuvers
            segment_idx: Index of the geometry segment

        Returns:
            Tuple of (lane_count, road_classes)
        """
        # Find closest maneuver to this segment (by index approximation)
        # Segments and maneuvers don't have 1:1 correspondence, so we estimate
        if not route_manager.maneuvers:
            return 2, []  # Default fallback

        # Use first maneuver as default (departure point has lane info)
        closest_maneuver = route_manager.maneuvers[0]

        # Try to find a better match if we have multiple maneuvers
        if len(route_manager.maneuvers) > 1:
            # Estimate which maneuver is closest to this segment
            segment_ratio = segment_idx / max(1, len(route_manager.geometry) - 1)
            maneuver_idx = min(
                int(segment_ratio * len(route_manager.maneuvers)),
                len(route_manager.maneuvers) - 1
            )
            closest_maneuver = route_manager.maneuvers[maneuver_idx]

        # Extract lane count - use actual data if available, otherwise estimate
        lane_count = closest_maneuver.lane_count
        if lane_count is None:
            # Fallback to estimation based on road type
            if closest_maneuver.road_classes:
                highway_classes = {"motorway", "trunk", "highway", "freeway"}
                if set(closest_maneuver.road_classes) & highway_classes:
                    lane_count = 3  # Assume 3 lanes for highways
                else:
                    lane_count = 2  # Default to 2 lanes for other roads
            else:
                lane_count = 2  # Ultimate fallback

        # Extract road classes
        road_classes = closest_maneuver.road_classes if closest_maneuver.road_classes else []

        return lane_count, road_classes

    def calculate_lane_position(
        self,
        gps_position: Coordinate,
        heading: float,
        gps_accuracy: float = 5.0
    ) -> Tuple[LanePosition, float, float]:
        """
        Calculate lane position from GPS lateral offset.

        Args:
            gps_position: Current GPS position
            heading: Current vehicle heading in degrees
            gps_accuracy: GPS position accuracy in meters

        Returns:
            Tuple of (LanePosition, confidence, lateral_offset_meters)
            - LanePosition: Estimated lane (LEFT/MIDDLE/RIGHT/UNKNOWN)
            - confidence: 0.0-1.0 confidence score
            - lateral_offset: Perpendicular distance from centerline (meters)
                             Negative = left of center, Positive = right of center
        """
        if not self.route_segments:
            return LanePosition.UNKNOWN, 0.0, 0.0

        # 1. Find closest road segment
        segment, segment_distance = self._find_closest_segment(gps_position)

        if segment is None:
            return LanePosition.UNKNOWN, 0.0, 0.0

        # 2. Calculate lateral offset from road centerline
        lateral_offset = self._calculate_lateral_offset(gps_position, segment)

        # 3. Estimate lane from offset and lane count
        lane_position = self._estimate_lane_from_offset(lateral_offset, segment.lane_count)

        # 4. Calculate confidence based on GPS accuracy and road type
        confidence = self._calculate_confidence(
            gps_accuracy,
            segment_distance,
            segment.lane_count,
            segment.is_highway()
        )

        return lane_position, confidence, lateral_offset

    def _find_closest_segment(self, position: Coordinate) -> Tuple[Optional[RoadSegment], float]:
        """
        Find closest route segment to current position.

        Returns:
            Tuple of (segment, distance_to_segment)
        """
        if not self.route_segments:
            return None, float('inf')

        # Start search from last known segment (temporal locality)
        search_start = max(0, self.last_segment_index - 5)
        search_end = min(len(self.route_segments), self.last_segment_index + 10)

        closest_segment = None
        closest_distance = float('inf')

        for i in range(search_start, search_end):
            segment = self.route_segments[i]
            distance = self._point_to_segment_distance(position, segment)

            if distance < closest_distance:
                closest_distance = distance
                closest_segment = segment
                self.last_segment_index = i

        # If we didn't find a close segment, search all segments
        if closest_distance > 100.0:  # 100m threshold
            for i, segment in enumerate(self.route_segments):
                distance = self._point_to_segment_distance(position, segment)
                if distance < closest_distance:
                    closest_distance = distance
                    closest_segment = segment
                    self.last_segment_index = i

        return closest_segment, closest_distance

    def _point_to_segment_distance(self, point: Coordinate, segment: RoadSegment) -> float:
        """Calculate minimum distance from point to line segment."""
        # Vector from segment start to point
        dx = point.longitude - segment.start.longitude
        dy = point.latitude - segment.start.latitude

        # Vector from segment start to end
        seg_dx = segment.end.longitude - segment.start.longitude
        seg_dy = segment.end.latitude - segment.start.latitude

        # Segment length squared
        seg_len_sq = seg_dx * seg_dx + seg_dy * seg_dy

        if seg_len_sq < 1e-10:
            # Segment is a point
            return segment.start.distance_to(point)

        # Project point onto segment (clamped to [0, 1])
        t = max(0, min(1, (dx * seg_dx + dy * seg_dy) / seg_len_sq))

        # Find closest point on segment
        closest_lon = segment.start.longitude + t * seg_dx
        closest_lat = segment.start.latitude + t * seg_dy
        closest_point = Coordinate(closest_lat, closest_lon)

        return point.distance_to(closest_point)

    def _calculate_lateral_offset(self, position: Coordinate, segment: RoadSegment) -> float:
        """
        Calculate perpendicular (lateral) distance from position to segment centerline.

        Returns:
            Lateral offset in meters. Negative = left of centerline, Positive = right
        """
        # Vector from segment start to point
        point_vec = np.array([
            position.longitude - segment.start.longitude,
            position.latitude - segment.start.latitude
        ])

        # Vector along segment (centerline direction)
        segment_vec = np.array([
            segment.end.longitude - segment.start.longitude,
            segment.end.latitude - segment.start.latitude
        ])

        # Normalize segment vector
        segment_length = np.linalg.norm(segment_vec)
        if segment_length < 1e-10:
            return 0.0

        segment_unit = segment_vec / segment_length

        # Calculate perpendicular (cross product in 2D gives signed area)
        # For lat/lon, we need to account for Earth's curvature
        # Using simple projection for now (works well for short distances)

        # Cross product gives signed perpendicular distance
        cross = point_vec[0] * segment_unit[1] - point_vec[1] * segment_unit[0]

        # Convert to meters (approximate)
        # At mid-latitudes, 1 degree longitude ≈ 111km * cos(latitude)
        # 1 degree latitude ≈ 111km
        avg_lat = (segment.start.latitude + position.latitude) / 2
        lon_to_meters = 111320.0 * math.cos(math.radians(avg_lat))
        lat_to_meters = 111320.0

        # Scale by average meters per degree
        avg_meters_per_degree = (lon_to_meters + lat_to_meters) / 2
        lateral_offset = cross * avg_meters_per_degree

        return lateral_offset

    def _estimate_lane_from_offset(self, lateral_offset: float, lane_count: int) -> LanePosition:
        """
        Estimate lane position based on lateral offset from centerline.

        Args:
            lateral_offset: Distance from centerline (negative = left, positive = right)
            lane_count: Number of lanes in same direction

        Returns:
            LanePosition enum
        """
        if lane_count < 1:
            return LanePosition.UNKNOWN

        # Assume standard lane width
        lane_width = LANE_WIDTH_HIGHWAY_US if lane_count >= 3 else LANE_WIDTH_URBAN_US

        # For multi-lane roads, lanes are numbered from left to right
        # Lane 0 (leftmost), Lane 1 (middle), Lane 2 (rightmost)

        if lane_count == 1:
            # Single lane - always middle
            return LanePosition.MIDDLE_LANE

        elif lane_count == 2:
            # Two lanes: left lane (negative offset), right lane (positive offset)
            # Centerline is between the two lanes
            if lateral_offset < 0:
                return LanePosition.LEFT_LANE
            else:
                return LanePosition.RIGHT_LANE

        else:  # 3+ lanes
            # Calculate which lane based on offset
            # Centerline is in the middle of the road
            # Example for 3 lanes:
            #   Left lane: -lane_width to -lane_width/3
            #   Middle lane: -lane_width/3 to +lane_width/3
            #   Right lane: +lane_width/3 to +lane_width

            half_road_width = (lane_count * lane_width) / 2

            # Normalize offset to lane position (-1 = left edge, +1 = right edge)
            normalized = lateral_offset / half_road_width

            # Determine lane based on normalized position
            if normalized < -0.33:
                return LanePosition.LEFT_LANE
            elif normalized > 0.33:
                return LanePosition.RIGHT_LANE
            else:
                return LanePosition.MIDDLE_LANE

    def _calculate_confidence(
        self,
        gps_accuracy: float,
        segment_distance: float,
        lane_count: int,
        is_highway: bool
    ) -> float:
        """
        Calculate confidence score for GPS lane estimate.

        Factors:
        - GPS accuracy (primary factor)
        - Distance to road centerline (off-road = low confidence)
        - Lane count (more lanes = easier to determine)
        - Road type (highways = better GPS, wider lanes)

        Returns:
            Confidence score 0.0-1.0
        """
        confidence = 1.0

        # 1. GPS accuracy factor (most important)
        if gps_accuracy < GPS_ACCURACY_EXCELLENT:
            gps_factor = 1.0
        elif gps_accuracy < GPS_ACCURACY_GOOD:
            gps_factor = 0.7
        elif gps_accuracy < GPS_ACCURACY_POOR:
            gps_factor = 0.4
        else:
            gps_factor = 0.2

        confidence *= gps_factor

        # 2. Distance to centerline factor
        # If we're far from the road, confidence drops
        expected_max_offset = lane_count * LANE_WIDTH_DEFAULT
        if segment_distance > expected_max_offset:
            distance_factor = max(0.1, 1.0 - (segment_distance - expected_max_offset) / 20.0)
            confidence *= distance_factor

        # 3. Lane count factor
        # More lanes = easier to distinguish (wider spacing)
        if lane_count >= 3:
            lane_factor = 1.0
        elif lane_count == 2:
            lane_factor = 0.7  # Harder to distinguish 2 lanes
        else:
            lane_factor = 0.5  # Single lane - just checking if on road

        confidence *= lane_factor

        # 4. Road type factor
        # Highways have better GPS reception (less buildings/trees)
        if is_highway:
            road_factor = 1.0
        else:
            road_factor = 0.8  # Urban areas may have GPS multipath

        confidence *= road_factor

        return max(0.0, min(1.0, confidence))
