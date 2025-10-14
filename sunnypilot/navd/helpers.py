from __future__ import annotations

import json
import math
import numpy as np
from enum import Enum
from typing import Any, cast

from openpilot.common.constants import CV
from openpilot.common.params import Params

DIRECTIONS = ('left', 'right', 'straight')
MODIFIABLE_DIRECTIONS = ('left', 'right')


class LanePosition(Enum):
  """Current lane position based on visible lane lines."""
  LEFT_LANE = "left"       # Only right lane line visible
  MIDDLE_LANE = "middle"   # Both lane lines visible
  RIGHT_LANE = "right"     # Only left lane line visible
  UNKNOWN = "unknown"      # Cannot determine (no visible lane lines)

EARTH_MEAN_RADIUS = 6371007.2
SPEED_CONVERSIONS = {
  'km/h': CV.KPH_TO_MS,
  'mph': CV.MPH_TO_MS,
}


class Coordinate:
  def __init__(self, latitude: float, longitude: float) -> None:
    self.latitude = latitude
    self.longitude = longitude
    self.annotations: dict[str, float] = {}

  @classmethod
  def from_mapbox_tuple(cls, t: tuple[float, float]) -> Coordinate:
    return cls(t[1], t[0])

  def as_dict(self) -> dict[str, float]:
    return {'latitude': self.latitude, 'longitude': self.longitude}

  def __str__(self) -> str:
    return f'Coordinate({self.latitude}, {self.longitude})'

  def __repr__(self) -> str:
    return self.__str__()

  def __eq__(self, other) -> bool:
    if not isinstance(other, Coordinate):
      return False
    return (self.latitude == other.latitude) and (self.longitude == other.longitude)

  def __sub__(self, other: Coordinate) -> Coordinate:
    return Coordinate(self.latitude - other.latitude, self.longitude - other.longitude)

  def __add__(self, other: Coordinate) -> Coordinate:
    return Coordinate(self.latitude + other.latitude, self.longitude + other.longitude)

  def __mul__(self, c: float) -> Coordinate:
    return Coordinate(self.latitude * c, self.longitude * c)

  def dot(self, other: Coordinate) -> float:
    return self.latitude * other.latitude + self.longitude * other.longitude

  def distance_to(self, other: Coordinate) -> float:
    # Haversine formula
    dlat = math.radians(other.latitude - self.latitude)
    dlon = math.radians(other.longitude - self.longitude)

    haversine_dlat = math.sin(dlat / 2.0)
    haversine_dlat *= haversine_dlat
    haversine_dlon = math.sin(dlon / 2.0)
    haversine_dlon *= haversine_dlon

    y = haversine_dlat \
        + math.cos(math.radians(self.latitude)) \
        * math.cos(math.radians(other.latitude)) \
        * haversine_dlon
    x = 2 * math.asin(math.sqrt(y))
    return x * EARTH_MEAN_RADIUS


def minimum_distance(a: Coordinate, b: Coordinate, p: Coordinate):
  if a.distance_to(b) < 0.01:
    return a.distance_to(p)

  ap = p - a
  ab = b - a
  t = np.clip(ap.dot(ab) / ab.dot(ab), 0.0, 1.0)
  projection = a + ab * t
  return projection.distance_to(p)


def distance_along_geometry(geometry: list[Coordinate], pos: Coordinate) -> float:
  if len(geometry) <= 2:
    return geometry[0].distance_to(pos)

  # 1. Find segment that is closest to current position
  # 2. Total distance is sum of distance to start of closest segment
  #    + all previous segments
  total_distance = 0.0
  total_distance_closest = 0.0
  closest_distance = 1e9

  for i in range(len(geometry) - 1):
    d = minimum_distance(geometry[i], geometry[i + 1], pos)

    if d < closest_distance:
      closest_distance = d
      total_distance_closest = total_distance + geometry[i].distance_to(pos)

    total_distance += geometry[i].distance_to(geometry[i + 1])

  return total_distance_closest


