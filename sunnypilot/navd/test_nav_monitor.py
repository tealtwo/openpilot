#!/usr/bin/env python3
"""
Quick script to monitor navigation status.
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

    # Track initial distance for progress calculation
    initial_distance = None
    last_destination = ""

    while True:
        sm.update(0)

        current_time = time.monotonic()

        # Log periodically or when state changes
        if current_time - last_log_time >= LOG_INTERVAL:
            # Use alive check since valid might be strict
            if sm.alive['navStateSP']:
                nav = sm['navStateSP']

                if nav.active:
                    # Reset initial distance if destination changed
                    if nav.destinationName != last_destination:
                        initial_distance = nav.distanceRemaining
                        last_destination = nav.destinationName

                    # Calculate progress percentage
                    progress = 0.0
                    if initial_distance and initial_distance > 0:
                        progress = ((initial_distance - nav.distanceRemaining) / initial_distance) * 100
                        progress = max(0, min(100, progress))  # Clamp to 0-100%
                        progress_bar = "█" * int(progress / 5) + "░" * (20 - int(progress / 5))
                        status = f"🚗 [{progress_bar}] {progress:.1f}% | {nav.destinationName}"
                    else:
                        status = f"🚗 Starting... | {nav.destinationName}"

                    status += f"\n   Remaining: {nav.distanceRemaining:.0f}m ({nav.timeRemaining/60:.1f}min)"

                    if nav.nextManeuverValid:
                        status += f"\n   Next Turn: {nav.nextManeuverDistance:.0f}m"
                        if nav.shouldSendTurnDesire:
                            status += f" 🔄 TURNING"

                    if nav.targetSpeedValid:
                        status += f"\n   Target Speed: {nav.targetSpeed*2.237:.0f}mph"

                    print(f"{status}\n")
                    cloudlog.info(f"nav_monitor: Progress {progress:.1f}% - {nav.distanceRemaining:.0f}m remaining")
                else:
                    print("⏸ INACTIVE - No destination set\n")
                    initial_distance = None
                    last_destination = ""
                    cloudlog.info("nav_monitor: INACTIVE")
            else:
                print("❌ navStateSP not available - is navd running?\n")
                cloudlog.warning("nav_monitor: navStateSP not available")

            last_log_time = current_time

        time.sleep(0.2)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        cloudlog.info("nav_monitor: Monitor stopped by user")
