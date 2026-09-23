print("Program started")

from datetime import datetime, date
import threading

import cv2

from vision.face_capture import FaceCapture
from recognition.face_recognizer import FaceRecognizer
from database.facedatabase import FaceDatabase
from database.patient_profile import PatientProfile
from database.patient_memory import PatientMemory
from database.safe_zone_store import SafeZoneStore
from database.caregiver_auth import CaregiverAuth
from voice.text_to_speech import TextToSpeech
from voice.speech_to_text import SpeechToText
from voice.alarm import Alarm
from language_utils import detect_language
from setup_wizard import run_family_setup, get_face_photo
from location.safe_zone import SafeZone
from location.map_setup import pick_safe_zone_on_map
from ai.assistant import Assistant, AssistantError

try:
    from location.gps_tracker import get_current_location
except Exception:
    # winsdk (Windows-only) might not be installed on this machine -
    # the Map & Safe Zone menu still works, just without live GPS.
    get_current_location = None


DOB_FORMAT = "%d/%m/%Y"

ASSISTANT_ERROR_MESSAGES_EN = {
    "connection_refused": "I can't reach the AI server. Please make sure Ollama is running.",
    "timeout": "That took too long to respond. Please try again.",
    "model_not_found": "The AI model isn't installed yet. Please check the setup.",
    "invalid_response": "I didn't get a proper response. Please try again.",
    "unknown": "Something went wrong. Please try again.",
}

ASSISTANT_ERROR_MESSAGES_AR = {
    "connection_refused": "مش قادر أوصل لسيرفر Ollama. اتأكد إنه شغال.",
    "timeout": "الرد استغرق وقت طويل. جرب تاني.",
    "model_not_found": "الموديل مش متثبت لسه. اتأكد من الإعداد.",
    "invalid_response": "مجتليش رد سليم. جرب تاني.",
    "unknown": "حصل خطأ غير متوقع. جرب تاني.",
}


# ============================================================
# HELPERS
# ============================================================

def calculate_age(dob):
    """dob: a datetime.date. Returns the age in whole years, today."""
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def read_date_of_birth():
    while True:
        raw = input("Date of birth (DD/MM/YYYY): ").strip()
        try:
            return datetime.strptime(raw, DOB_FORMAT).date()
        except ValueError:
            print("That doesn't look like a valid date. Please use DD/MM/YYYY, e.g. 05/03/1950.")


def read_required(prompt):
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("This field can't be empty.")


def get_person_info(listener):
    """
    Asks for a person's name and relationship, by voice first,
    falling back to typing if voice isn't understood.
    """

    print("Please say the person's name...")
    name = listener.listen_and_transcribe()
    if not name:
        print("Voice not detected/understood, please type the name instead.")
        name = input("Enter the person's name: ").strip()

    print("Please say their relationship (e.g. daughter, son, caregiver)...")
    relationship = listener.listen_and_transcribe()
    if not relationship:
        print("Voice not detected/understood, please type the relationship instead.")
        relationship = input("Enter their relationship to the patient: ").strip()

    return name, relationship


# ============================================================
# LIVE SAFE-ZONE MONITORING (runs in the background the whole time
# the app is open, no matter which menu you're in) - scoped to
# whichever account is currently logged in.
# ============================================================

