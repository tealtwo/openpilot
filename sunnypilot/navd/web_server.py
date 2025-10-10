#!/usr/bin/env python3
"""
Copyright ©️ Project Teal Lvbs Licensed Under MIT License
"""
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import requests

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
    </style>
</head>
<body>
    <div class="container">
        <h1>🗺️ openpilot Navigation</h1>

        <div class="tab-buttons">
            <button class="tab-button active" onclick="switchTab('address')">Address Search</button>
            <button class="tab-button" onclick="switchTab('coords')">Coordinates</button>
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

        <div id="status" class="status"></div>
    </div>

    <script>
        function switchTab(tab) {
            // Hide all tabs
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-button').forEach(b => b.classList.remove('active'));

            // Show selected tab
            if (tab === 'address') {
                document.getElementById('address-tab').classList.add('active');
                document.querySelectorAll('.tab-button')[0].classList.add('active');
            } else {
                document.getElementById('coords-tab').classList.add('active');
                document.querySelectorAll('.tab-button')[1].classList.add('active');
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
