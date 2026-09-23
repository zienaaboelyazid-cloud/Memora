from datetime import datetime

import ollama

from config import (OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT, MAX_HISTORY_MESSAGES,
                    SYSTEM_PROMPT_TEMPLATE, SCHEDULE_REFRESH_HOURS)


class AssistantError(Exception):
    """
    Raised whenever Ollama can't be reached or returns something unusable.
    error_type is one of:
        "connection_refused", "timeout", "model_not_found",
        "invalid_response", "unknown"
    Callers (voice_assistant.py, test_assistant.py) catch this and decide
    what to say/show instead of crashing.
    """

    def __init__(self, message, error_type="unknown"):
        super().__init__(message)
        self.error_type = error_type


class Assistant:
    """
    THE single AI pipeline used by both text and voice input:

        text  -> Assistant.ask() -> Ollama -> reply
        voice -> STT -> Assistant.ask() -> Ollama -> reply -> TTS

    Talks to a REAL local Ollama model (never fake/hard-coded answers),
    keeps conversation history, understands the CURRENTLY LOGGED-IN
    patient's stored facts and live safe-zone status (never someone
    else's - pass the right patient_id in), and replies in whichever
    language the patient used - English, Arabic, or a natural mix of
    both.
    """

    def __init__(self, patient_id=None,
                 base_url=OLLAMA_BASE_URL, model=OLLAMA_MODEL, timeout=OLLAMA_TIMEOUT):
        self.patient_id = patient_id
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self.client = ollama.Client(host=self.base_url)
        self.history = []  # [{"role": "user"/"assistant", "content": "..."}]

    # ---------------- Patient facts (scoped to this account) ----------------

    def _load_memory(self):
        from database.patient_memory import PatientMemory

        try:
            memory = PatientMemory()
            return memory.get_all(self.patient_id)

        except Exception:
            return {}

    def _get_profile_lines(self):
        """
        The patient's own profile (name, age, date of birth, national ID),
        so the assistant can answer "what's my name / how old am I?".
        """
        if self.patient_id is None:
            return []

        try:
            from database.patient_profile import PatientProfile

            info = PatientProfile().get(self.patient_id)
            if not info:
                return []

            return [
                f"- patient_name: {info['name']}",
                f"- patient_age: {info['age']}",
                f"- patient_date_of_birth: {info['date_of_birth']}",
                f"- patient_national_id: {info['national_id']}",
            ]
        except Exception:
            return []

    def _get_family_lines(self):
        """
        Everyone registered under this patient's account (name + how they
        are related to the patient), so "who is Sara?" -> "Sara is your sister".
        """
        if self.patient_id is None:
            return []

        try:
            from database.facedatabase import FaceDatabase

            people = FaceDatabase().list_people(self.patient_id)
            if not people:
                return ["- family_and_known_people: (nobody has been registered yet)"]

            lines = ["- family_and_known_people (name - relationship to the patient - age - notes):"]
            for person in people:
                relationship = (person.get("relationship") or "").strip()
                age = person.get("age")
                notes = (person.get("notes") or "").strip()
                age_part = f"age {age}" if age is not None else "age not recorded"
                notes_part = f"; notes: {notes}" if notes else ""
                if relationship.lower().startswith("patient (self)"):
                    lines.append(f"    * {person['name']} - this is the patient themself - {age_part}{notes_part}")
                elif relationship:
                    lines.append(f"    * {person['name']} - the patient's {relationship} - {age_part}{notes_part}")
                else:
                    lines.append(f"    * {person['name']} - relationship not recorded - {age_part}{notes_part}")
            return lines
        except Exception:
            return []

    def _schedule_for_prompt(self, schedule_text):
        """
        Today's schedule only counts for SCHEDULE_REFRESH_HOURS. After that
        the AI is told it hasn't been updated yet, instead of repeating
        yesterday's plans as if they were today's.
        """
        try:
            from database.patient_memory import PatientMemory

            age_hours = PatientMemory().get_age_hours(self.patient_id, "today_schedule")
            if age_hours is not None and age_hours >= SCHEDULE_REFRESH_HOURS:
                return (f"NOT UPDATED FOR TODAY YET (the last saved schedule is more than "
                        f"{SCHEDULE_REFRESH_HOURS} hours old, so it is out of date)")
        except Exception:
            pass

        if not (schedule_text or "").strip():
            return "nothing scheduled for today"
        return schedule_text

    def _get_location_fact(self):
        """
        Checks the patient's live GPS location against their saved safe
        zone, right now, so the assistant can answer "am I in the safe
        zone?" correctly instead of saying it has no location info.
        Returns a short fact string, or None if this can't be
        determined right now (no GPS, no safe zone set up, etc).
        """
        if self.patient_id is None:
            return None

        try:
            from database.safe_zone_store import SafeZoneStore
            from location.safe_zone import SafeZone

            config = SafeZoneStore().get(self.patient_id)
            if config is None:
                return None

            try:
                from location.gps_tracker import get_current_location
            except Exception:
                return None

            location = get_current_location()
            if location is None:
                return None

            lat, lon = location
            zone = SafeZone(config["center_lat"], config["center_lon"], config["radius_meters"])
            status = zone.check_status(lat, lon)

            if status["inside_safe_zone"]:
                return (f"The patient is currently INSIDE the safe zone "
                        f"({status['distance_meters']} meters from home).")
            return (f"WARNING: the patient is currently OUTSIDE the safe zone "
                    f"({status['distance_meters']} meters from home).")

        except Exception:
            return None

    def _build_system_prompt(self):
        memory = self._load_memory()

        fact_lines = [f"- current_date_and_time: {datetime.now().strftime('%A, %d %B %Y, %I:%M %p')}"]
        fact_lines += self._get_profile_lines()
        fact_lines += self._get_family_lines()

        for k, v in memory.items():
            if k == "today_schedule":
                v = self._schedule_for_prompt(v)
            fact_lines.append(f"- {k}: {v}")

        location_fact = self._get_location_fact()
        if location_fact:
            fact_lines.append(f"- current_location_status: {location_fact}")

        facts = "\n".join(fact_lines) if fact_lines else "(no facts stored yet)"
        return SYSTEM_PROMPT_TEMPLATE.format(facts=facts)

    # ---------------- Main pipeline ----------------

    def ask(self, question):
        """
        Sends `question` to Ollama with full conversation context and
        returns the plain-text reply. Works identically whether the
        question came from typing or from speech-to-text - there is no
        separate "voice" logic here.

        Raises AssistantError on any failure (never returns a fake answer).
        """
        question = (question or "").strip()
        if not question:
            return ""

        self.history.append({"role": "user", "content": question})
        self.history = self.history[-MAX_HISTORY_MESSAGES:]

        messages = [{"role": "system", "content": self._build_system_prompt()}] + self.history

        try:
            response = self.client.chat(model=self.model, messages=messages)
        except ollama.ResponseError as e:
            status = getattr(e, "status_code", None)
            if status == 404:
                raise AssistantError(
                    f"Model '{self.model}' not found. Run: ollama pull {self.model}",
                    error_type="model_not_found",
                )
            raise AssistantError(f"Ollama returned an error: {e}", error_type="invalid_response")
        except Exception as e:
            raise AssistantError(*self._classify_connection_error(e))

        content = self._extract_content(response)

        if not content:
            raise AssistantError("Ollama returned an empty response.", error_type="invalid_response")

        self.history.append({"role": "assistant", "content": content})
        self.history = self.history[-MAX_HISTORY_MESSAGES:]

        return content

    def clear_history(self):
        """Starts a fresh conversation (e.g. when the patient starts a new topic)."""
        self.history = []

    # ---------------- Helpers ----------------

    def _extract_content(self, response):
        """
        Handles both possible shapes the ollama python client can return
        (a plain dict on older versions, or a typed object with
        .message.content on newer ones).
        """
        content = None

        if isinstance(response, dict):
            content = response.get("message", {}).get("content")
        else:
            message = getattr(response, "message", None)
            content = getattr(message, "content", None)

        return content.strip() if isinstance(content, str) else None

    def _classify_connection_error(self, e):
        """
        Turns whatever low-level exception the HTTP client raised into
        one of our structured error types, so the UI/voice layer can
        show a sensible message instead of a stack trace.
        """
        message = str(e).lower()

        if "timed out" in message or "timeout" in message:
            return f"Ollama did not respond in time: {e}", "timeout"

        if "connection" in message or "refused" in message or "failed to establish" in message:
            return f"Could not reach Ollama at {self.base_url}. Is it running?", "connection_refused"

        return f"Unexpected error talking to Ollama: {e}", "unknown"