def safe_zone_monitor_loop(patient_id, speaker, tts_lock, stop_event, interval_seconds=15):
    """
    Runs continuously in the background: every `interval_seconds`, checks
    the CURRENT account's GPS location against ITS OWN saved safe zone,
    and speaks a warning immediately the moment the patient leaves it
    (and a reassuring message the moment they come back).

    Safe to run alongside the camera / AI assistant / any other menu -
    it never blocks and never calls input(). Stops automatically on
    logout (see stop_event, set right before returning to the welcome
    screen).
    """
    last_status = None
    warned_no_gps = False
    store = SafeZoneStore()

    while not stop_event.is_set():

        if get_current_location is None:
            if not warned_no_gps:
                print("\n[Safe Zone] Live GPS isn't available on this machine - "
                      "background monitoring is off. You can still check manually "
                      "from the Map & Safe Zone menu.")
                warned_no_gps = True
            stop_event.wait(interval_seconds)
            continue

        config = store.get(patient_id)
        if config is None:
            # Not configured yet for this account - keep waiting quietly.
            stop_event.wait(interval_seconds)
            continue

        location = get_current_location()
        if location is None:
            stop_event.wait(interval_seconds)
            continue

        lat, lon = location
        safe_zone = SafeZone(config["center_lat"], config["center_lon"], config["radius_meters"])
        status = safe_zone.check_status(lat, lon)

        if status["inside_safe_zone"] != last_status:
            with tts_lock:
                if status["inside_safe_zone"]:
                    print("\n[Safe Zone] Back inside the safe zone.")
                    speaker.speak("You are back inside the safe zone.")
                else:
                    print(f"\n[Safe Zone] WARNING - outside the safe zone "
                          f"({status['distance_meters']} m from home)!")
                    speaker.speak("Warning. You have left the safe zone.")
            last_status = status["inside_safe_zone"]

        stop_event.wait(interval_seconds)


def start_safe_zone_monitor(patient_id, speaker, tts_lock):
    """
    Starts the live monitor as a daemon thread and returns the stop_event
    used to shut it down cleanly on logout / app exit.
    """
    stop_event = threading.Event()
    thread = threading.Thread(
        target=safe_zone_monitor_loop,
        args=(patient_id, speaker, tts_lock, stop_event),
        daemon=True,
    )
    thread.start()
    return stop_event


# ============================================================
# WELCOME / SIGN UP / LOGIN
# ============================================================

def run_signup(camera, capture, recognizer, database, profile, speaker):
    """
    Creates a brand new MEMORA account on this device: first name, last
    name, date of birth (age is computed from it), and a national ID
    (used afterwards to log in). Then hands off to the family-members
    setup, and returns (patient_id, first_name) - or None if cancelled.
    """

    print("\n=== Sign Up - Let's create a new account ===")
    speaker.speak("Let's create your account.")

    first_name = read_required("First name: ")
    last_name = read_required("Last name: ")
    dob = read_date_of_birth()
    age = calculate_age(dob)

    print(f"Age calculated: {age}")

    patient_id = None
    while patient_id is None:
        national_id = read_required("National ID (this will be used to log in later): ")
        try:
            patient_id = profile.create(first_name, last_name, dob.isoformat(), age, national_id)
        except ValueError as e:
            print(str(e))
            again = input("Try a different national ID? (y/n): ").strip().lower()
            if again != "y":
                print("Sign up cancelled.")
                return None

    print(f"\nAccount created for {first_name} {last_name}, age {age}.")
    speaker.speak(f"Account created. Welcome, {first_name}.")

    # Optional patient photo - take with camera or upload a file, always
    # going through real face detection first (same as family members).
    add_photo = input("\nAdd a photo of the patient now? (y/n): ").strip().lower()
    if add_photo == "y":
        full_name = f"{first_name} {last_name}"
        frame, bbox, embedding = get_face_photo(camera, recognizer, person_label=full_name)

        if embedding is not None:
            x1, y1, x2, y2 = bbox
            x, y, w, h = x1, y1, x2 - x1, y2 - y1
            photo_path = capture.capture_face(frame, (x, y, w, h), f"{first_name}_{last_name}")
            profile.update_photo(patient_id, photo_path)

            # Also register the patient's own face under this account,
            # so the camera can recognize them too, not just the family.
            database.save(patient_id, full_name, embedding, "Patient (self)")

            print("Patient photo saved and registered for face recognition.")
        else:
            print("No photo added - you can add one later.")

    # The usual family-member questions
    run_family_setup(camera, capture, recognizer, database, speaker, patient_id)

    return patient_id, first_name


