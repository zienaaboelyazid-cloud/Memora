"""
MEMORA Web API
==============
A small Flask backend that exposes the SAME database, face-recognition
and AI-assistant logic used by main.py (the terminal app) over HTTP, so
the website (index.html / style.css / script.js) is a REAL front-end
for this project instead of a browser-only demo.

Run it with:
    pip install flask
    python api_server.py

It serves on http://127.0.0.1:5000 by default. Keep this window open
while you use the website (open index.html with VS Code's "Live
Server" extension, not directly as a file:// page, since browsers
block camera access on file:// pages).
"""

import base64
import os
from datetime import date

import cv2
import numpy as np
from flask import Flask, request, jsonify, send_file

from database.patient_profile import PatientProfile
from database.facedatabase import FaceDatabase
from database.patient_memory import PatientMemory
from database.safe_zone_store import SafeZoneStore
from recognition.face_recognizer import FaceRecognizer
from location.safe_zone import SafeZone
from vision.face_capture import FaceCapture
from ai.assistant import Assistant, AssistantError
from config import SCHEDULE_REFRESH_HOURS

try:
    from location.gps_tracker import get_current_location
except Exception:
    # winsdk (Windows-only) might not be installed on this machine.
    get_current_location = None


app = Flask(__name__)

profile = PatientProfile()
database = FaceDatabase()
memory_store = PatientMemory()
zone_store = SafeZoneStore()
face_capture = FaceCapture()  # saves cropped face photos to data/people (same as the terminal app)

print("Loading the face recognition model (this can take a few seconds)...")
recognizer = FaceRecognizer()
print("Ready.")

# One Assistant instance per patient, kept alive across requests so the
# conversation actually has memory/history like the terminal app does.
_assistants = {}

CAREGIVER_USERNAME = "NanZy@memora.NZ"
CAREGIVER_PASSWORD = "NanZy"


# ---------------- CORS (the website is opened from a different origin/port) ----------------

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    return response


@app.route("/api/<path:_any>", methods=["OPTIONS"])
def cors_preflight(_any):
    return "", 204


# ---------------- helpers ----------------

def decode_image(data_url):
    """
    Turns a 'data:image/png;base64,....' string sent by the browser into
    an OpenCV/numpy image - the same shape main.py gets from the webcam.
    """
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    binary = base64.b64decode(data_url)
    array = np.frombuffer(binary, dtype=np.uint8)
    return cv2.imdecode(array, cv2.IMREAD_COLOR)


def calculate_age(dob_str):
    dob = date.fromisoformat(dob_str)
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def error(message, status=400):
    return jsonify({"error": message}), status


def patient_json(info):
    photo_path = info.get("photo_path") or ""
    return {
        "id": info["id"],
        "firstName": info["first_name"],
        "lastName": info["last_name"],
        "dob": info["date_of_birth"],
        "age": info["age"],
        "nationalId": info["national_id"],
        "hasPhoto": bool(photo_path) and os.path.exists(photo_path),
    }


def get_assistant(patient_id):
    if patient_id not in _assistants:
        _assistants[patient_id] = Assistant(patient_id=patient_id)
    return _assistants[patient_id]


# ---------------- Patients: sign up / login / admin ----------------

@app.route("/api/signup", methods=["POST"])
def signup():
    data = request.get_json(force=True)
    first_name = (data.get("firstName") or "").strip()
    last_name = (data.get("lastName") or "").strip()
    dob = (data.get("dob") or "").strip()
    national_id = (data.get("nationalId") or "").strip()

    if not (first_name and last_name and dob and national_id):
        return error("All fields are required.")

    try:
        age = calculate_age(dob)
    except ValueError:
        return error("Invalid date of birth (expected YYYY-MM-DD).")

    try:
        patient_id = profile.create(first_name, last_name, dob, age, national_id)
    except ValueError as e:
        return error(str(e), 409)

    return jsonify(patient_json(profile.get(patient_id)))


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    national_id = (data.get("nationalId") or "").strip()
    info = profile.find_by_national_id(national_id)
    if not info:
        return error("No account found with that national ID.", 404)
    return jsonify(patient_json(info))


@app.route("/api/patients", methods=["GET"])
def list_patients():
    result = []
    for p in profile.list_all():
        result.append({
            "id": p["id"],
            "firstName": p["first_name"],
            "lastName": p["last_name"],
            "nationalId": p["national_id"],
            "familyCount": database.count_people(p["id"]),
        })
    return jsonify(result)


@app.route("/api/patients/<int:patient_id>", methods=["GET"])
def get_patient(patient_id):
    info = profile.get(patient_id)
    if not info:
        return error("Patient not found.", 404)

    return jsonify({
        "profile": patient_json(info),
        "family": database.list_people(patient_id),
        "facts": memory_store.get_all(patient_id),
        "safeZone": zone_store.get(patient_id),
    })


