#!/usr/bin/env python3
"""
Copyright ©️ Project Teal Lvbs Licensed Under MIT License
"""
import json
import math
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import requests

from cereal import messaging, log
from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog

# ============================================================================
# MAPBOX API TOKEN - Set your token here for quick setup
# Get your token from: https://account.mapbox.com/access-tokens/
# This is the same token used in navd.py
# ============================================================================
DEFAULT_MAPBOX_TOKEN = "pk.eyJ1IjoidGVhbDIiLCJhIjoiY205Znl1dXBnMXF2eTJrcTFvcnF0NTNnaiJ9.trElYJImmMd1Aie0n3gOMQ"  # <-- PUT YOUR MAPBOX TOKEN HERE
# ============================================================================


HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>openpilot Navigation</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            background-color: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            margin-bottom: 30px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            color: #666;
            font-weight: bold;
        }
        input[type="text"] {
            width: 100%;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 5px;
            font-size: 16px;
            box-sizing: border-box;
        }
        button {
            background-color: #4CAF50;
            color: white;
            padding: 15px 30px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
            margin-right: 10px;
        }
        button:hover {
            background-color: #45a049;
        }
        .cancel-btn {
            background-color: #f44336;
        }
        .cancel-btn:hover {
            background-color: #da190b;
        }
        .status {
            margin-top: 20px;
            padding: 15px;
            border-radius: 5px;
            display: none;
        }
        .status.success {
            background-color: #d4edda;
            color: #155724;
            display: block;
        }
        .status.error {
            background-color: #f8d7da;
            color: #721c24;
            display: block;
        }
        .help-text {
            font-size: 14px;
            color: #999;
            margin-top: 5px;
        }
        .tab-buttons {
            margin-bottom: 20px;
        }
        .tab-button {
            background-color: #e0e0e0;
            color: #333;
            padding: 10px 20px;
            border: none;
            cursor: pointer;
            font-size: 16px;
        }
        .tab-button.active {
            background-color: #4CAF50;
            color: white;
        }
        .tab-content {
            display: none;
        }
        .tab-content.active {
            display: block;
        }
        .debug-refresh {
            text-align: center;
            padding: 10px;
            background-color: #e3f2fd;
            border-radius: 5px;
            margin-bottom: 20px;
            color: #1976d2;
            font-size: 14px;
        }
        .debug-section {
            margin-bottom: 20px;
            padding: 15px;
            background-color: #f8f9fa;
            border-radius: 5px;
            border-left: 4px solid #4CAF50;
        }
        .debug-header {
            font-weight: bold;
            color: #333;
            margin-bottom: 10px;
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .debug-row {
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
            font-size: 14px;
        }
        .debug-label {
            color: #666;
            font-weight: 500;
        }
        .debug-value {
            color: #333;
            font-weight: bold;
            font-family: 'Courier New', monospace;
        }
        .debug-progress-bar {
            width: 100%;
            height: 20px;
            background-color: #e0e0e0;
            border-radius: 10px;
            overflow: hidden;
            margin: 10px 0;
        }
        .debug-progress-fill {
            height: 100%;
            background-color: #4CAF50;
            transition: width 0.3s ease;
            width: 0%;
        }
        .debug-progress-text {
            text-align: center;
            font-size: 14px;
            color: #666;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Navigate on SunnyPilot</h1>

        <div class="tab-buttons">
            <button class="tab-button active" onclick="switchTab('address')">Address Search</button>
            <button class="tab-button" onclick="switchTab('coords')">Coordinates</button>
            <button class="tab-button" onclick="switchTab('debug')">Debug</button>
        </div>

        <!-- Address Search Tab -->
        <div id="address-tab" class="tab-content active">
            <form id="address-form" onsubmit="return submitAddress(event)">
                <div class="form-group">
                    <label for="address">Enter Destination Address:</label>
                    <input type="text" id="address" name="address" placeholder="e.g., 123 Main St, San Francisco, CA" required>
                    <div class="help-text">Enter a full address to search for destination</div>
                </div>
                <button type="submit">Navigate</button>
                <button type="button" class="cancel-btn" onclick="cancelNavigation()">Cancel Navigation</button>
            </form>
        </div>

        <!-- Coordinates Tab -->
        <div id="coords-tab" class="tab-content">
            <form id="coords-form" onsubmit="return submitCoords(event)">
                <div class="form-group">
                    <label for="name">Destination Name (optional):</label>
                    <input type="text" id="name" name="name" placeholder="e.g., Home, Work, etc.">
                </div>
                <div class="form-group">
                    <label for="latitude">Latitude:</label>
                    <input type="text" id="latitude" name="latitude" placeholder="e.g., 37.7749" required>
                </div>
                <div class="form-group">
                    <label for="longitude">Longitude:</label>
                    <input type="text" id="longitude" name="longitude" placeholder="e.g., -122.4194" required>
                </div>
                <button type="submit">Navigate</button>
                <button type="button" class="cancel-btn" onclick="cancelNavigation()">Cancel Navigation</button>
            </form>
        </div>

        <!-- Debug Tab -->
        <div id="debug-tab" class="tab-content">
            <div class="debug-refresh">🔄 Auto-refreshing every 1s</div>

            <div class="debug-section">
                <div class="debug-header">STATUS</div>
                <div class="debug-row">
                    <span class="debug-label">Navigation:</span>
                    <span class="debug-value" id="debug-status">○ Inactive</span>
                </div>
            </div>

            <div class="debug-section">
                <div class="debug-header">GPS POSITION</div>
                <div class="debug-row">
                    <span class="debug-label">Latitude:</span>
                    <span class="debug-value" id="debug-gps-lat">N/A</span>
                </div>
                <div class="debug-row">
                    <span class="debug-label">Longitude:</span>
                    <span class="debug-value" id="debug-gps-lon">N/A</span>
                </div>
                <div class="debug-row">
                    <span class="debug-label">Valid:</span>
                    <span class="debug-value" id="debug-gps-valid">No</span>
                </div>
            </div>

            <div class="debug-section">
                <div class="debug-header">DESTINATION</div>
                <div class="debug-row">
                    <span class="debug-label">Name:</span>
                    <span class="debug-value" id="debug-dest-name">N/A</span>
                </div>
                <div class="debug-row">
                    <span class="debug-label">Coordinates:</span>
                    <span class="debug-value" id="debug-dest-coords">N/A</span>
                </div>
                <div class="debug-row">
                    <span class="debug-label">Distance:</span>
                    <span class="debug-value" id="debug-dist-remaining">N/A</span>
                </div>
                <div class="debug-row">
                    <span class="debug-label">Time:</span>
                    <span class="debug-value" id="debug-time-remaining">N/A</span>
                </div>
            </div>

            <div class="debug-section">
                <div class="debug-header">ROUTE PROGRESS</div>
                <div class="debug-row">
                    <span class="debug-label">Segment:</span>
                    <span class="debug-value" id="debug-segment">N/A</span>
                </div>
                <div class="debug-progress-bar">
                    <div class="debug-progress-fill" id="debug-progress"></div>
                </div>
                <div class="debug-progress-text" id="debug-progress-text">0%</div>
            </div>

            <div class="debug-section">
                <div class="debug-header">NEXT MANEUVER</div>
                <div class="debug-row">
                    <span class="debug-label">Type:</span>
                    <span class="debug-value" id="debug-maneuver-type">N/A</span>
                </div>
                <div class="debug-row">
                    <span class="debug-label">Direction:</span>
                    <span class="debug-value" id="debug-maneuver-dir">N/A</span>
                </div>
                <div class="debug-row">
                    <span class="debug-label">Distance:</span>
                    <span class="debug-value" id="debug-maneuver-dist">N/A</span>
                </div>
                <div class="debug-row">
                    <span class="debug-label">Description:</span>
                    <span class="debug-value" id="debug-maneuver-desc">N/A</span>
                </div>
            </div>

            <div class="debug-section">
                <div class="debug-header">TURN DESIRES</div>
                <div class="debug-row">
                    <span class="debug-label">Active:</span>
                    <span class="debug-value" id="debug-turn-active">No</span>
                </div>
                <div class="debug-row">
                    <span class="debug-label">Direction:</span>
                    <span class="debug-value" id="debug-turn-dir">None</span>
                </div>
            </div>

            <div class="debug-section">
                <div class="debug-header">SPEED TARGET</div>
                <div class="debug-row">
                    <span class="debug-label">Target:</span>
                    <span class="debug-value" id="debug-speed-target">N/A</span>
                </div>
                <div class="debug-row">
                    <span class="debug-label">Valid:</span>
                    <span class="debug-value" id="debug-speed-valid">No</span>
                </div>
            </div>
        </div>

        <div id="status" class="status"></div>
    </div>

    <script>
        let debugInterval = null;

        function switchTab(tab) {
            // Hide all tabs
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-button').forEach(b => b.classList.remove('active'));

            // Stop debug polling if switching away from debug tab
            if (debugInterval) {
                clearInterval(debugInterval);
                debugInterval = null;
            }

            // Show selected tab
            if (tab === 'address') {
                document.getElementById('address-tab').classList.add('active');
                document.querySelectorAll('.tab-button')[0].classList.add('active');
            } else if (tab === 'coords') {
                document.getElementById('coords-tab').classList.add('active');
                document.querySelectorAll('.tab-button')[1].classList.add('active');
            } else if (tab === 'debug') {
                document.getElementById('debug-tab').classList.add('active');
                document.querySelectorAll('.tab-button')[2].classList.add('active');
                // Start debug polling
                updateDebugPanel(); // Immediate update
                debugInterval = setInterval(updateDebugPanel, 1000); // Update every 1 second
            }
        }

        async function updateDebugPanel() {
            try {
                const response = await fetch('/nav_status');
                const status = await response.json();

                // Update STATUS
                document.getElementById('debug-status').textContent = status.active ? '● Active' : '○ Inactive';
                document.getElementById('debug-status').style.color = status.active ? '#4CAF50' : '#999';

                // Update GPS POSITION
                document.getElementById('debug-gps-lat').textContent = (status.gps_lat != null) ? status.gps_lat.toFixed(6) : 'N/A';
                document.getElementById('debug-gps-lon').textContent = (status.gps_lon != null) ? status.gps_lon.toFixed(6) : 'N/A';
                document.getElementById('debug-gps-valid').textContent = status.gps_valid ? 'Yes' : 'No';

                // Update DESTINATION
                document.getElementById('debug-dest-name').textContent = status.dest_name || 'N/A';
                document.getElementById('debug-dest-coords').textContent =
                    (status.dest_lat != null && status.dest_lon != null)
                    ? `${status.dest_lat.toFixed(6)}, ${status.dest_lon.toFixed(6)}`
                    : 'N/A';
                document.getElementById('debug-dist-remaining').textContent =
                    (status.distance_remaining != null)
                    ? `${status.distance_remaining.toFixed(0)}m (${(status.distance_remaining * 0.000621371).toFixed(2)}mi)`
                    : 'N/A';
                document.getElementById('debug-time-remaining').textContent =
                    (status.time_remaining != null)
                    ? `${Math.floor(status.time_remaining / 60)}min ${Math.floor(status.time_remaining % 60)}s`
                    : 'N/A';

                // Update ROUTE PROGRESS
                document.getElementById('debug-segment').textContent =
                    (status.current_segment != null && status.total_segments != null)
                    ? `${status.current_segment + 1} / ${status.total_segments}`
                    : 'N/A';

                if (status.current_segment != null && status.total_segments != null && status.total_segments > 0) {
                    const progress = ((status.current_segment + 1) / status.total_segments) * 100;
                    document.getElementById('debug-progress').style.width = progress + '%';
                    document.getElementById('debug-progress-text').textContent = Math.round(progress) + '%';
                } else {
                    document.getElementById('debug-progress').style.width = '0%';
                    document.getElementById('debug-progress-text').textContent = '0%';
                }

                // Update NEXT MANEUVER
                const maneuverTypes = ['none', 'turn', 'exit', 'merge', 'fork', 'continue', 'arrive', 'roundabout'];
                const maneuverDirs = ['none', 'left', 'right'];  // TurnDirection enum: none=0, turnLeft=1, turnRight=2

                document.getElementById('debug-maneuver-type').textContent =
                    status.next_maneuver_valid ? (maneuverTypes[status.next_maneuver_type] || 'unknown') : 'N/A';
                document.getElementById('debug-maneuver-dir').textContent =
                    status.next_maneuver_valid ? (maneuverDirs[status.next_maneuver_direction] || 'unknown') : 'N/A';
                document.getElementById('debug-maneuver-dist').textContent =
                    (status.next_maneuver_valid && status.next_maneuver_distance != null) ? `${status.next_maneuver_distance.toFixed(0)}m` : 'N/A';
                document.getElementById('debug-maneuver-desc').textContent =
                    status.next_maneuver_valid ? (status.next_maneuver_description || 'N/A') : 'N/A';

                // Update TURN DESIRES
                const turnDirs = ['none', 'left', 'right'];
                const turnDir = (status.turn_desire_direction != null) ? (turnDirs[status.turn_desire_direction] || 'unknown') : 'none';
                document.getElementById('debug-turn-active').textContent = status.turn_desire_active ? `Yes - ${turnDir.toUpperCase()}` : 'No';
                document.getElementById('debug-turn-active').style.color = status.turn_desire_active ? '#f44336' : '#999';
                document.getElementById('debug-turn-dir').textContent = turnDir;

                // Update SPEED TARGET
                document.getElementById('debug-speed-target').textContent =
                    (status.target_speed_valid && status.target_speed != null)
                    ? `${status.target_speed.toFixed(1)} m/s (${(status.target_speed * 2.23694).toFixed(0)} mph)`
                    : 'N/A';
                document.getElementById('debug-speed-valid').textContent = status.target_speed_valid ? 'Yes' : 'No';

            } catch (error) {
                console.error('Failed to update debug panel:', error);
            }
        }

        function showStatus(message, isSuccess) {
            const status = document.getElementById('status');
            status.textContent = message;
            status.className = 'status ' + (isSuccess ? 'success' : 'error');
            setTimeout(() => {
                status.className = 'status';
            }, 5000);
        }

        async function submitAddress(event) {
            event.preventDefault();
            const address = document.getElementById('address').value;

            showStatus('Searching for address...', true);

            try {
                const response = await fetch('/set_destination_address', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                    body: 'address=' + encodeURIComponent(address)
                });

                const result = await response.json();

                if (result.success) {
                    showStatus('Navigation started to: ' + result.name, true);
                } else {
                    showStatus('Error: ' + result.error, false);
                }
            } catch (error) {
                showStatus('Failed to set destination: ' + error, false);
            }

            return false;
        }

        async function submitCoords(event) {
            event.preventDefault();
            const name = document.getElementById('name').value || 'Custom Location';
            const lat = parseFloat(document.getElementById('latitude').value);
            const lon = parseFloat(document.getElementById('longitude').value);

            if (isNaN(lat) || isNaN(lon)) {
                showStatus('Invalid coordinates', false);
                return false;
            }

            try {
                const response = await fetch('/set_destination', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({name: name, latitude: lat, longitude: lon})
                });

                const result = await response.json();

                if (result.success) {
                    showStatus('Navigation started to: ' + name, true);
                } else {
                    showStatus('Error: ' + result.error, false);
                }
            } catch (error) {
                showStatus('Failed to set destination: ' + error, false);
            }

            return false;
        }

        async function cancelNavigation() {
            try {
                const response = await fetch('/cancel_navigation', {method: 'POST'});
                const result = await response.json();

                if (result.success) {
                    showStatus('Navigation cancelled', true);
                } else {
                    showStatus('Error: ' + result.error, false);
                }
            } catch (error) {
                showStatus('Failed to cancel navigation: ' + error, false);
            }
        }
    </script>
