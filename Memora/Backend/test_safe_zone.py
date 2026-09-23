print("Starting automatic safe zone tracker...")
import time

from location.safe_zone import SafeZone
from location.gps_tracker import get_current_location
from voice.text_to_speech import TextToSpeech

speaker = TextToSpeech()

safe_zone = SafeZone.load_or_create()

print("\nTracking your location automatically. Press Ctrl+C to stop.\n")

last_status = None  # so we only speak when the status CHANGES

try:
    while True:

        location = get_current_location()

        if location is None:
            print("Could not get current location, retrying...")
            time.sleep(5)
            continue

        lat, lon = location
        status = safe_zone.check_status(lat, lon)

        print(f"Location: ({lat:.5f}, {lon:.5f}) - "
              f"{status['distance_meters']}m from home - "
              f"{'INSIDE' if status['inside_safe_zone'] else 'OUTSIDE'} safe zone")

        if status["inside_safe_zone"] != last_status:
            if status["inside_safe_zone"]:
                speaker.speak("You are back inside the safe zone.")
            else:
                speaker.speak("Warning. The patient has left the safe zone.")

            last_status = status["inside_safe_zone"]

        time.sleep(5)  # check every 5 seconds

except KeyboardInterrupt:
    print("\nTracking stopped.")