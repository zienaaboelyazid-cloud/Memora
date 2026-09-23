import pyttsx3

from language_utils import detect_language


class TextToSpeech:
    """
    Converts text into spoken audio, fully offline (no internet needed).

    IMPORTANT: pyttsx3 has a well-known bug on Windows where reusing the
    SAME engine instance for multiple speak() calls in one running
    program works the first time, then silently stops producing audio
    (no error - it just doesn't speak). The fix is to create a fresh
    engine for every single speak() call instead of keeping one around -
    that's what this version does.
    """

    def __init__(self, rate=160):
        self.rate = rate
        self._is_speaking = False

    def _create_engine(self):
        engine = pyttsx3.init()
        engine.setProperty("rate", self.rate)
        return engine

    def _pick_voice_for_language(self, engine, lang_code):
        """
        lang_code: 'ar' or 'en'. Searches installed system voices for a
        match. Falls back silently to the default voice if no matching
        voice is installed.
        """
        voices = engine.getProperty("voices") or []

        for voice in voices:
            name = (voice.name or "").lower()
            langs = [str(l).lower() for l in (getattr(voice, "languages", None) or [])]
            haystack = name + " " + " ".join(langs) + " " + (voice.id or "").lower()

            if lang_code == "ar" and ("arabic" in haystack or "ar-" in haystack or "ar_" in haystack):
                return voice.id
            if lang_code == "en" and ("english" in haystack or "en-" in haystack or "en_" in haystack):
                return voice.id

        return None

    def speak(self, text, language_hint=None):
        """
        language_hint: 'ar' or 'en'. If omitted, auto-detected from `text`.
        Creates a brand-new engine for this one utterance (see class
        docstring for why), so every call works reliably, not just the
        first one.
        """
        if not text:
            return

        lang_code = language_hint or ("ar" if detect_language(text) in ("ar", "mixed") else "en")

        engine = self._create_engine()
        voice_id = self._pick_voice_for_language(engine, lang_code)
        if voice_id:
            engine.setProperty("voice", voice_id)

        print(f"[Speaking] ({lang_code}): {text}")

        self._is_speaking = True
        try:
            engine.say(text)
            engine.runAndWait()
        finally:
            engine.stop()
            try:
                # Releases the underlying driver cleanly so the next
                # speak() call gets a completely fresh engine.
                del engine
            except Exception:
                pass
            self._is_speaking = False

    def stop(self):
        """
        Note: since each speak() call now uses its own short-lived engine,
        there's nothing long-running to stop mid-utterance with this
        approach. This method is kept for interface compatibility.
        """
        self._is_speaking = False

    @property
    def is_speaking(self):
        return self._is_speaking