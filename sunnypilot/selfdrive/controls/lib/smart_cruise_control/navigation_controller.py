"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""

from cereal import messaging, custom
from openpilot.common.params import Params
from openpilot.common.realtime import DT_MDL
from openpilot.selfdrive.car.cruise import V_CRUISE_UNSET
from openpilot.sunnypilot import PARAMS_UPDATE_PERIOD
from openpilot.sunnypilot.selfdrive.controls.lib.smart_cruise_control import MIN_V

NavState = custom.LongitudinalPlanSP.SmartCruiseControl.MapState  # Reuse MapState enum

ACTIVE_STATES = (NavState.turning,)
ENABLED_STATES = (NavState.enabled, NavState.overriding, *ACTIVE_STATES)


class NavigationController:
    """Controls longitudinal speed based on navigation guidance."""
    v_target: float = 0
    a_target: float = 0.
    v_ego: float = 0.
    a_ego: float = 0.
    output_v_target: float = V_CRUISE_UNSET
    output_a_target: float = 0.

    def __init__(self):
        self.params = Params()
        self.enabled = self.params.get_bool("NavigationSpeedControl")
        self.long_enabled = False
        self.long_override = False
        self.is_enabled = False
        self.is_active = False
        self.state = NavState.disabled
        self.v_cruise = 0
        self.frame = -1

        # Navigation state
        self.nav_active = False
        self.nav_target_speed = 0.0
        self.nav_target_speed_valid = False

    def get_v_target_from_control(self) -> float:
        if self.is_active:
            return max(self.v_target, MIN_V)

        return V_CRUISE_UNSET

    def get_a_target_from_control(self) -> float:
        return self.a_ego

    def update_params(self):
        if self.frame % int(PARAMS_UPDATE_PERIOD / DT_MDL) == 0:
            self.enabled = self.params.get_bool("NavigationSpeedControl")

    def update_navigation_state(self, sm: messaging.SubMaster) -> None:
        """Update navigation state from navStateSP message."""
        if not sm.valid['navStateSP']:
            self.nav_active = False
            self.nav_target_speed_valid = False
            return

        nav_state = sm['navStateSP']
        self.nav_active = nav_state.active
        self.nav_target_speed_valid = nav_state.targetSpeedValid

        if self.nav_target_speed_valid:
            self.nav_target_speed = nav_state.targetSpeed
        else:
            self.nav_target_speed = 0.0

    def _update_state_machine(self) -> tuple[bool, bool]:
        # ENABLED, TURNING
        if self.state != NavState.disabled:
            if not self.long_enabled or not self.enabled or not self.nav_active:
                self.state = NavState.disabled
            elif self.long_override:
                self.state = NavState.overriding

            else:
                # ENABLED
                if self.state == NavState.enabled:
                    if self.nav_target_speed_valid and self.v_cruise > self.v_target != 0:
                        self.state = NavState.turning

                # TURNING
                elif self.state == NavState.turning:
                    if not self.nav_target_speed_valid or self.v_cruise <= self.v_target or self.v_target == 0:
                        self.state = NavState.enabled

                # OVERRIDING
                elif self.state == NavState.overriding:
                    if not self.long_override:
                        if self.nav_target_speed_valid and self.v_cruise > self.v_target != 0:
                            self.state = NavState.turning
                        else:
                            self.state = NavState.enabled

        # DISABLED
        elif self.state == NavState.disabled:
            if self.long_enabled and self.enabled and self.nav_active:
                if self.long_override:
                    self.state = NavState.overriding
                else:
                    self.state = NavState.enabled

        enabled = self.state in ENABLED_STATES
        active = self.state in ACTIVE_STATES

        return enabled, active

    def update(self, sm: messaging.SubMaster, long_enabled: bool, long_override: bool, v_ego, a_ego, v_cruise) -> None:
        self.long_enabled = long_enabled
        self.long_override = long_override
        self.v_ego = v_ego
        self.a_ego = a_ego
        self.v_cruise = v_cruise

        self.update_params()
        self.update_navigation_state(sm)

        # Set target speed from navigation
        if self.nav_target_speed_valid:
            self.v_target = self.nav_target_speed
        else:
            self.v_target = 0

        self.is_enabled, self.is_active = self._update_state_machine()

        self.output_v_target = self.get_v_target_from_control()
        self.output_a_target = self.get_a_target_from_control()

        self.frame += 1
