"""
Copyright ©️ Project Teal Lvbs Licensed Under MIT License
"""
import json
import math
import time
import requests
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass

from openpilot.common.swaglog import cloudlog
from openpilot.sunnypilot.navd.helpers import Coordinate, distance_along_geometry, minimum_distance

# Thresholds for turn desire triggering
TURN_DESIRE_START_DISTANCE = 150.0  # meters - start sending turn desires
TURN_DESIRE_END_DISTANCE = 20.0     # meters - stop sending turn desires after passing
MANEUVER_COMPLETION_THRESHOLD = 30.0  # meters - consider maneuver completed

# Turn sharpness thresholds (degrees) for speed recommendations
SHARP_TURN_ANGLE = 60.0    # < 60 degrees is sharp
MODERATE_TURN_ANGLE = 100.0  # 60-100 degrees is moderate
GENTLE_TURN_ANGLE = 140.0   # 100-140 degrees is gentle
# > 140 degrees is very gentle/straight

# Recommended speeds for turn types (m/s)
SPEED_SHARP_TURN = 8.0      # ~18 mph
SPEED_MODERATE_TURN = 12.0  # ~27 mph
SPEED_GENTLE_TURN = 16.0    # ~36 mph
SPEED_EXIT = 15.0           # ~34 mph for highway exits

# Auto-rerouting thresholds
OFF_ROUTE_DISTANCE_THRESHOLD = 75.0  # meters - trigger reroute if this far from route
MIN_REROUTE_INTERVAL = 30.0          # seconds - minimum time between reroute attempts

# Arrival detection threshold
ARRIVAL_THRESHOLD = 10.0  # meters - consider arrived when this close to destination


@dataclass
class Maneuver:
    """Represents a single maneuver in the route."""
    distance_from_start: float  # Distance from route start (m)
    latitude: float
    longitude: float
    type: str  # "turn", "exit", "merge", "fork", "continue", "arrive"
    direction: str  # "left", "right", "straight", "none"
    description: str
    angle: Optional[float] = None  # Turn angle in degrees (for speed calculation)

    def get_recommended_speed(self) -> Optional[float]:
        """Calculate recommended speed for this maneuver."""
        if self.type == "exit":
            return SPEED_EXIT
        elif self.type == "turn" and self.angle is not None:
            if abs(self.angle) < SHARP_TURN_ANGLE:
                return SPEED_SHARP_TURN
            elif abs(self.angle) < MODERATE_TURN_ANGLE:
                return SPEED_MODERATE_TURN
            elif abs(self.angle) < GENTLE_TURN_ANGLE:
                return SPEED_GENTLE_TURN
        return None  # No speed recommendation