def coordinate_from_param(param: str, params: Params = None) -> Coordinate | None:
  if params is None:
    params = Params()

  json_str = params.get(param)
  if json_str is None:
    return None

  pos = json.loads(json_str)
  if 'latitude' not in pos or 'longitude' not in pos:
    return None

  return Coordinate(pos['latitude'], pos['longitude'])


def string_to_direction(direction: str) -> str:
  for d in DIRECTIONS:
    if d in direction:
      if 'slight' in direction and d in MODIFIABLE_DIRECTIONS:
        return 'slight' + d.capitalize()
      return d
  return 'none'


def maxspeed_to_ms(maxspeed: dict[str, str | float]) -> float:
  unit = cast(str, maxspeed['unit'])
  speed = cast(float, maxspeed['speed'])
  return float(SPEED_CONVERSIONS[unit] * speed)


def field_valid(dat: dict, field: str) -> bool:
  return field in dat and dat[field] is not None


def detect_lane_position(model_v2) -> LanePosition:
  """
  Detect current lane position based on visible lane lines from modelV2.

  Filters out curbs and road edges by checking if lane lines are at realistic distances.
  Typical lane width is 3-4 meters. Lane lines closer than 1.8m or farther than 5m
  are likely curbs/edges, not drivable lanes.

  Args:
    model_v2: modelV2 message with laneLineProbs and laneLines

  Returns:
    LanePosition enum indicating current lane
  """
  # Lane line probabilities:
  # Index 0: current lane
  # Index 1: left lane line
  # Index 2: right lane line
  # Index 3+: further lanes

  LANE_LINE_PROB_THRESHOLD = 0.5
  MIN_LANE_WIDTH = 1.8  # Minimum realistic lane line distance (meters)
  MAX_LANE_WIDTH = 5.0  # Maximum realistic lane line distance (meters)

  if not model_v2 or not hasattr(model_v2, 'laneLineProbs') or len(model_v2.laneLineProbs) < 3:
    return LanePosition.UNKNOWN

  # Check if we have laneLines data with position information
  if not hasattr(model_v2, 'laneLines') or len(model_v2.laneLines) < 3:
    return LanePosition.UNKNOWN

  # Get lane line probabilities
  left_lane_prob = model_v2.laneLineProbs[1]
  right_lane_prob = model_v2.laneLineProbs[2]

  # Check if lane lines meet probability threshold
  left_lane_visible = left_lane_prob > LANE_LINE_PROB_THRESHOLD
  right_lane_visible = right_lane_prob > LANE_LINE_PROB_THRESHOLD

  # Validate lane line distances to filter out curbs/edges
  # laneLines[1] = left line (negative y), laneLines[2] = right line (positive y)
  # y[0] is the lateral position at the closest point
  if left_lane_visible:
    left_lane = model_v2.laneLines[1]
    if hasattr(left_lane, 'y') and len(left_lane.y) > 0:
      left_y = left_lane.y[0]
      # Left lane line should be to the left (negative y) and within reasonable distance
      if left_y > -MIN_LANE_WIDTH or left_y < -MAX_LANE_WIDTH:
        left_lane_visible = False

  if right_lane_visible:
    right_lane = model_v2.laneLines[2]
    if hasattr(right_lane, 'y') and len(right_lane.y) > 0:
      right_y = right_lane.y[0]
      # Right lane line should be to the right (positive y) and within reasonable distance
      if right_y < MIN_LANE_WIDTH or right_y > MAX_LANE_WIDTH:
        right_lane_visible = False

  # Determine lane position based on validated lane lines
  if left_lane_visible and right_lane_visible:
    # Both lane lines visible - we're in a middle lane
    return LanePosition.MIDDLE_LANE
  elif left_lane_visible and not right_lane_visible:
    # Only left lane line visible - we're in the rightmost lane
    return LanePosition.RIGHT_LANE
  elif right_lane_visible and not left_lane_visible:
    # Only right lane line visible - we're in the leftmost lane
    return LanePosition.LEFT_LANE
  else:
    # No lane lines visible - cannot determine position
    return LanePosition.UNKNOWN


