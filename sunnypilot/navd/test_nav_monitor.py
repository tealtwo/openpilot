#!/usr/bin/env python3
"""
Quick script to monitor navigation status.
Run this on your Comma 3X to see if navigation is working.
"""

import time
from cereal import messaging
from openpilot.common.swaglog import cloudlog

def main():
    sm = messaging.SubMaster(['navStateSP'])

    print("=== Navigation Monitor Started ===")
    print("Watching for navigation state...\n")

    last_log_time = 0
    LOG_INTERVAL = 2.0  # Log every 2 seconds to avoid spam

    while True:
        sm.update(0)

        current_time = time.monotonic()

        # Log periodically or when state changes
        if current_time - last_log_time >= LOG_INTERVAL:
            print(f"DEBUG: valid={sm.valid['navStateSP']}, updated={sm.updated['navStateSP']}, " +
                  f"alive={sm.alive['navStateSP']}, freq_ok={sm.freq_ok['navStateSP']}")

            if sm.valid['navStateSP']:
                nav = sm['navStateSP']

                if nav.active:
                    status = f"NAV ACTIVE | Dest: {nav.destinationName} | Dist: {nav.distanceRemaining:.0f}m | Time: {nav.timeRemaining/60:.1f}min"

                    if nav.nextManeuverValid:
                        status += f" | Next: {nav.nextManeuverDistance:.0f}m | Turn Desire: {nav.shouldSendTurnDesire}"

                    if nav.targetSpeedValid:
                        status += f" | Target Speed: {nav.targetSpeed*2.237:.0f}mph"

                    print(f"✓ {status}")
                    cloudlog.info(f"nav_monitor: {status}")
                else:
                    print("✓ INACTIVE - No destination set")
                    cloudlog.info("nav_monitor: INACTIVE - No destination set")
            else:
                # Show what we CAN read even if not valid
                nav = sm['navStateSP']
                print(f"✗ NOT VALID - but active={nav.active}, dest={nav.destinationName}")
                cloudlog.warning("nav_monitor: navStateSP not valid - is navd running?")

            last_log_time = current_time

        time.sleep(0.2)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        cloudlog.info("nav_monitor: Monitor stopped by user")
