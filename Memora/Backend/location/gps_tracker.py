import asyncio
from winsdk.windows.devices.geolocation import Geolocator


async def _get_location_async():
    geolocator = Geolocator()
    position = await geolocator.get_geoposition_async()

    lat = position.coordinate.point.position.latitude
    lon = position.coordinate.point.position.longitude

    return lat, lon


def get_current_location():
    """
    Gets the device's current location using Windows' built-in
    location service (the same one Maps/Weather apps use).

    Requires: Settings -> Privacy & security -> Location ->
    "Location services" ON, and "Let apps access your location" ON.

    Returns (lat, lon), or None if location couldn't be determined
    (e.g. permission denied, or no location source available).
    """
    try:
        return asyncio.run(_get_location_async())
    except Exception as e:
        print(f"Could not get location: {e}")
        return None