</body>
</html>
"""


class NavigationWebServer(BaseHTTPRequestHandler):
    params = Params()

    def do_GET(self):
        """Handle GET requests."""
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode())
        elif self.path == '/nav_status':
            self._handle_nav_status()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        """Handle POST requests."""
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)

        if self.path == '/set_destination':
            self._handle_set_destination(post_data)
        elif self.path == '/set_destination_address':
            self._handle_set_destination_address(post_data)
        elif self.path == '/cancel_navigation':
            self._handle_cancel_navigation()
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_set_destination(self, post_data):
        """Handle direct coordinate destination setting."""
        try:
            data = json.loads(post_data.decode('utf-8'))
            name = data.get('name', 'Custom Location')
            latitude = data.get('latitude')
            longitude = data.get('longitude')

            if latitude is None or longitude is None:
                self._send_json_response({'success': False, 'error': 'Missing coordinates'})
                return

            # Set destination parameter
            destination = {
                'name': name,
                'latitude': latitude,
                'longitude': longitude
            }

            self.params.put("NavigationDestination", json.dumps(destination))

            cloudlog.info(f"navd: Web UI set destination to {name} ({latitude}, {longitude})")

            self._send_json_response({'success': True, 'name': name})

        except Exception as e:
            cloudlog.exception(f"navd: Error setting destination: {e}")
            self._send_json_response({'success': False, 'error': str(e)})

    def _handle_set_destination_address(self, post_data):
        """Handle address-based destination setting using geocoding."""
        try:
            # Parse form data
            parsed = parse_qs(post_data.decode('utf-8'))
            address = parsed.get('address', [''])[0]

            if not address:
                self._send_json_response({'success': False, 'error': 'No address provided'})
                return

            # Get Mapbox token - try parameter first, then use default
            mapbox_token = self.params.get("MapboxToken")
            if not mapbox_token and DEFAULT_MAPBOX_TOKEN:
                mapbox_token = DEFAULT_MAPBOX_TOKEN
            elif not mapbox_token:
                self._send_json_response({'success': False, 'error': 'Mapbox token not configured. Set DEFAULT_MAPBOX_TOKEN in web_server.py'})
                return

            # Geocode address using Mapbox Geocoding API
            geocode_url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{requests.utils.quote(address)}.json"
            params = {
                'access_token': mapbox_token,
                'limit': 1,
                'types': 'address,poi,place'
            }

            response = requests.get(geocode_url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            results = data.get('features', [])

            if not results:
                self._send_json_response({'success': False, 'error': 'Address not found'})
                return

            result = results[0]
            # Mapbox returns [lon, lat]
            longitude, latitude = result['center']
            display_name = result.get('place_name', address)

            # Set destination parameter
            destination = {
                'name': display_name,
                'latitude': latitude,
                'longitude': longitude
            }

            self.params.put("NavigationDestination", json.dumps(destination))

            cloudlog.info(f"navd: Web UI set destination via address: {display_name} ({latitude}, {longitude})")

            self._send_json_response({'success': True, 'name': display_name})

        except requests.RequestException as e:
            cloudlog.exception(f"navd: Mapbox geocoding request failed: {e}")
            self._send_json_response({'success': False, 'error': 'Mapbox geocoding service unavailable'})
        except Exception as e:
            cloudlog.exception(f"navd: Error setting destination from address: {e}")
            self._send_json_response({'success': False, 'error': str(e)})

    def _handle_cancel_navigation(self):
        """Handle navigation cancellation."""
        try:
            # Clear destination parameter
            self.params.remove("NavigationDestination")
            self.params.put_bool("NavigationActive", False)

            cloudlog.info("navd: Web UI cancelled navigation")

            self._send_json_response({'success': True})

        except Exception as e:
            cloudlog.exception(f"navd: Error cancelling navigation: {e}")
            self._send_json_response({'success': False, 'error': str(e)})

    def _handle_nav_status(self):
        """Return current navigation status as JSON."""
        try:
            # Subscribe to messages with short timeout
            sm = messaging.SubMaster(['navStateSP', 'liveLocationKalman'], poll='navStateSP')
            sm.update(timeout=100)  # 100ms timeout

            # Read params
            nav_active = self.params.get_bool("NavigationActive")
            dest_json = self.params.get("NavigationDestination")

            # Parse destination if available
            destination = None
            if dest_json:
                try:
                    destination = json.loads(dest_json)
                except:
                    pass

            # Build status response
            status = {
                'active': nav_active,
                'gps_valid': False,
                'gps_lat': None,
                'gps_lon': None,
                'dest_name': None,
                'dest_lat': None,
                'dest_lon': None,
                'distance_remaining': None,
                'time_remaining': None,
                'current_segment': None,
                'total_segments': None,
                'next_maneuver_valid': False,
                'next_maneuver_type': None,
                'next_maneuver_direction': None,
                'next_maneuver_distance': None,
                'next_maneuver_description': None,
                'turn_desire_active': False,
                'turn_desire_direction': None,
                'target_speed_valid': False,
                'target_speed': None,
            }

            # Get GPS position
            if sm.alive['liveLocationKalman']:
                location = sm['liveLocationKalman']
                if location.status == log.LiveLocationKalman.Status.valid and location.positionGeodetic.valid:
                    status['gps_valid'] = True
                    status['gps_lat'] = location.positionGeodetic.value[0]
                    status['gps_lon'] = location.positionGeodetic.value[1]

            # Get destination info from params
            if destination:
                status['dest_name'] = destination.get('name')
                status['dest_lat'] = destination.get('latitude')
                status['dest_lon'] = destination.get('longitude')

            # Get navigation state if available
            if sm.alive['navStateSP']:
                nav = sm['navStateSP']
                if nav.active:
                    status['distance_remaining'] = nav.distanceRemaining
                    status['time_remaining'] = nav.timeRemaining
                    status['current_segment'] = nav.currentSegmentIndex
                    status['total_segments'] = nav.totalSegments

                    if nav.nextManeuverValid:
                        status['next_maneuver_valid'] = True
                        status['next_maneuver_type'] = nav.nextManeuverType
                        status['next_maneuver_direction'] = nav.nextManeuverDirection
                        status['next_maneuver_distance'] = nav.nextManeuverDistance
                        status['next_maneuver_description'] = nav.nextManeuverDescription

                    status['turn_desire_active'] = nav.shouldSendTurnDesire
                    status['turn_desire_direction'] = nav.turnDesireDirection

                    if nav.targetSpeedValid:
                        status['target_speed_valid'] = True
                        status['target_speed'] = nav.targetSpeed

            self._send_json_response(status)

        except Exception as e:
            cloudlog.exception(f"navd: Error getting nav status: {e}")
            self._send_json_response({'error': str(e)})

    def _send_json_response(self, data):
        """Send JSON response."""
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        """Override to use cloudlog instead of printing to stdout."""
        cloudlog.info(f"navd web: {format % args}")


def main():
    port = 8083
    server = HTTPServer(('0.0.0.0', port), NavigationWebServer)
    cloudlog.info(f"navd: Web server started on http://0.0.0.0:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        cloudlog.info("navd: Web server stopped")
        server.shutdown()


if __name__ == "__main__":
    main()
