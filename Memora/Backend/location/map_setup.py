"""
A real, visual way to set the Safe Zone: opens a local map in the
family's browser (OpenStreetMap/Leaflet) so they click the patient's
home location and drag the radius, instead of typing raw lat/lon
numbers into the terminal.

This is still 100% local/offline for the app itself - it only starts a
tiny local web server on 127.0.0.1 for the map page, controlled
entirely from the terminal app. It is NOT the old Flutter mobile
backend; it just gives the terminal app a way to show a real map.

Usage (from main.py):

    from location.map_setup import pick_safe_zone_on_map
    config = pick_safe_zone_on_map(patient_id)
    if config:
        print(config)   # {"center_lat": ..., "center_lon": ..., "radius_meters": ...}
"""

import threading
import webbrowser

from flask import Flask, request, jsonify
from werkzeug.serving import make_server

from database.safe_zone_store import SafeZoneStore

# Default map center (Cairo) - only used if this account has no safe
# zone saved yet.
DEFAULT_LAT = 30.0444
DEFAULT_LON = 31.2357

PAGE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>MEMORA - Set Safe Zone</title>
    <meta charset="utf-8" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 0; }}
        #map {{ height: 80vh; width: 100%; }}
        #controls {{ padding: 15px; background: #f5f5f5; }}
        button {{ padding: 10px 20px; font-size: 16px; background: #6a5acd; color: white;
                  border: none; border-radius: 8px; cursor: pointer; }}
        #status {{ margin-top: 10px; font-weight: bold; }}
    </style>
</head>
<body>
    <div id="controls">
        <h2>Click on the map to set the Home / Safe Zone center</h2>
        <label>Radius (meters): <input type="range" id="radius" min="50" max="3000" value="{default_radius}"
               oninput="updateRadius(this.value)"></label>
        <span id="radiusValue">{default_radius}</span> m
        <br><br>
        <button onclick="saveZone()">Save Safe Zone</button>
        <div id="status"></div>
    </div>
    <div id="map"></div>

    <script>
        var map = L.map('map').setView([{default_lat}, {default_lon}], 15);

        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: 'OpenStreetMap contributors'
        }}).addTo(map);

        var marker = null;
        var circle = null;
        var currentLat = {default_lat};
        var currentLon = {default_lon};
        var currentRadius = {default_radius};
        var hasExisting = {has_existing};

        if (hasExisting) {{
            marker = L.marker([currentLat, currentLon]).addTo(map);
            circle = L.circle([currentLat, currentLon], {{ radius: currentRadius }}).addTo(map);
        }}

        function updateRadius(value) {{
            currentRadius = parseInt(value);
            document.getElementById('radiusValue').innerText = value;
            if (circle) {{
                circle.setRadius(currentRadius);
            }}
        }}

        map.on('click', function(e) {{
            currentLat = e.latlng.lat;
            currentLon = e.latlng.lng;

            if (marker) {{ map.removeLayer(marker); }}
            if (circle) {{ map.removeLayer(circle); }}

            marker = L.marker([currentLat, currentLon]).addTo(map);
            circle = L.circle([currentLat, currentLon], {{ radius: currentRadius }}).addTo(map);
        }});

        function saveZone() {{
            if (!marker) {{
                document.getElementById('status').innerText = "Please click on the map first.";
                return;
            }}

            fetch('/save', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{
                    lat: currentLat,
                    lon: currentLon,
                    radius: currentRadius
                }})
            }})
            .then(response => response.json())
            .then(data => {{
                document.getElementById('status').innerText =
                    "Saved! You can go back to the terminal now (this tab will close).";
                setTimeout(function() {{ window.close(); }}, 1500);
            }});
        }}
    </script>
</body>
</html>
"""


def _build_app(save_event, result_holder, patient_id):
    app = Flask(__name__)
    app.logger.disabled = True

    store = SafeZoneStore()
    existing = store.get(patient_id)
    default_lat = existing["center_lat"] if existing else DEFAULT_LAT
    default_lon = existing["center_lon"] if existing else DEFAULT_LON
    default_radius = int(existing["radius_meters"]) if existing else 500

    @app.route("/")
    def index():
        return PAGE_HTML.format(
            default_lat=default_lat,
            default_lon=default_lon,
            default_radius=default_radius,
            has_existing="true" if existing else "false",
        )

    @app.route("/save", methods=["POST"])
    def save():
        data = request.get_json()

        center_lat = data["lat"]
        center_lon = data["lon"]
        radius_meters = data["radius"]

        store.save(patient_id, center_lat, center_lon, radius_meters)

        result_holder["config"] = {
            "center_lat": center_lat,
            "center_lon": center_lon,
            "radius_meters": radius_meters,
        }
        save_event.set()

        return jsonify({"status": "ok"})

    return app


def pick_safe_zone_on_map(patient_id, timeout=300):
    """
    Opens a local map in the default browser so the family can click the
    patient's home location and drag the safe-zone radius visually, for
    this specific account (patient_id). Saved straight into the shared
    SQLite database, scoped to this account.

    Blocks (with the terminal free to show a waiting message) until the
    family clicks "Save Safe Zone" in the browser, or `timeout` seconds
    pass with nothing saved.

    Returns the saved config dict {"center_lat", "center_lon",
    "radius_meters"}, or None if nothing was saved in time.
    """
    save_event = threading.Event()
    result_holder = {}

    app = _build_app(save_event, result_holder, patient_id)
    server = make_server("127.0.0.1", 0, app)
    port = server.server_port

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    url = f"http://127.0.0.1:{port}/"

    print(f"\nOpening the map in your browser: {url}")
    print("Click on the map for the patient's home location, adjust the radius slider, "
          "then press 'Save Safe Zone'.")
    print("(Waiting for you to save... this will time out after "
          f"{timeout} seconds if nothing is saved.)")

    webbrowser.open(url)

    saved = save_event.wait(timeout)

    server.shutdown()
    thread.join(timeout=5)

    if not saved:
        print("No safe zone was saved (timed out, or the browser tab was closed).")
        return None

    return result_holder.get("config")
