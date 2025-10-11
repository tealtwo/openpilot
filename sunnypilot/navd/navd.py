#!/usr/bin/env python3
"""
Copyright ©️ Project Teal Lvbs Licensed Under MIT License
"""
import json
import math

from cereal import messaging, custom, log
from openpilot.common.params import Params
from openpilot.common.realtime import Ratekeeper, config_realtime_process
from openpilot.common.swaglog import cloudlog
from openpilot.sunnypilot.navd.helpers import Coordinate
from openpilot.sunnypilot.navd.route_manager import RouteManager


# MAPBOX API TOKEN
# Get your token from: https://account.mapbox.com/access-tokens/
DEFAULT_MAPBOX_TOKEN = "pk.eyJ1IjoidGVhbDIiLCJhIjoiY205Znl1dXBnMXF2eTJrcTFvcnF0NTNnaiJ9.trElYJImmMd1Aie0n3gOMQ"


class NavigationDaemon:
    def __init__(self):
        self.params = Params()

        # Messaging
        self.sm = messaging.SubMaster(['liveLocationKalman'])
        self.pm = messaging.PubMaster(['navStateSP'])

        # Get Mapbox token - try parameter first, then use default
        mapbox_token = self.params.get("MapboxToken")
        if not mapbox_token and DEFAULT_MAPBOX_TOKEN:
            cloudlog.info("navd: Using default Mapbox token from code")
            mapbox_token = DEFAULT_MAPBOX_TOKEN
        elif not mapbox_token:
            cloudlog.warning("navd: No Mapbox token found. Set DEFAULT_MAPBOX_TOKEN in navd.py or 'MapboxToken' parameter.")
            mapbox_token = ""

        # Route manager
        self.route_manager = RouteManager(routing_backend="mapbox", mapbox_token=mapbox_token)

        # State
        self.current_position: Coordinate | None = None
        self.last_bearing: float | None = None
        self.localizer_valid = False

        # Destination tracking
        self.last_destination_json = ""
        self.destination_check_counter = 0

        cloudlog.info("navd: Navigation daemon initialized")

    def update_location(self) -> None:
        # Update Current Location liveLocationKalman
        location = self.sm['liveLocationKalman']

        self.localizer_valid = (
            location.status == log.LiveLocationKalman.Status.valid
            and location.positionGeodetic.valid
        )

        if self.localizer_valid:
            self.last_bearing = math.degrees(location.calibratedOrientationNED.value[2])
            self.current_position = Coordinate(
                location.positionGeodetic.value[0],
                location.positionGeodetic.value[1]
            )

            # Update route manager with current position
            if self.route_manager.active and self.current_position:
                self.route_manager.update_position(self.current_position)

                # Check if arrived at destination
                if self.route_manager.check_arrival(self.current_position):
                    cloudlog.info(f"navd: Auto-ending navigation - arrived at {self.route_manager.destination_name}")
                    self.params.remove("NavigationDestination")
                    self.params.put_bool("NavigationActive", False)
                    self.last_destination_json = ""  # Clear destination tracking

    def check_destination_update(self) -> None:
        # Check if new destination has been set via params
        # Check every 5 cycles (~1 second at 5Hz)
        self.destination_check_counter += 1
        if self.destination_check_counter < 5:
            return

        self.destination_check_counter = 0

        # Check for destination param
        destination_json = self.params.get("NavigationDestination")

        if not destination_json:
            # No destination set
            if self.route_manager.active:
                cloudlog.info("navd: Destination cleared, cancelling navigation")
                self.route_manager.cancel_navigation()
            return

        # Check if destination changed or if we need to retry if GPS not valid
        destination_changed = destination_json != self.last_destination_json
        need_route_calc = destination_changed or (destination_json and not self.route_manager.active)

        if not need_route_calc:
            return

        try:
            dest_data = json.loads(destination_json)
            dest_lat = dest_data.get("latitude")
            dest_lon = dest_data.get("longitude")
            dest_name = dest_data.get("name", "")

            if dest_lat is None or dest_lon is None:
                cloudlog.error("navd: Invalid destination data")
                self.last_destination_json = destination_json  # Mark as processed even if invalid
                return

            # Check if we have a valid current position
            if not self.current_position or not self.localizer_valid:
                # Don't update last_destination_json so we retry when GPS becomes valid
                if destination_changed:
                    cloudlog.warning("navd: Waiting for valid GPS position to calculate route...")
                return

            destination = Coordinate(dest_lat, dest_lon)

            # Only log on new destinations, not retries
            if destination_changed:
                cloudlog.info(f"navd: New destination set: {dest_name} ({dest_lat}, {dest_lon})")

            # Calculate route
            success = self.route_manager.calculate_route(
                self.current_position,
                destination,
                dest_name
            )

            if success:
                cloudlog.info("navd: Route calculation succeeded")
                self.params.put_bool("NavigationActive", True)
                self.last_destination_json = destination_json  # Mark as processed after success
            else:
                cloudlog.error("navd: Route calculation failed")
                self.params.put_bool("NavigationActive", False)
                self.last_destination_json = destination_json  # Mark as processed even if failed

        except json.JSONDecodeError as e:
            cloudlog.error(f"navd: Failed to parse destination JSON: {e}")
            self.last_destination_json = destination_json  # Mark as processed
        except Exception as e:
            cloudlog.exception(f"navd: Error processing destination update: {e}")
            self.last_destination_json = destination_json  # Mark as processed

    def publish_nav_state(self) -> None:
        # Publish nav state to navStateSP
        msg = messaging.new_message('navStateSP')
        nav_state = msg.navStateSP

        # Basic state
        nav_state.active = self.route_manager.active
        nav_state.destinationValid = self.route_manager.destination is not None

        if self.route_manager.active:
            # Position and route info
            nav_state.distanceRemaining = self.route_manager.distance_remaining
            nav_state.timeRemaining = self.route_manager.time_remaining
            nav_state.currentSegmentIndex = self.route_manager.current_maneuver_index
            nav_state.totalSegments = len(self.route_manager.maneuvers)

            # Next maneuver
            next_maneuver = self.route_manager.get_next_maneuver()
            if next_maneuver:
                nav_state.nextManeuverValid = True
                nav_state.nextManeuverDistance = self.route_manager.get_distance_to_next_maneuver()
                nav_state.nextManeuverType = self._map_maneuver_type(next_maneuver.type)
                nav_state.nextManeuverDirection = self._map_direction(next_maneuver.direction)
                nav_state.nextManeuverDescription = next_maneuver.description
            else:
                nav_state.nextManeuverValid = False

            # Iniate Turn desire control
            should_send, direction = self.route_manager.should_send_turn_desire()
            nav_state.shouldSendTurnDesire = should_send
            nav_state.turnDesireDirection = self._map_direction(direction)

            # E2e Speed guidance
            target_speed = self.route_manager.get_target_speed()
            if target_speed is not None:
                nav_state.targetSpeed = target_speed
                nav_state.targetSpeedValid = True
            else:
                nav_state.targetSpeedValid = False

            # Destination info
            if self.route_manager.destination:
                nav_state.destinationLatitude = self.route_manager.destination.latitude
                nav_state.destinationLongitude = self.route_manager.destination.longitude
                nav_state.destinationName = self.route_manager.destination_name

        else:
            nav_state.nextManeuverValid = False
            nav_state.shouldSendTurnDesire = False
            nav_state.targetSpeedValid = False

        # Send message
        self.pm.send('navStateSP', msg)

    def _map_maneuver_type(self, maneuver_type: str) -> int:
        # Map manuever type to enum
        type_map = {
            "none": custom.NavStateSP.ManeuverType.none,
            "turn": custom.NavStateSP.ManeuverType.turn,
            "exit": custom.NavStateSP.ManeuverType.exit,
            "merge": custom.NavStateSP.ManeuverType.merge,
            "fork": custom.NavStateSP.ManeuverType.fork,
            "continue_": custom.NavStateSP.ManeuverType.continueStraight,
            "arrive": custom.NavStateSP.ManeuverType.arrive,
            "roundabout": custom.NavStateSP.ManeuverType.roundabout,
        }
        return type_map.get(maneuver_type, custom.NavStateSP.ManeuverType.none)

    def _map_direction(self, direction: str) -> int:
        # Map turnDirection string to enum
        direction_map = {
            "none": custom.TurnDirection.none,
            "straight": custom.TurnDirection.none,
            "left": custom.TurnDirection.turnLeft,
            "right": custom.TurnDirection.turnRight,
        }
        return direction_map.get(direction, custom.TurnDirection.none)

    def step(self) -> None:
        # Update messaging
        self.sm.update(0)

        # Update location
        self.update_location()

        # Check for destination updates
        self.check_destination_update()

        # Publish navigation state
        self.publish_nav_state()


def main():
    config_realtime_process([0, 1, 2, 3], 5)

    rk = Ratekeeper(5.0, print_delay_threshold=None)  # 5 Hz
    daemon = NavigationDaemon()

    cloudlog.info("navd: Navigation daemon started")

    while True:
        daemon.step()
        rk.keep_time()


if __name__ == "__main__":
    main()
