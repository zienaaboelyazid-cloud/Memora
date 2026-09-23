import math
import json
import os


class SafeZone:
    """
    Represents a circular safe area around a center point (e.g. home),
    and checks whether a given location is inside or outside it.
    """

    def __init__(self, center_lat, center_lon, radius_meters):
        self.center_lat = center_lat
        self.center_lon = center_lon
        self.radius_meters = radius_meters

    @classmethod
    def load_or_create(cls, config_path="data/safe_zone_config.json"):
        """
        Loads the safe zone settings from a config file if it exists.
        If it doesn't exist yet, asks the user to enter them (once),
        saves them, and returns a SafeZone built from that.
        """

        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                config = json.load(f)

            print(f"Loaded saved safe zone: {config['radius_meters']}m around "
                  f"({config['center_lat']}, {config['center_lon']})")

            return cls(config["center_lat"], config["center_lon"], config["radius_meters"])

        print("No safe zone configured yet. Let's set one up.")
        center_lat = float(input("Enter home latitude: ").strip())
        center_lon = float(input("Enter home longitude: ").strip())
        radius_meters = float(input("Enter safe zone radius in meters: ").strip())

        folder = os.path.dirname(config_path)
        if folder and not os.path.exists(folder):
            os.makedirs(folder)

        with open(config_path, "w") as f:
            json.dump({
                "center_lat": center_lat,
                "center_lon": center_lon,
                "radius_meters": radius_meters
            }, f)

        print("Safe zone saved.")
        return cls(center_lat, center_lon, radius_meters)

    def distance_from_center(self, lat, lon):
        """
        Calculates the distance (in meters) between the given location
        and the center of the safe zone, using the Haversine formula
        (accounts for the Earth's curvature).
        """

        R = 6371000  # Earth's radius in meters

        lat1_rad = math.radians(self.center_lat)
        lat2_rad = math.radians(lat)
        delta_lat = math.radians(lat - self.center_lat)
        delta_lon = math.radians(lon - self.center_lon)

        a = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    def is_inside(self, lat, lon):
        """
        Returns True if the given location is within the safe zone radius.
        """
        return self.distance_from_center(lat, lon) <= self.radius_meters

    def check_status(self, lat, lon):
        """
        Returns a dictionary describing the current status:
        whether inside the safe zone, and the distance from its center.
        """
        distance = self.distance_from_center(lat, lon)
        inside = distance <= self.radius_meters

        return {
            "inside_safe_zone": inside,
            "distance_meters": round(distance, 1)
        }