def run_login(profile):
    """Returns (patient_id, first_name) on success, or None."""
    print("\n=== Login ===")

    for attempt in range(3):
        national_id = read_required("Enter your national ID to log in: ")
        info = profile.find_by_national_id(national_id)
        if info:
            print(f"Login successful. Welcome back, {info['first_name']}!")
            return info["id"], info["first_name"]
        print("No account found with that national ID, please try again.")

    print("Too many incorrect attempts.")
    return None


def choose_role():
    """
    The very first screen: is whoever opened MEMORA a Patient, or the
    Caregiver / Admin who manages every patient on this device?
    """
    print("=" * 40)
    print("        Welcome to MEMORA")
    print("=" * 40)

    while True:
        print("\n1) Patient")
        print("2) Caregiver / Admin")
        print("3) Exit")
        choice = input("Choose an option (1/2/3): ").strip()

        if choice in ("1", "2", "3"):
            return choice

        print("Please enter 1, 2 or 3.")


def patient_welcome_screen(camera, capture, recognizer, database, profile, speaker):
    """
    Sign up / Login choice for a PATIENT. Returns (patient_id, first_name)
    to continue into the app, or None to go back to the role screen.
    """
    while True:
        print("\n--- Patient ---")
        print("1) Sign up")
        print("2) Login")
        print("3) Back")
        choice = input("Choose an option (1/2/3): ").strip()

        if choice == "1":
            result = run_signup(camera, capture, recognizer, database, profile, speaker)
            if result:
                return result
            # cancelled - show this menu again

        elif choice == "2":
            result = run_login(profile)
            if result:
                return result
            # too many failed attempts or user wants to try something else

        elif choice == "3":
            return None

        else:
            print("Please enter 1, 2 or 3.")


# ============================================================
# DAILY SCHEDULE (right after login/signup)
# ============================================================

def run_daily_schedule_setup(patient_id, first_name, speaker, listener):
    """
    Greets the patient by name and asks for today's schedule, item by
    item (time + what's happening), by voice first and falling back to
    typing. Saved as a fact in this account's memory so the AI
    Assistant can answer questions about it later.
    """

    print(f"\nHi, {first_name}!")
    speaker.speak(f"Hi, {first_name}!")

    print("What is your schedule for today?")
    speaker.speak("What is your schedule for today?")

    entries = []

    while True:
        add_more = input("\nAdd a schedule item for today? (y/n): ").strip().lower()
        if add_more != "y":
            break

        print("What time is it? (say it, or press Enter to type instead)")
        time_text = listener.listen_and_transcribe()
        if not time_text:
            time_text = input("Time: ").strip()

        if not time_text:
            print("No time entered, skipping this item.")
            continue

        print("What's happening at that time? (say it, or press Enter to type instead)")
        activity_text = listener.listen_and_transcribe()
        if not activity_text:
            activity_text = input("Activity: ").strip()

        if not activity_text:
            print("No activity entered, skipping this item.")
            continue

        entries.append(f"{time_text} - {activity_text}")
        print(f"Added: {time_text} - {activity_text}")

    if entries:
        schedule_text = "; ".join(entries)
        PatientMemory().set(patient_id, "today_schedule", schedule_text)
        print("\nToday's schedule saved:")
        print(schedule_text)
        speaker.speak("Got it, I've saved your schedule for today.")
    else:
        print("\nNo schedule added for today - you can add it later by asking the AI assistant, "
              "or from a future update of this menu.")


# ============================================================
# MENU OPTION 1: CAMERA - RECOGNIZE / REGISTER A PERSON
# ============================================================

