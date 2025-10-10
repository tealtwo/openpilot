#!/usr/bin/env python3
"""
Quick script to monitor navigation status.
Run this on your Comma 3X to see if navigation is working.
"""

import time
from cereal import messaging

def main():
    sm = messaging.SubMaster(['navStateSP'])

    print("=== Navigation Monitor ===")
    print("Watching for navigation state...\n")

    while True:
        sm.update(0)

        if sm.updated['navStateSP']:
            nav = sm['navStateSP']

            print(f"\r[{time.strftime('%H:%M:%S')}]", end=" ")

            if nav.active:
                print(f"ACTIVE | ", end="")
                print(f"Dest: {nav.destinationName[:30]:30s} | ", end="")
                print(f"Dist: {nav.distanceRemaining:6.0f}m | ", end="")
                print(f"Time: {nav.timeRemaining/60:4.1f}min | ", end="")

                if nav.nextManeuverValid:
                    print(f"Next: {nav.nextManeuverDistance:5.0f}m | ", end="")
                    print(f"Desire: {nav.shouldSendTurnDesire} ", end="")
                else:
                    print("No maneuver ", end="")

                if nav.targetSpeedValid:
                    print(f"| Speed: {nav.targetSpeed*2.237:.0f}mph", end="")
            else:
                print("INACTIVE - No destination set", end="")

            print(" " * 20, end="")  # Clear rest of line

        time.sleep(0.2)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nMonitor stopped.")