@app.route("/api/patients/<int:patient_id>", methods=["DELETE"])
def delete_patient(patient_id):
    info = profile.get(patient_id)
    if info and info["photo_path"] and os.path.exists(info["photo_path"]):
        try:
            os.remove(info["photo_path"])
        except OSError:
            pass

    database.delete_all_for_patient(patient_id)
    memory_store.delete_all_for_patient(patient_id)
    zone_store.delete(patient_id)
    profile.delete(patient_id)
    _assistants.pop(patient_id, None)
    return jsonify({"status": "deleted"})


# ---------------- Patient's own photo (asked at sign-up / first login) ----------------

@app.route("/api/patients/<int:patient_id>/photo", methods=["GET"])
def get_patient_photo(patient_id):
    info = profile.get(patient_id)
    path = info["photo_path"] if info else ""
    if not path or not os.path.exists(path):
        return error("No photo saved for this patient.", 404)
    return send_file(os.path.abspath(path), mimetype="image/jpeg")


@app.route("/api/patients/<int:patient_id>/photo", methods=["POST"])
def set_patient_photo(patient_id):
    """
    Same steps as the terminal app's sign-up photo: real face detection,
    save the cropped face, store it as the patient's photo, and register
    the patient's own face ("Patient (self)") so the camera recognizes them.
    """
    info = profile.get(patient_id)
    if not info:
        return error("Patient not found.", 404)

    data = request.get_json(force=True)
    image_b64 = data.get("image")
    if not image_b64:
        return error("No photo was sent.")

    try:
        image = decode_image(image_b64)
    except Exception:
        image = None
    if image is None:
        return error("That file could not be read as an image.")

    faces = recognizer.get_all_faces(image)
    if not faces:
        return error("No face was detected in that photo. Please try again.", 422)

    bbox, embedding = faces[0]

    # crop the face with a little margin, clamped to the picture
    img_h, img_w = image.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in bbox]
    margin = int(0.2 * max(x2 - x1, y2 - y1))
    x1, y1 = max(0, x1 - margin), max(0, y1 - margin)
    x2, y2 = min(img_w, x2 + margin), min(img_h, y2 + margin)

    old_path = info["photo_path"]
    new_path = face_capture.capture_face(image, (x1, y1, x2 - x1, y2 - y1), f"patient_{patient_id}")
    if not os.path.exists(new_path):
        return error("Could not save the photo on the server.", 500)

    profile.update_photo(patient_id, new_path)
    if old_path and old_path != new_path and os.path.exists(old_path):
        try:
            os.remove(old_path)
        except OSError:
            pass

    database.save(patient_id, info["name"], embedding, "Patient (self)")
    return jsonify({"status": "ok"})


# ---------------- Family / faces (real InsightFace recognition) ----------------

@app.route("/api/patients/<int:patient_id>/family", methods=["GET"])
def list_family(patient_id):
    return jsonify(database.list_people(patient_id))


@app.route("/api/patients/<int:patient_id>/family", methods=["POST"])
def add_family(patient_id):
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    relationship = (data.get("relationship") or "").strip()
    age_raw = data.get("age")
    notes = (data.get("notes") or "").strip()
    image_b64 = data.get("image")

    if not (name and relationship and age_raw not in (None, "") and image_b64):
        return error("Name, relationship, age and a photo are all required.")

    try:
        age = int(age_raw)
        if age < 0 or age > 130:
            raise ValueError
    except (TypeError, ValueError):
        return error("Please enter a valid age.")

    image = decode_image(image_b64)
    faces = recognizer.get_all_faces(image)
    if not faces:
        return error("No face was detected in that photo. Please try again.", 422)

    bbox, embedding = faces[0]

    # crop the face with a little margin, clamped to the picture (same as the patient's own photo)
    img_h, img_w = image.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in bbox]
    margin = int(0.2 * max(x2 - x1, y2 - y1))
    x1, y1 = max(0, x1 - margin), max(0, y1 - margin)
    x2, y2 = min(img_w, x2 + margin), min(img_h, y2 + margin)

    safe_name = "".join(c if c.isalnum() else "_" for c in name)
    photo_path = face_capture.capture_face(image, (x1, y1, x2 - x1, y2 - y1), f"family_{patient_id}_{safe_name}")

    person_id = database.save(patient_id, name, embedding, relationship, age, photo_path, notes)
    return jsonify({"status": "ok", "id": person_id, "name": name, "relationship": relationship, "age": age, "notes": notes})


@app.route("/api/patients/<int:patient_id>/family/<int:person_id>/photo", methods=["GET"])
def get_family_photo(patient_id, person_id):
    path = database.get_photo_path(patient_id, person_id)
    if not path or not os.path.exists(path):
        return error("No photo saved for this person.", 404)
    return send_file(os.path.abspath(path), mimetype="image/jpeg")