class RouteManager:
    """Manages route calculation, tracking, and maneuver detection."""

    def __init__(self, routing_backend: str = "mapbox", mapbox_token: str = ""):
        """
        Initialize route manager.

        Args:
            routing_backend: "mapbox" (default) or "osrm"
            mapbox_token: Mapbox API token (required for mapbox backend)
        """
        self.routing_backend = routing_backend
        self.mapbox_token = mapbox_token
        self.active = False
        self.route_geometry: List[Coordinate] = []
        self.maneuvers: List[Maneuver] = []
        self.current_maneuver_index = 0
        self.destination: Optional[Coordinate] = None
        self.destination_name: str = ""

        # Current tracking state
        self.distance_along_route = 0.0
        self.distance_remaining = 0.0
        self.time_remaining = 0.0
        self.last_position: Optional[Coordinate] = None

        # Auto-rerouting state
        self.last_reroute_time = 0.0
        self.reroute_attempts = 0

        # Turn desire state tracking (for logging)
        self.last_turn_desire_active = False
        self.last_turn_direction = "none"

        # Arrival detection
        self.has_arrived_flag = False

        # OSRM demo server (fallback only)
        self.osrm_server = "http://router.project-osrm.org"

    def calculate_route(self, start: Coordinate, end: Coordinate, destination_name: str = "") -> bool:
        """
        Calculate a route from start to end.

        Returns:
            True if route calculation succeeded, False otherwise
        """
        try:
            if self.routing_backend == "mapbox":
                success = self._calculate_route_mapbox(start, end)
            elif self.routing_backend == "osrm":
                success = self._calculate_route_osrm(start, end)
            else:
                cloudlog.error(f"navd: Unsupported routing backend: {self.routing_backend}")
                return False

            if success:
                self.destination = end
                self.destination_name = destination_name
                self.active = True
                self.current_maneuver_index = 0
                self.has_arrived_flag = False  # Reset arrival flag for new route
                cloudlog.info(f"navd: Route calculated successfully with {len(self.maneuvers)} maneuvers")
                return True
            return False

        except Exception as e:
            cloudlog.exception(f"navd: Route calculation failed: {e}")
            return False

    def _calculate_route_mapbox(self, start: Coordinate, end: Coordinate) -> bool:
        """Calculate route using Mapbox Directions API."""
        try:
            if not self.mapbox_token:
                cloudlog.error("navd: Mapbox token not provided")
                return False

            # Mapbox Directions API
            url = f"https://api.mapbox.com/directions/v5/mapbox/driving/{start.longitude},{start.latitude};{end.longitude},{end.latitude}"
            params = {
                "access_token": self.mapbox_token,
                "geometries": "geojson",
                "steps": "true",
                "banner_instructions": "true",
                "voice_instructions": "false",
                "overview": "full"
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get("code") != "Ok" or not data.get("routes"):
                cloudlog.error(f"navd: Mapbox returned no routes: {data.get('code')}")
                return False

            route = data["routes"][0]

            # Parse geometry
            coordinates = route["geometry"]["coordinates"]
            self.route_geometry = [Coordinate(lat, lon) for lon, lat in coordinates]

            # Parse maneuvers from steps
            self.maneuvers = []
            distance_accumulator = 0.0

            for leg in route.get("legs", []):
                for step in leg.get("steps", []):
                    maneuver_data = step.get("maneuver", {})
                    maneuver_type = maneuver_data.get("type", "turn")
                    modifier = maneuver_data.get("modifier", "straight")

                    # Get location
                    location = maneuver_data.get("location", [0, 0])
                    lon, lat = location[0], location[1]

                    # Determine direction
                    direction = self._parse_direction(modifier)

                    # Get turn angle if available (bearing_after - bearing_before)
                    bearing_before = maneuver_data.get("bearing_before")
                    bearing_after = maneuver_data.get("bearing_after")
                    angle = None
                    if bearing_before is not None and bearing_after is not None:
                        angle = (bearing_after - bearing_before) % 360
                        if angle > 180:
                            angle = angle - 360

                    # Get instruction text
                    instruction = maneuver_data.get("instruction", step.get("name", "Continue"))

                    # Create maneuver
                    maneuver = Maneuver(
                        distance_from_start=distance_accumulator,
                        latitude=lat,
                        longitude=lon,
                        type=self._map_maneuver_type(maneuver_type),
                        direction=direction,
                        description=instruction,
                        angle=angle
                    )

                    self.maneuvers.append(maneuver)
                    distance_accumulator += step.get("distance", 0)

            # Calculate total distance and duration
            self.distance_remaining = route.get("distance", 0)
            self.time_remaining = route.get("duration", 0)

            cloudlog.info(f"navd: Mapbox route: {self.distance_remaining:.0f}m, {self.time_remaining:.0f}s, {len(self.maneuvers)} maneuvers")
            return True

        except requests.RequestException as e:
            cloudlog.exception(f"navd: Mapbox API request failed: {e}")
            return False
        except Exception as e:
            cloudlog.exception(f"navd: Error parsing Mapbox response: {e}")
            return False

    def _calculate_route_osrm(self, start: Coordinate, end: Coordinate) -> bool:
        """Calculate route using OSRM API."""
        try:
            url = f"{self.osrm_server}/route/v1/driving/{start.longitude},{start.latitude};{end.longitude},{end.latitude}"
            params = {
                "overview": "full",
                "geometries": "geojson",
                "steps": "true",
                "annotations": "true"
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get("code") != "Ok" or not data.get("routes"):
                cloudlog.error(f"navd: OSRM returned no routes")
                return False

            route = data["routes"][0]

            # Parse geometry
            coordinates = route["geometry"]["coordinates"]
            self.route_geometry = [Coordinate(lat, lon) for lon, lat in coordinates]

            # Parse maneuvers from steps
            self.maneuvers = []
            distance_accumulator = 0.0

            for leg in route.get("legs", []):
                for step in leg.get("steps", []):
                    maneuver_data = step.get("maneuver", {})
                    maneuver_type = maneuver_data.get("type", "turn")
                    modifier = maneuver_data.get("modifier", "straight")

                    # Get location
                    location = maneuver_data.get("location", [0, 0])
                    lat, lon = location[1], location[0]

                    # Determine direction
                    direction = self._parse_direction(modifier)

                    # Get turn angle if available (bearing_after - bearing_before)
                    bearing_before = maneuver_data.get("bearing_before")
                    bearing_after = maneuver_data.get("bearing_after")
                    angle = None
                    if bearing_before is not None and bearing_after is not None:
                        angle = (bearing_after - bearing_before) % 360
                        if angle > 180:
                            angle = angle - 360

                    # Create maneuver
                    maneuver = Maneuver(
                        distance_from_start=distance_accumulator,
                        latitude=lat,
                        longitude=lon,
                        type=self._map_maneuver_type(maneuver_type),
                        direction=direction,
                        description=step.get("name", "Continue"),
                        angle=angle
                    )

                    self.maneuvers.append(maneuver)
                    distance_accumulator += step.get("distance", 0)

            # Calculate total distance
            self.distance_remaining = route.get("distance", 0)
            self.time_remaining = route.get("duration", 0)

            return True

        except requests.RequestException as e:
            cloudlog.exception(f"navd: OSRM API request failed: {e}")
            return False
        except Exception as e:
            cloudlog.exception(f"navd: Error parsing OSRM response: {e}")
            return False

    def _parse_direction(self, modifier: str) -> str:
        """Parse OSRM modifier to direction."""
        if "left" in modifier:
            return "left"
        elif "right" in modifier:
            return "right"
        elif "straight" in modifier or modifier == "":
            return "straight"
        return "none"

    def _map_maneuver_type(self, maneuver_type: str) -> str:
        """Map routing service maneuver type to our internal type."""
        type_mapping = {
            # Mapbox types
            "turn": "turn",
            "new name": "continue_",
            "depart": "continue_",
            "arrive": "arrive",
            "merge": "merge",
            "on ramp": "merge",
            "off ramp": "exit",
            "fork": "fork",
            "end of road": "turn",
            "continue": "continue_",
            "roundabout": "roundabout",
            "rotary": "roundabout",
            "roundabout turn": "roundabout",
            "notification": "continue_",
            "exit roundabout": "turn",
            "exit rotary": "turn",
            # OSRM types (for compatibility)
            "straight": "continue_",
        }
        return type_mapping.get(maneuver_type, "turn")

    def update_position(self, current_pos: Coordinate) -> None:
        """
        Update current position and recalculate distance along route.

        Args:
            current_pos: Current GPS position
        """
        if not self.active or not self.route_geometry:
            return

        self.last_position = current_pos

        # Calculate distance along route
        self.distance_along_route = distance_along_geometry(self.route_geometry, current_pos)

        # Update distance remaining
        total_distance = sum(
            self.route_geometry[i].distance_to(self.route_geometry[i + 1])
            for i in range(len(self.route_geometry) - 1)
        )
        self.distance_remaining = max(0, total_distance - self.distance_along_route)

        # Update current maneuver index
        self._update_current_maneuver()

        # Check if we need to reroute
        self._check_and_reroute(current_pos)

    def _update_current_maneuver(self) -> None:
        """Update current maneuver index based on distance along route."""
        # Find the maneuver we're approaching or have just passed
        for i, maneuver in enumerate(self.maneuvers):
            if self.distance_along_route < maneuver.distance_from_start + MANEUVER_COMPLETION_THRESHOLD:
                self.current_maneuver_index = i
                return

        # If we've passed all maneuvers, we're at the last one
        if self.maneuvers:
            self.current_maneuver_index = len(self.maneuvers) - 1

    def get_next_maneuver(self) -> Optional[Maneuver]:
        """Get the next upcoming maneuver."""
        if not self.active or not self.maneuvers:
            return None

        if self.current_maneuver_index < len(self.maneuvers):
            return self.maneuvers[self.current_maneuver_index]

        return None

    def get_distance_to_next_maneuver(self) -> float:
        """Get distance to next maneuver in meters."""
        maneuver = self.get_next_maneuver()
        if maneuver is None:
            return 0.0

        return max(0, maneuver.distance_from_start - self.distance_along_route)

    def should_send_turn_desire(self) -> Tuple[bool, str]:
        """
        Determine if we should send turn desires to the model.

        Returns:
            (should_send, direction) tuple where:
                should_send: True if turn desires should be sent
                direction: "left", "right", or "none"
        """
        maneuver = self.get_next_maneuver()
        if maneuver is None:
            return False, "none"

        distance_to_maneuver = self.get_distance_to_next_maneuver()

        # Don't send turn desires for straight maneuvers
        if maneuver.direction == "straight" or maneuver.direction == "none":
            return False, "none"

        # Send turn desires when within threshold distance
        should_send = False
        direction = "none"

        if 0 <= distance_to_maneuver <= TURN_DESIRE_START_DISTANCE:
            should_send = True
            direction = maneuver.direction
        elif distance_to_maneuver < -TURN_DESIRE_END_DISTANCE:
            should_send = False
            direction = "none"

        # Log when turn desire state changes
        if should_send != self.last_turn_desire_active or direction != self.last_turn_direction:
            if should_send:
                cloudlog.info(f"navd: 🔄 TURN DESIRE ACTIVE - Direction: {direction.upper()} | "
                             f"Distance: {distance_to_maneuver:.0f}m | Maneuver: {maneuver.description}")
            else:
                cloudlog.info(f"navd: ✓ Turn desire cleared")

            self.last_turn_desire_active = should_send
            self.last_turn_direction = direction

        return should_send, direction

    def get_target_speed(self) -> Optional[float]:
        """
        Get target speed for upcoming maneuver.

        Returns:
            Target speed in m/s, or None if no speed recommendation
        """
        maneuver = self.get_next_maneuver()
        if maneuver is None:
            return None

        distance_to_maneuver = self.get_distance_to_next_maneuver()

        # Only provide speed recommendation when approaching maneuver
        if 0 <= distance_to_maneuver <= 300.0:  # 300m lookahead
            return maneuver.get_recommended_speed()

        return None

    def _check_and_reroute(self, current_pos: Coordinate) -> None:
        """
        Check if vehicle is off route and trigger reroute if needed.

        Args:
            current_pos: Current GPS position
        """
        if not self.active or not self.route_geometry or not self.destination:
            return

        # Check time since last reroute
        current_time = time.monotonic()
        if current_time - self.last_reroute_time < MIN_REROUTE_INTERVAL:
            return

        # Calculate distance from route (find minimum distance to any segment)
        distance_from_route = self._get_distance_from_route(current_pos)

        # Trigger reroute if too far off course
        if distance_from_route > OFF_ROUTE_DISTANCE_THRESHOLD:
            cloudlog.warning(f"navd: Off route by {distance_from_route:.0f}m, triggering reroute (attempt {self.reroute_attempts + 1})")
            self._trigger_reroute(current_pos)

    def _get_distance_from_route(self, pos: Coordinate) -> float:
        """
        Calculate minimum distance from position to route.

        Args:
            pos: Current position

        Returns:
            Minimum distance to route in meters
        """
        if len(self.route_geometry) < 2:
            return 0.0

        min_dist = float('inf')
        for i in range(len(self.route_geometry) - 1):
            dist = minimum_distance(self.route_geometry[i], self.route_geometry[i + 1], pos)
            min_dist = min(min_dist, dist)

        return min_dist

    def _trigger_reroute(self, current_pos: Coordinate) -> None:
        """
        Trigger automatic rerouting from current position to destination.

        Args:
            current_pos: Current GPS position
        """
        if not self.destination:
            return

        self.last_reroute_time = time.monotonic()
        self.reroute_attempts += 1

        # Calculate new route from current position
        success = self.calculate_route(current_pos, self.destination, self.destination_name)

        if success:
            cloudlog.info(f"navd: Reroute successful (attempt {self.reroute_attempts})")
        else:
            cloudlog.error(f"navd: Reroute failed (attempt {self.reroute_attempts})")

    def cancel_navigation(self) -> None:
        """Cancel active navigation."""
        self.active = False
        self.route_geometry = []
        self.maneuvers = []
        self.current_maneuver_index = 0
        self.destination = None
        self.destination_name = ""
        self.last_reroute_time = 0.0
        self.reroute_attempts = 0
        self.has_arrived_flag = False
        cloudlog.info("navd: Navigation cancelled")

    def check_arrival(self, current_pos: Coordinate) -> bool:
        """
        Check if vehicle has arrived at destination.

        Uses three detection criteria:
        1. Distance remaining < threshold
        2. Direct distance to destination < threshold
        3. Last maneuver is "arrive" type and vehicle has passed it

        Args:
            current_pos: Current GPS position

        Returns:
            True if arrived at destination
        """
        # Don't check arrival if not navigating or already arrived
        if not self.active or not self.destination or self.has_arrived_flag:
            return False

        # Criterion 1: Distance remaining along route is very small
        if self.distance_remaining < ARRIVAL_THRESHOLD:
            self.has_arrived_flag = True
            cloudlog.info(f"navd: 🎯 ARRIVED - Distance remaining: {self.distance_remaining:.1f}m")
            return True

        # Criterion 2: Direct distance to destination (as-the-crow-flies)
        direct_distance = current_pos.distance_to(self.destination)
        if direct_distance < ARRIVAL_THRESHOLD:
            self.has_arrived_flag = True
            cloudlog.info(f"navd: 🎯 ARRIVED - Direct distance to destination: {direct_distance:.1f}m")
            return True

        # Criterion 3: Last maneuver is "arrive" type and we've reached or passed it
        if self.maneuvers:
            last_maneuver = self.maneuvers[-1]
            if last_maneuver.type == "arrive":
                # Check if we've reached or passed the arrive maneuver
                distance_to_arrive = last_maneuver.distance_from_start - self.distance_along_route
                # Trigger when we're at or past the arrival point (distance_to_arrive <= threshold)
                # This handles both arriving at the point and passing it
                if distance_to_arrive <= ARRIVAL_THRESHOLD:
                    self.has_arrived_flag = True
                    cloudlog.info(f"navd: 🎯 ARRIVED - Reached/passed arrival maneuver (distance: {abs(distance_to_arrive):.1f}m)")
                    return True

        return False
