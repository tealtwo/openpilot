"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from cereal import custom

from openpilot.common.constants import CV
from openpilot.common.params import Params

TurnDirection = custom.ModelDataV2SP.TurnDirection

LANE_CHANGE_SPEED_MIN = 30 * CV.MPH_TO_MS


class LaneTurnController:
  def __init__(self, desire_helper):
    self.DH = desire_helper
    self.turn_direction = TurnDirection.none
    self.params = Params()
    self.lane_turn_value = float(self.params.get("LaneTurnValue", return_default=True)) * CV.MPH_TO_MS
    self.param_read_counter = 0
    self.enabled = self.params.get_bool("LaneTurnDesire")

    # Navigation-based turn desires
    self.nav_turn_direction = TurnDirection.none
    self.nav_enabled = False

    # Navigation-based lane positioning
    self.nav_lane_positioning_direction = TurnDirection.none
    self.nav_lane_positioning_enabled = False

  def read_params(self):
    self.enabled = self.params.get_bool("LaneTurnDesire")
    value = float(self.params.get("LaneTurnValue", return_default=True)) * CV.MPH_TO_MS
    self.lane_turn_value = min(float(LANE_CHANGE_SPEED_MIN), value)

  def update_params(self) -> None:
    if self.param_read_counter % 50 == 0:
      self.read_params()
    self.param_read_counter += 1

  def update_lane_turn(self, blindspot_left: bool, blindspot_right: bool, left_blinker: bool, right_blinker: bool, v_ego: float) -> None:
    if left_blinker and not right_blinker and v_ego < self.lane_turn_value and not blindspot_left:
      self.turn_direction = TurnDirection.turnLeft
    elif right_blinker and not left_blinker and v_ego < self.lane_turn_value and not blindspot_right:
      self.turn_direction = TurnDirection.turnRight
    else:
      self.turn_direction = TurnDirection.none

  def update_nav_turn(self, nav_state) -> None:
    """
    Update turn direction based on navigation state.

    Args:
      nav_state: NavStateSP message from navd
    """
    if not nav_state:
      self.nav_turn_direction = TurnDirection.none
      self.nav_enabled = False
      return

    # Check if navigation is active and wants to send turn desires
    if nav_state.active and nav_state.shouldSendTurnDesire:
      # Convert capnp enum integer to TurnDirection enum
      turn_dir_int = nav_state.turnDesireDirection
      if turn_dir_int == TurnDirection.turnLeft:
        self.nav_turn_direction = TurnDirection.turnLeft
      elif turn_dir_int == TurnDirection.turnRight:
        self.nav_turn_direction = TurnDirection.turnRight
      else:
        self.nav_turn_direction = TurnDirection.none
      self.nav_enabled = True
    else:
      self.nav_turn_direction = TurnDirection.none
      self.nav_enabled = False

  def update_nav_lane_positioning(self, nav_state) -> None:
    """
    Update lane positioning direction based on navigation state.

    This is used for early lane positioning (0.5-1 mile before exits/turns)
    to guide the vehicle into the correct lane.

    Args:
      nav_state: NavStateSP message from navd
    """
    if not nav_state:
      self.nav_lane_positioning_direction = TurnDirection.none
      self.nav_lane_positioning_enabled = False
      return

    # Check if navigation wants to send lane positioning desires
    if nav_state.active and nav_state.shouldSendLanePositioning:
      # Convert capnp enum integer to TurnDirection enum
      lane_pos_dir_int = nav_state.lanePositioningDirection
      if lane_pos_dir_int == TurnDirection.turnLeft:
        self.nav_lane_positioning_direction = TurnDirection.turnLeft
      elif lane_pos_dir_int == TurnDirection.turnRight:
        self.nav_lane_positioning_direction = TurnDirection.turnRight
      else:
        self.nav_lane_positioning_direction = TurnDirection.none
      self.nav_lane_positioning_enabled = True
    else:
      self.nav_lane_positioning_direction = TurnDirection.none
      self.nav_lane_positioning_enabled = False

  def get_lane_positioning_direction(self):
    """Get navigation lane positioning direction (for keepLeft/keepRight desires)."""
    if not self.enabled:
      return TurnDirection.none

    if self.nav_lane_positioning_enabled and self.nav_lane_positioning_direction != TurnDirection.none:
      return self.nav_lane_positioning_direction

    return TurnDirection.none

  def get_turn_direction(self):
    if not self.enabled:
      return TurnDirection.none

    # Navigation turn desires take priority over blinker-based turn desires
    if self.nav_enabled and self.nav_turn_direction != TurnDirection.none:
      return self.nav_turn_direction

    return self.turn_direction