@app.route("/api/patients/<int:patient_id>/recognize", methods=["POST"])
def recognize(patient_id):
    data = request.get_json(force=True)
    image_b64 = data.get("image")
    if not image_b64:
        return error("No image was sent.")

    image = decode_image(image_b64)
    faces = recognizer.get_all_faces(image)

    if not faces:
        return jsonify({"found": False, "message": "No face was detected in that photo."})

    _, embedding = faces[0]
    known_faces = database.load(patient_id)
    name, score = recognizer.recognize(embedding, known_faces)

    if name == "Unknown":
        return jsonify({"found": False, "match": False, "score": float(score)})

    relationship = database.get_relationship(patient_id, name)
    return jsonify({
        "found": True, "match": True,
        "name": name, "relationship": relationship, "score": float(score),
    })


# ---------------- Schedule / facts ----------------

@app.route("/api/patients/<int:patient_id>/schedule", methods=["GET"])
def get_schedule(patient_id):
    """
    Also tells the website whether the schedule is out of date: it counts
    for SCHEDULE_REFRESH_HOURS (24h), after which the patient is asked
    "what do you have today?" again.
    """
    schedule = memory_store.get(patient_id, "today_schedule")
    age_hours = memory_store.get_age_hours(patient_id, "today_schedule")
    needs_update = schedule is None or (age_hours is not None and age_hours >= SCHEDULE_REFRESH_HOURS)
    return jsonify({
        "schedule": schedule,
        "ageHours": age_hours,
        "refreshHours": SCHEDULE_REFRESH_HOURS,
        "needsUpdate": needs_update,
    })


@app.route("/api/patients/<int:patient_id>/schedule", methods=["POST"])
def set_schedule(patient_id):
    data = request.get_json(force=True)
    text = (data.get("schedule") or "").strip()
    memory_store.set(patient_id, "today_schedule", text)
    return jsonify({"status": "ok"})


# ---------------- Safe zone (real lat/lon + Haversine distance) ----------------

@app.route("/api/patients/<int:patient_id>/safezone", methods=["GET"])
def get_safezone(patient_id):
    return jsonify(zone_store.get(patient_id))


@app.route("/api/patients/<int:patient_id>/safezone", methods=["POST"])
def set_safezone(patient_id):
    data = request.get_json(force=True)
    try:
        lat = float(data["centerLat"])
        lon = float(data["centerLon"])
        radius = float(data["radiusMeters"])
    except (KeyError, TypeError, ValueError):
        return error("centerLat, centerLon and radiusMeters are required numbers.")

    zone_store.save(patient_id, lat, lon, radius)
    return jsonify({"status": "ok"})


@app.route("/api/patients/<int:patient_id>/safezone/check", methods=["POST"])
def check_safezone(patient_id):
    """
    Body can include {"lat":.., "lon":..} to check a specific point (the
    website's map, or the browser's real GPS) - or be sent empty to use
    THIS SERVER's own real GPS (Windows + winsdk), exactly like the
    terminal app's live monitor.
    """
    data = request.get_json(silent=True) or {}
    zone = zone_store.get(patient_id)
    if zone is None:
        return error("No safe zone has been set up yet.", 404)

    if "lat" in data and "lon" in data:
        lat, lon = float(data["lat"]), float(data["lon"])
        source = "provided"
    elif get_current_location is not None:
        location = get_current_location()
        if location is None:
            return error("Could not get this server's current location.", 503)
        lat, lon = location
        source = "server_gps"
    else:
        return error("No coordinates were provided, and this server has no GPS available.", 503)

    safe_zone = SafeZone(zone["center_lat"], zone["center_lon"], zone["radius_meters"])
    status = safe_zone.check_status(lat, lon)
    status.update({"source": source, "lat": lat, "lon": lon})
    return jsonify(status)


# ---------------- AI Assistant (real Ollama model) ----------------

@app.route("/api/patients/<int:patient_id>/assistant", methods=["POST"])
def ask_assistant(patient_id):
    data = request.get_json(force=True)
    question = (data.get("message") or "").strip()
    if not question:
        return error("No message was sent.")

    assistant = get_assistant(patient_id)
    try:
        answer = assistant.ask(question)
    except AssistantError as e:
        return jsonify({"error": str(e), "errorType": e.error_type}), 502

    return jsonify({"reply": answer})


# ---------------- Caregiver / Admin (static account) ----------------

@app.route("/api/caregiver/login", methods=["POST"])
def caregiver_login():
    data = request.get_json(force=True)
    if data.get("username") == CAREGIVER_USERNAME and data.get("password") == CAREGIVER_PASSWORD:
        return jsonify({"status": "ok"})
    return error("Incorrect username or password.", 401)


if __name__ == "__main__":
    print("MEMORA API running on http://127.0.0.1:5000")
    print("Keep this window open while you use the website.")
    app.run(host="127.0.0.1", port=5000, debug=False)
