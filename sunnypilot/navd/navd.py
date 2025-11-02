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
from openpilot.sunnypilot.navd.helpers import Coordinate, detect_lane_position, LanePosition
from openpilot.sunnypilot.navd.route_manager import RouteManager
from openpilot.sunnypilot.navd.gps_lane_tracker import GPSLaneTracker


# MAPBOX API TOKEN
# Get your token from: https://account.mapbox.com/access-tokens/
DEFAULT_MAPBOX_TOKEN = "pk.eyJ1IjoidGVhbDIiLCJhIjoiY205Znl1dXBnMXF2eTJrcTFvcnF0NTNnaiJ9.trElYJImmMd1Aie0n3gOMQ"


class NavigationDaemon:
    def __init__(self):
        self.params = Params()

        # Messaging
        self.sm = messaging.SubMaster(['liveLocationKalman', 'modelV2'])
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

        # GPS lane tracker (observation mode - testing only)
        self.gps_lane_tracker = GPSLaneTracker()

        # State
        self.current_position: Coordinate | None = None
        self.last_bearing: float | None = None
        self.localizer_valid = False
        self.v_ego: float = 0.0  # Current vehicle speed in m/s
        self.current_lane_position: LanePosition = LanePosition.UNKNOWN  # Current detected lane position

        # Lane tracking debug info for web UI
        self.lane_debug_info: dict = {
            'model_lane': 'unknown',
            'model_confidence': 0.0,
            'gps_lane': 'unknown',
            'gps_confidence': 0.0,
            'lateral_offset': 0.0,
            'gps_accuracy': 0.0,
            'agreement': False,
        }

        # Destination tracking
        self.last_destination_json = ""
        self.destination_check_counter = 0

        # Route selection state tracking
        self.last_preferences_json = ""
        self.last_route_selection_json = ""
        self.preferences_check_counter = 0
        self.route_selection_check_counter = 0

        # Load routing preferences
        self.load_preferences_from_params()

        cloudlog.info("navd: Navigation daemon initialized")

    def load_preferences_from_params(self) -> None:
        """Load routing preferences from params and apply to route manager."""
        prefs_json = self.params.get("NavigationPreferences")

        if prefs_json:
            try:
                preferences = json.loads(prefs_json)
                updated_prefs = self.route_manager.set_preferences(preferences)
                cloudlog.info(f"navd: Loaded routing preferences: {updated_prefs}")
                self.last_preferences_json = prefs_json
            except json.JSONDecodeError as e:
                cloudlog.error(f"navd: Failed to parse preferences JSON: {e}")

    def check_preferences_update(self) -> None:
        """Check for preference updates and recalculation requests."""
        self.preferences_check_counter += 1
        if self.preferences_check_counter < 5:
            return

        self.preferences_check_counter = 0

        # Check for preference changes
        prefs_json = self.params.get("NavigationPreferences")
        if prefs_json and prefs_json != self.last_preferences_json:
            try:
                preferences = json.loads(prefs_json)
                updated_prefs = self.route_manager.set_preferences(preferences)
                cloudlog.info(f"navd: Preferences updated: {updated_prefs}")
                self.last_preferences_json = prefs_json
            except json.JSONDecodeError as e:
                cloudlog.error(f"navd: Failed to parse preferences JSON: {e}")

        # Check for recalculation request
        if self.params.get_bool("NavigationRecalculateRoutes"):
            # Clear flag immediately
            self.params.remove("NavigationRecalculateRoutes")

            # Trigger recalculation if we have an active destination
            if self.route_manager.active and self.current_position and self.localizer_valid:
                cloudlog.info("navd: Recalculating routes with new preferences...")
                success = self.route_manager.calculate_route(
                    self.current_position,
                    self.route_manager.destination,
                    self.route_manager.destination_name
                )

                if success:
                    cloudlog.info("navd: Route recalculation succeeded")
                    self.write_route_alternatives_to_params()
                else:
                    cloudlog.error("navd: Route recalculation failed")

    def check_route_selection_update(self) -> None:
        """Check for route selection updates from web UI."""
        self.route_selection_check_counter += 1
        if self.route_selection_check_counter < 5:
            return

        self.route_selection_check_counter = 0

        selection_json = self.params.get("NavigationRouteSelection")

        if not selection_json:
            return

        if selection_json == self.last_route_selection_json:
            return

        try:
            selection_data = json.loads(selection_json)
            route_index = selection_data.get("route_index")

            if route_index is not None:
                success = self.route_manager.select_route(route_index)
                if success:
                    cloudlog.info(f"navd: Successfully selected route {route_index}")
                    self.last_route_selection_json = selection_json
                else:
                    cloudlog.error(f"navd: Failed to select route {route_index}")

        except json.JSONDecodeError as e:
            cloudlog.error(f"navd: Failed to parse route selection JSON: {e}")
        except Exception as e:
            cloudlog.exception(f"navd: Error processing route selection: {e}")

    def write_route_alternatives_to_params(self) -> None:
        """Write calculated route alternatives to params for web UI."""
        try:
            alternatives = self.route_manager.get_route_alternatives_summary()
            alternatives_json = json.dumps(alternatives)
            self.params.put("NavigationRouteAlternatives", alternatives_json)
            cloudlog.info(f"navd: Wrote {len(alternatives)} route alternatives to params")
        except Exception as e:
            cloudlog.exception(f"navd: Error writing route alternatives: {e}")

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

            # Extract vehicle speed (velocity magnitude from NED frame)
            if location.velocityCalibrated.valid:
                v_ned = location.velocityCalibrated.value
                self.v_ego = math.sqrt(v_ned[0]**2 + v_ned[1]**2 + v_ned[2]**2)
            else:
                self.v_ego = 0.0

            # Update route manager with current position
            if self.route_manager.active and self.current_position:
                self.route_manager.update_position(self.current_position)

                # Update GPS lane tracker with route data
                self.gps_lane_tracker.update_from_route(self.route_manager)

                # Check if arrived at destination
                if self.route_manager.check_arrival(self.current_position):
                    cloudlog.info(f"navd: Auto-ending navigation - arrived at {self.route_manager.destination_name}")
                    self.params.remove("NavigationDestination")
                    self.params.put_bool("NavigationActive", False)
                    self.last_destination_json = ""  # Clear destination tracking

    def update_lane_position(self) -> None:
        """
        Update current lane position from MULTIPLE sources.

        MODEL-BASED (ACTIVE): Primary source, controls lane positioning
        GPS-BASED (TESTING): Secondary source, for validation only

        Both sources are tracked and logged for comparison and validation.
        """
        # MODEL-BASED DETECTION (ACTIVE - controls lane positioning)
        model_lane = LanePosition.UNKNOWN
        model_confidence = 0.0

        if 'modelV2' in self.sm.valid and self.sm.valid['modelV2']:
            model_v2 = self.sm['modelV2']
            model_lane = detect_lane_position(model_v2)
            # Calculate model confidence from lane line probabilities
            model_confidence = self._calculate_model_confidence(model_v2)

        # USE MODEL AS SOLE AUTHORITY (no fusion yet)
        self.current_lane_position = model_lane

        # GPS-BASED DETECTION (TESTING - observation only)
        gps_lane = LanePosition.UNKNOWN
        gps_confidence = 0.0
        lateral_offset = 0.0

        if self.route_manager.active and self.current_position and self.localizer_valid:
            # Get GPS accuracy from liveLocationKalman
            location = self.sm['liveLocationKalman']
            gps_accuracy = 5.0  # Default
            if location.positionGeodetic.valid and hasattr(location.positionGeodetic, 'std'):
                # Standard deviation gives position uncertainty
                gps_accuracy = max(location.positionGeodetic.std[0], location.positionGeodetic.std[1])

            # Calculate GPS-based lane estimate
            gps_lane, gps_confidence, lateral_offset = self.gps_lane_tracker.calculate_lane_position(
                self.current_position,
                self.last_bearing if self.last_bearing else 0.0,
                gps_accuracy
            )

        # Check agreement between sources
        agreement = (model_lane == gps_lane) and (model_lane != LanePosition.UNKNOWN)

        # Helper to safely convert floats, replacing NaN with 0.0
        def safe_float(value):
            if value is None or (isinstance(value, float) and math.isnan(value)):
                return 0.0
            return float(value)

        # Update debug info for web UI
        self.lane_debug_info = {
            'model_lane': model_lane.value,
            'model_confidence': safe_float(model_confidence),
            'gps_lane': gps_lane.value,
            'gps_confidence': safe_float(gps_confidence),
            'lateral_offset': safe_float(lateral_offset),
            'gps_accuracy': safe_float(gps_accuracy) if self.route_manager.active else 0.0,
            'agreement': bool(agreement),
        }

        # Log disagreements and periodic status (every 5 seconds at 5Hz = 25 frames)
        if not agreement or self.sm.frame % 25 == 0:
            if self.route_manager.active:  # Only log when navigation is active
                cloudlog.info(
                    f"navd: Lane tracking - "
                    f"Model: {model_lane.value} (conf: {model_confidence:.2f}), "
                    f"GPS: {gps_lane.value} (conf: {gps_confidence:.2f}), "
                    f"Offset: {lateral_offset:.2f}m, "
                    f"Agree: {agreement}"
                )

    def _calculate_model_confidence(self, model_v2) -> float:
        """
        Calculate confidence score for model-based lane detection.

        Factors:
        - Lane line probabilities
        - Number of visible lane lines
        - Distance validation (not curbs/edges)

        Returns:
            Confidence score 0.0-1.0
        """
        if not model_v2 or not hasattr(model_v2, 'laneLineProbs') or len(model_v2.laneLineProbs) < 3:
            return 0.0

        # Get lane line probabilities
        left_prob = model_v2.laneLineProbs[1] if len(model_v2.laneLineProbs) > 1 else 0.0
        right_prob = model_v2.laneLineProbs[2] if len(model_v2.laneLineProbs) > 2 else 0.0

        # Average of visible lane line probabilities
        max_prob = max(left_prob, right_prob)
        avg_prob = (left_prob + right_prob) / 2.0

        # If both lines visible with high confidence, return average
        if left_prob > 0.5 and right_prob > 0.5:
            return avg_prob

        # If only one line visible, use that probability but reduce confidence
        if max_prob > 0.5:
            return max_prob * 0.7

        # Low confidence - no clear lane lines
        return max_prob * 0.5

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
                # Write route alternatives to params for web UI
                self.write_route_alternatives_to_params()
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
                nav_state.nextManeuverAngle = float(next_maneuver.angle) if next_maneuver.angle is not None else 0.0
            else:
                nav_state.nextManeuverValid = False

            # Initiate Turn desire control (dynamic distance based on turn characteristics and speed)
            should_send, direction = self.route_manager.should_send_turn_desire(self.v_ego)
            nav_state.shouldSendTurnDesire = should_send
            nav_state.turnDesireDirection = self._map_direction(direction)

            # Lane change desire control (for highway exits/ramps at >45 mph)
            should_send_lc, lc_direction = self.route_manager.should_send_lane_change_desire(self.v_ego)
            nav_state.shouldSendLaneChangeDesire = should_send_lc
            nav_state.laneChangeDesireDirection = self._map_direction(lc_direction)

            # Lane positioning guidance (for early lane changes before exits/turns)
            # Pass model_v2 for safety validation (lane counting to prevent oncoming traffic lane changes)
            should_send_lane_pos, lane_pos_direction = self.route_manager.should_send_lane_positioning_desire(
                self.current_lane_position,
                self.sm['modelV2']
            )
            nav_state.shouldSendLanePositioning = should_send_lane_pos
            nav_state.lanePositioningDirection = self._map_direction(lane_pos_direction)

            # E2e Speed guidance (dynamic distance based on current speed)
            target_speed = self.route_manager.get_target_speed(self.v_ego)
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
            nav_state.shouldSendLanePositioning = False
            nav_state.targetSpeedValid = False

        # Lane tracking debug info (for web UI)
        debug_info = nav_state.laneDebugInfo
        debug_info.modelLane = self.lane_debug_info['model_lane']
        debug_info.modelConfidence = self.lane_debug_info['model_confidence']
        debug_info.gpsLane = self.lane_debug_info['gps_lane']
        debug_info.gpsConfidence = self.lane_debug_info['gps_confidence']
        debug_info.lateralOffset = self.lane_debug_info['lateral_offset']
        debug_info.gpsAccuracy = self.lane_debug_info['gps_accuracy']
        debug_info.agreement = self.lane_debug_info['agreement']

        # Navigation-specific UI event fields (for selfdrived to trigger UI alerts)
        if self.route_manager.active:
            # Set nav turn desire direction from existing logic
            should_send_turn, turn_dir = self.route_manager.should_send_turn_desire(self.v_ego)
            nav_state.navTurnDesireDirection = self._map_nav_direction(turn_dir)

            # Set nav lane change desire direction from existing logic
            should_send_lc, lc_dir = self.route_manager.should_send_lane_change_desire(self.v_ego)
            nav_state.navLaneChangeDesireDirection = self._map_nav_direction(lc_dir)

            # Set nav lane positioning direction from existing logic
            should_send_pos, pos_dir = self.route_manager.should_send_lane_positioning_desire(
                self.current_lane_position,
                self.sm['modelV2']
            )
            nav_state.navLanePositioningDirection = self._map_nav_direction(pos_dir)

            # Set speed target active status
            nav_state.navSpeedTargetActive = self.route_manager.get_target_speed(self.v_ego) is not None
        else:
            # Clear nav UI fields when navigation is inactive
            nav_state.navTurnDesireDirection = 0  # NavDirection.none
            nav_state.navLaneChangeDesireDirection = 0  # NavDirection.none
            nav_state.navLanePositioningDirection = 0  # NavDirection.none
            nav_state.navSpeedTargetActive = False

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
            "none": custom.ModelDataV2SP.TurnDirection.none,
            "straight": custom.ModelDataV2SP.TurnDirection.none,
            "left": custom.ModelDataV2SP.TurnDirection.turnLeft,
            "right": custom.ModelDataV2SP.TurnDirection.turnRight,
        }
        return direction_map.get(direction, custom.ModelDataV2SP.TurnDirection.none)

    def _map_nav_direction(self, direction: str) -> int:
        """Map direction string to NavDirection enum for UI events."""
        if direction == "left":
            return 1  # NavDirection.left
        elif direction == "right":
            return 2  # NavDirection.right
        return 0  # NavDirection.none

    def step(self) -> None:
        # Update messaging
        self.sm.update(0)

        # Update location
        self.update_location()

        # Update lane position from modelV2
        self.update_lane_position()

        # Check for destination updates
        self.check_destination_update()

        # Check for preferences updates and recalculation requests
        self.check_preferences_update()

        # Check for route selection updates
        self.check_route_selection_update()

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
