#!/usr/bin/env python3
"""
Helper script to set Mapbox API token for navigation.

Usage:
    python set_mapbox_token.py YOUR_MAPBOX_TOKEN

Or run interactively:
    python set_mapbox_token.py
"""
# Why tf does this file exist, just set it in navd.py
import sys
from openpilot.common.params import Params

def main():
    params = Params()

    if len(sys.argv) > 1:
        # Token provided as argument
        token = sys.argv[1]
    else:
        # Interactive mode
        print("=" * 60)
        print("Mapbox API Token Setup for openpilot Navigation")
        print("=" * 60)
        print("\nGet your Mapbox token from: https://account.mapbox.com/access-tokens/")
        print("You need a token with the following scopes:")
        print("  - Navigation Downloads API")
        print("  - Geocoding API")
        print("\n")
        token = input("Enter your Mapbox API token: ").strip()

    if not token:
        print("Error: No token provided")
        sys.exit(1)

    # Validate token format (basic check)
    if not token.startswith("pk.") and not token.startswith("sk."):
        print("Warning: Token doesn't appear to be a valid Mapbox token (should start with 'pk.' or 'sk.')")
        response = input("Continue anyway? (y/N): ").strip().lower()
        if response != 'y':
            print("Cancelled.")
            sys.exit(1)

    # Set the token
    params.put("MapboxToken", token)

    print("\n✅ Mapbox token saved successfully!")
    print("\nYou can now use navigation:")
    print("  1. Open http://<device-ip>:8083 in your browser")
    print("  2. Enter a destination address or coordinates")
    print("  3. Click 'Navigate'")
    print("\nThe token is stored in: /data/params/d/MapboxToken")
    print("\nTo remove the token later:")
    print("  rm /data/params/d/MapboxToken")

if __name__ == "__main__":
    main()