def run_camera_mode(camera, capture, recognizer, database, speaker, listener, alarm, patient_id):
    print("\n=== Camera Mode ===")
    print("Looking for faces... press 'q' at any time to stop.")

    while True:

        ret, frame = camera.read()

        if not ret:
            print("Could not read frame from camera.")
            break

        faces = recognizer.get_all_faces(frame)

        if len(faces) > 0:

            print(f"Found {len(faces)} face(s) in this frame.")

            known_faces = database.load(patient_id)

            for i, (bbox, embedding) in enumerate(faces):

                x1, y1, x2, y2 = bbox

                display_frame = frame.copy()
                cv2.rectangle(display_frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
                cv2.putText(
                    display_frame, f"Person {i + 1}/{len(faces)}",
                    (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2
                )
                cv2.imshow("MEMORA", display_frame)
                cv2.waitKey(500)

                name, score = recognizer.recognize(embedding, known_faces)

                if name != "Unknown":
                    relationship = database.get_relationship(patient_id, name)
                    print(f"Recognized: {name} ({relationship}) score: {score:.2f}")

                    if relationship:
                        speaker.speak(f"This is {name}, your {relationship}")
                    else:
                        speaker.speak(f"This is {name}")

                    x, y, w, h = x1, y1, x2 - x1, y2 - y1
                    capture.capture_face(frame, (x, y, w, h), name)

                else:
                    print("This person is not registered yet.")
                    speaker.speak("I don't recognize this person yet.")

                    real_name, relationship = get_person_info(listener)

                    if real_name:
                        database.save(patient_id, real_name, embedding, relationship)
                        known_faces = database.load(patient_id)
                        print(f"'{real_name}' ({relationship}) registered successfully.")
                        speaker.speak(f"Got it. I will remember {real_name} from now on.")

                        x, y, w, h = x1, y1, x2 - x1, y2 - y1
                        capture.capture_face(frame, (x, y, w, h), real_name)
                    else:
                        print("No name entered, the person will not be registered.")

                alarm.beep()

            break

        cv2.imshow("MEMORA", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cv2.destroyAllWindows()
    print("Camera mode closed.\n")


# ============================================================
# MENU OPTION 2: MAP & SAFE ZONE
# ============================================================

def run_map_and_safe_zone(speaker, tts_lock, patient_id):
    print("\n=== Map & Safe Zone ===")
    store = SafeZoneStore()

    while True:
        print("\n1) View current safe zone")
        print("2) Set / update safe zone on the map")
        print("3) Check current location against the safe zone (manual, one-time)")
        print("4) Back to main menu")
        choice = input("Choose an option: ").strip()

        if choice == "1":
            config = store.get(patient_id)
            if config is None:
                print("No safe zone has been set up yet. Choose option 2 to set one on the map.")
            else:
                print(f"Center: ({config['center_lat']}, {config['center_lon']}) - "
                      f"radius: {config['radius_meters']} m")

        elif choice == "2":
            config = pick_safe_zone_on_map(patient_id)
            if config:
                print(f"Safe zone saved: ({config['center_lat']}, {config['center_lon']}) - "
                      f"radius: {config['radius_meters']} m")
                with tts_lock:
                    speaker.speak("Safe zone saved.")

        elif choice == "3":
            if get_current_location is None:
                print("Live GPS isn't available on this machine (Windows location "
                      "service / winsdk not found). You can enter coordinates manually instead, "
                      "just for testing.")
                try:
                    lat = float(input("Enter current latitude: ").strip())
                    lon = float(input("Enter current longitude: ").strip())
                except ValueError:
                    print("Please enter valid numbers.")
                    continue
            else:
                location = get_current_location()
                if location is None:
                    print("Could not get current location.")
                    continue
                lat, lon = location

            config = store.get(patient_id)
            if config is None:
                print("No safe zone has been set up yet. Choose option 2 to set one on the map.")
                continue

            safe_zone = SafeZone(config["center_lat"], config["center_lon"], config["radius_meters"])
            status = safe_zone.check_status(lat, lon)
            state = "INSIDE" if status["inside_safe_zone"] else "OUTSIDE"
            print(f"({lat:.5f}, {lon:.5f}) is {state} the safe zone "
                  f"({status['distance_meters']} m from center).")

            with tts_lock:
                if status["inside_safe_zone"]:
                    speaker.speak("You are inside the safe zone.")
                else:
                    speaker.speak("Warning. You are outside the safe zone.")

        elif choice == "4":
            break

        else:
            print("Invalid option.")

    print("Returning to main menu.\n")


# ============================================================
# MENU OPTION 3: AI ASSISTANT (text + voice, TTS/STT built in,
# aware of this account's facts, schedule and live safe-zone status)
# ============================================================

def speak_assistant_error(speaker, error, last_language):
    is_arabic = last_language in ("ar", "mixed")
    messages = ASSISTANT_ERROR_MESSAGES_AR if is_arabic else ASSISTANT_ERROR_MESSAGES_EN
    speaker.speak(messages.get(error.error_type, messages["unknown"]),
                  language_hint="ar" if is_arabic else "en")


def run_ai_assistant(speaker, listener, tts_lock, patient_id):
    print("\n=== AI Assistant ===")
    assistant = Assistant(patient_id=patient_id)

    mode = ""
    while mode not in ("1", "2"):
        print("1) Type your questions")
        print("2) Speak your questions (voice)")
        mode = input("Choose a mode: ").strip()

    voice_mode = (mode == "2")

    if voice_mode and not listener.microphone_available:
        print("No microphone detected - switching to typed mode.")
        voice_mode = False

    print("Say/type 'quit' at any time to return to the main menu.\n")
    with tts_lock:
        speaker.speak("I'm ready. Go ahead and ask me anything.")

    last_language = "en"

    while True:
        if voice_mode:
            print("(Listening for your question...)")
            question = listener.listen_and_transcribe()
            if not question:
                continue
        else:
            question = input("You: ").strip()

        if not question:
            continue

        if question.strip().lower() in ("quit", "exit", "خروج"):
            break

        last_language = detect_language(question)
        print(f"You said ({last_language}): {question}")

        try:
            answer = assistant.ask(question)
        except AssistantError as e:
            print(f"[Assistant error - {e.error_type}]: {e}")
            with tts_lock:
                speak_assistant_error(speaker, e, last_language)
            continue

        print(f"Assistant: {answer}")

        reply_language = "ar" if detect_language(answer) in ("ar", "mixed") else "en"
        with tts_lock:
            speaker.speak(answer, language_hint=reply_language)

    print("Leaving the AI assistant.\n")


# ============================================================
# MENU OPTION 4: MY DATA (debug view - proves the DB is per-account)
# ============================================================

def run_my_data(profile, database, patient_id):
    print("\n=== My Data ===")

    info = profile.get(patient_id)
    if info:
        print(f"Name: {info['name']}")
        print(f"Date of birth: {info['date_of_birth']}  (age {info['age']})")
        print(f"National ID: {info['national_id']}")

    people_count = database.count_people(patient_id)
    print(f"Registered faces (patient + family) under this account: {people_count}")

    facts = PatientMemory().get_all(patient_id)
    if facts:
        print("Stored facts / schedule for this account:")
        for key, value in facts.items():
            print(f"  - {key}: {value}")
    else:
        print("No facts/schedule stored yet for this account.")

    total_accounts = len(profile.list_all())
    print(f"\n(Total MEMORA accounts registered on this device: {total_accounts})")
    print("Log in with a different national ID to see a different account's data.\n")


# ============================================================
# CAREGIVER / ADMIN PANEL
# ============================================================

def run_caregiver_login(caregiver_auth):
    """Returns True if the caregiver is now logged into the admin panel."""
    print("\n--- Caregiver / Admin ---")

    if not caregiver_auth.is_set_up():
        print("No caregiver PIN has been set up on this device yet. Let's create one.")
        while True:
            pin1 = read_required("Create a caregiver PIN: ")
            pin2 = read_required("Confirm the PIN: ")
            if pin1 == pin2:
                caregiver_auth.set_pin(pin1)
                print("Caregiver PIN created. You're logged in.")
                return True
            print("Those didn't match, please try again.")

    for attempt in range(3):
        pin = read_required("Enter the caregiver PIN: ")
        if caregiver_auth.verify(pin):
            print("Caregiver login successful.")
            return True
        print("Incorrect PIN, please try again.")

    print("Too many incorrect attempts.")
    return False


def select_patient(profile):
    """
    Shows every patient registered on this device and lets the
    caregiver pick one by number. Returns a patient_id, or None if
    there are no patients yet or the caregiver cancels.
    """
    patients = profile.list_all()

    if not patients:
        print("No patients registered on this device yet.")
        return None

    print("\nRegistered patients:")
    for i, p in enumerate(patients, start=1):
        print(f"{i}) {p['first_name']} {p['last_name']} (National ID: {p['national_id']})")

    choice = input("Choose a patient number (or press Enter to cancel): ").strip()
    if not choice:
        return None

    try:
        index = int(choice) - 1
    except ValueError:
        print("Invalid selection.")
        return None

    if 0 <= index < len(patients):
        return patients[index]["id"]

    print("Invalid selection.")
    return None


def show_patient_details(profile, database, patient_id):
    info = profile.get(patient_id)
    if not info:
        print("Patient not found.")
        return

    print(f"\nName: {info['name']}")
    print(f"Date of birth: {info['date_of_birth']}  (age {info['age']})")
    print(f"National ID: {info['national_id']}")

    people = database.list_people(patient_id)
    print(f"\nFamily / registered faces ({len(people)}):")
    if people:
        for p in people:
            print(f"  - {p['name']} ({p['relationship']})")
    else:
        print("  (none yet)")

    facts = PatientMemory().get_all(patient_id)
    print("\nStored facts / schedule:")
    if facts:
        for key, value in facts.items():
            print(f"  - {key}: {value}")
    else:
        print("  (none yet)")

    config = SafeZoneStore().get(patient_id)
    print("\nSafe zone:")
    if config:
        print(f"  Center: ({config['center_lat']}, {config['center_lon']}) - "
              f"radius: {config['radius_meters']} m")
        if get_current_location is not None:
            location = get_current_location()
            if location:
                lat, lon = location
                zone = SafeZone(config["center_lat"], config["center_lon"], config["radius_meters"])
                status = zone.check_status(lat, lon)
                state = "INSIDE" if status["inside_safe_zone"] else "OUTSIDE"
                print(f"  Live status: {state} the safe zone "
                      f"({status['distance_meters']} m from home)")
    else:
        print("  (not set up yet)")

    print()


def run_delete_patient(profile, database):
    patient_id = select_patient(profile)
    if patient_id is None:
        return

    info = profile.get(patient_id)
    confirm = input(
        f"Type DELETE to permanently remove {info['name']}'s account and all their "
        f"data (family faces, schedule, safe zone): "
    ).strip()

    if confirm == "DELETE":
        database.delete_all_for_patient(patient_id)
        PatientMemory().delete_all_for_patient(patient_id)
        SafeZoneStore().delete(patient_id)
        profile.delete(patient_id)
        print(f"{info['name']}'s account has been deleted.")
    else:
        print("Cancelled - nothing was deleted.")


def run_caregiver_menu(camera, capture, recognizer, database, profile, speaker, tts_lock):
    while True:
        print("\n" + "=" * 40)
        print("        Caregiver / Admin Panel")
        print("=" * 40)
        print("1) View all patients")
        print("2) View a patient's details")
        print("3) Register a new patient account")
        print("4) Add a family member to a patient")
        print("5) Set / update a patient's safe zone (map)")
        print("6) Remove a patient account")
        print("7) Log out of admin panel")

        choice = input("Choose an option: ").strip()

        if choice == "1":
            patients = profile.list_all()
            if not patients:
                print("No patients registered yet.")
            else:
                print(f"\n{len(patients)} patient(s) registered on this device:")
                for p in patients:
                    family_count = database.count_people(p["id"])
                    print(f"  - {p['first_name']} {p['last_name']} "
                          f"(National ID: {p['national_id']}) - {family_count} family member(s)")

        elif choice == "2":
            patient_id = select_patient(profile)
            if patient_id is not None:
                show_patient_details(profile, database, patient_id)

        elif choice == "3":
            result = run_signup(camera, capture, recognizer, database, profile, speaker)
            if result:
                print(f"New patient account created for {result[1]}.")

        elif choice == "4":
            patient_id = select_patient(profile)
            if patient_id is not None:
                run_family_setup(camera, capture, recognizer, database, speaker, patient_id)

        elif choice == "5":
            patient_id = select_patient(profile)
            if patient_id is not None:
                config = pick_safe_zone_on_map(patient_id)
                if config:
                    print("Safe zone saved for this patient.")
                    with tts_lock:
                        speaker.speak("Safe zone saved.")

        elif choice == "6":
            run_delete_patient(profile, database)

        elif choice == "7":
            print("Logging out of the admin panel.\n")
            break

        else:
            print("Invalid option, please choose 1-7.")


# ============================================================
# MAIN MENU
# ============================================================

def main_menu(camera, capture, recognizer, database, speaker, listener, alarm, tts_lock, patient_id, profile):
    """Returns "logout" or "exit"."""
    while True:
        print("\n" + "=" * 40)
        print("           MEMORA - Main Menu")
        print("=" * 40)
        print("1) Camera - recognize / register a person")
        print("2) Map & Safe Zone")
        print("3) AI Assistant")
        print("4) My data (debug)")
        print("5) Logout")
        print("6) Exit")

        choice = input("Choose an option: ").strip()

        if choice == "1":
            run_camera_mode(camera, capture, recognizer, database, speaker, listener, alarm, patient_id)
        elif choice == "2":
            run_map_and_safe_zone(speaker, tts_lock, patient_id)
        elif choice == "3":
            run_ai_assistant(speaker, listener, tts_lock, patient_id)
        elif choice == "4":
            run_my_data(profile, database, patient_id)
        elif choice == "5":
            print("Logging out...\n")
            return "logout"
        elif choice == "6":
            print("Goodbye!")
            return "exit"
        else:
            print("Invalid option, please choose 1-6.")


# ============================================================
# ENTRY POINT
# ============================================================

def main():

    capture = FaceCapture()
    recognizer = FaceRecognizer()
    database = FaceDatabase()
    profile = PatientProfile()
    caregiver_auth = CaregiverAuth()
    speaker = TextToSpeech()
    listener = SpeechToText()
    alarm = Alarm()
    tts_lock = threading.Lock()  # so the background safe-zone monitor and the
                                  # foreground menus never talk over each other

    camera = cv2.VideoCapture(0)

    if not camera.isOpened():
        print("Could not open camera")
        return

    try:
        while True:
            role = choose_role()

            if role == "3":
                break

            elif role == "1":
                session = patient_welcome_screen(camera, capture, recognizer, database, profile, speaker)
                if session is None:
                    continue  # back to the role screen

                patient_id, first_name = session

                run_daily_schedule_setup(patient_id, first_name, speaker, listener)

                # Runs for the rest of this login session, in the
                # background, no matter which menu is open - alerts the
                # moment the patient leaves THEIR OWN safe zone.
                monitor_stop_event = start_safe_zone_monitor(patient_id, speaker, tts_lock)

                action = main_menu(
                    camera, capture, recognizer, database, speaker, listener, alarm,
                    tts_lock, patient_id, profile
                )

                monitor_stop_event.set()

                if action == "exit":
                    break
                # else "logout" -> loop back to the role screen

            elif role == "2":
                if run_caregiver_login(caregiver_auth):
                    run_caregiver_menu(camera, capture, recognizer, database, profile, speaker, tts_lock)
                # either way, loop back to the role screen

    finally:
        camera.release()
        cv2.destroyAllWindows()
        print("Camera closed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("!!! An error occurred !!!")
        print(e)
        import traceback
        traceback.print_exc()
    input("Press Enter to close...")