def count_visible_same_direction_lanes(model_v2) -> int:
  """
  Count number of visible same-direction lanes from modelV2.

  This is used for safety checks to prevent lane changes into oncoming traffic
  on two-way single-lane roads. The function counts validated lane lines
  (filtering out curbs and road edges) to determine if multiple same-direction
  lanes exist.

  Args:
    model_v2: modelV2 message with laneLineProbs and laneLines

  Returns:
    Number of visible lanes:
      - 2: Multiple same-direction lanes confirmed (both left and right lane lines visible)
      - 1: Single lane or uncertain (conservative default)
  """
  LANE_LINE_PROB_THRESHOLD = 0.5
  MIN_LANE_WIDTH = 1.8  # Minimum realistic lane line distance (meters)
  MAX_LANE_WIDTH = 5.0  # Maximum realistic lane line distance (meters)

  # Conservative default: assume single lane if we can't determine
  if not model_v2 or not hasattr(model_v2, 'laneLineProbs') or len(model_v2.laneLineProbs) < 3:
    return 1

  if not hasattr(model_v2, 'laneLines') or len(model_v2.laneLines) < 3:
    return 1

  # Check left lane line
  left_lane_visible = False
  if len(model_v2.laneLineProbs) > 1:
    left_lane_visible = model_v2.laneLineProbs[1] > LANE_LINE_PROB_THRESHOLD
    if left_lane_visible:
      left_lane = model_v2.laneLines[1]
      if hasattr(left_lane, 'y') and len(left_lane.y) > 0:
        left_y = left_lane.y[0]
        # Left lane line should be to the left (negative y) and within reasonable distance
        # This filters out curbs/edges
        if left_y > -MIN_LANE_WIDTH or left_y < -MAX_LANE_WIDTH:
          left_lane_visible = False

  # Check right lane line
  right_lane_visible = False
  if len(model_v2.laneLineProbs) > 2:
    right_lane_visible = model_v2.laneLineProbs[2] > LANE_LINE_PROB_THRESHOLD
    if right_lane_visible:
      right_lane = model_v2.laneLines[2]
      if hasattr(right_lane, 'y') and len(right_lane.y) > 0:
        right_y = right_lane.y[0]
        # Right lane line should be to the right (positive y) and within reasonable distance
        # This filters out curbs/edges
        if right_y < MIN_LANE_WIDTH or right_y > MAX_LANE_WIDTH:
          right_lane_visible = False

  # If both lane lines are visible and validated, we have at least 2 lanes in same direction
  # If only one or none visible, conservatively assume single lane
  if left_lane_visible and right_lane_visible:
    return 2  # Multi-lane confirmed
  else:
    return 1  # Single lane or uncertain - be conservative


def parse_banner_instructions(banners: Any, distance_to_maneuver: float = 0.0) -> dict[str, Any] | None:
  if not len(banners):
    return None

  instruction = {}

  # A segment can contain multiple banners, find one that we need to show now
  current_banner = banners[0]
  for banner in banners:
    if distance_to_maneuver < banner['distanceAlongGeometry']:
      current_banner = banner

  # Only show banner when close enough to maneuver
  instruction['showFull'] = distance_to_maneuver < current_banner['distanceAlongGeometry']

  # Primary
  p = current_banner['primary']
  if field_valid(p, 'text'):
    instruction['maneuverPrimaryText'] = p['text']
  if field_valid(p, 'type'):
    instruction['maneuverType'] = p['type']
  if field_valid(p, 'modifier'):
    instruction['maneuverModifier'] = p['modifier']

  # Secondary
  if field_valid(current_banner, 'secondary'):
    instruction['maneuverSecondaryText'] = current_banner['secondary']['text']

  # Lane lines
  if field_valid(current_banner, 'sub'):
    lanes = []
    for component in current_banner['sub']['components']:
      if component['type'] != 'lane':
        continue

      lane = {
        'active': component['active'],
        'directions': [string_to_direction(d) for d in component['directions']],
      }

      if field_valid(component, 'active_direction'):
        lane['activeDirection'] = string_to_direction(component['active_direction'])

      lanes.append(lane)
    instruction['lanes'] = lanes

  return instruction
