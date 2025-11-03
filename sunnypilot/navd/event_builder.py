#!/usr/bin/env python3
"""
Copyright ©️ Project Teal Lvbs Licensed Under MIT License
"""
from cereal import custom, messaging
from openpilot.common.constants import CV

SHORT_DISTANCE_METERS = 200.0
QUARTER_MILE = 402.336
METERS_TO_KILO = 1000
METERS_TO_MILE = 1609.344
METERS_TO_FEET = 3.280839895


class EventBuilder:
  @staticmethod
  def _build_banner_message(metric: bool, nav_state) -> str:
    if not nav_state.nextManeuverValid:
      return ""

    distance = nav_state.nextManeuverDistance
    instruction = nav_state.nextManeuverDescription
    maneuver_type = nav_state.nextManeuverType

    # Format distance
    if metric:
      if distance < SHORT_DISTANCE_METERS:
        dist = f'{int(distance)}m'
      else:
        dist = f'{distance / METERS_TO_KILO:.1f} km'
    else:
      if distance < QUARTER_MILE:
        dist = f'{round((distance * METERS_TO_FEET) / 50) * 50}ft'
      else:
        dist = f'{distance / METERS_TO_MILE:.1f} mi'
    if maneuver_type == custom.NavStateSP.ManeuverType.arrive:
      return instruction
    elif any(keyword in instruction for keyword in ['Continue', 'Drive', 'Head']):
      return f'For {dist}, {instruction}'
    elif any(keyword in instruction for keyword in ['Turn', 'Take', 'Make', 'Exit']):
      return f'In {dist}, {instruction}'
    else:
      return f'For {dist}, Continue - {instruction}'

  @staticmethod
  def build_navigation_banner_message(sm: messaging.SubMaster, metric: bool = True) -> str:
    nav_state = sm['navStateSP']
    if not nav_state.active or not nav_state.nextManeuverValid:
      return ""
    banner_message = EventBuilder._build_banner_message(metric, nav_state)

    return banner_message
