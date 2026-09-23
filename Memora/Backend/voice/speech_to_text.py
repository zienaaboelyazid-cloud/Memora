import speech_recognition as sr

from config import LANGUAGE_MODE, STT_LOCALES, LanguageMode


class SpeechToText:
    """
    Converts spoken audio into text, fully offline (uses Whisper locally,
    no internet needed after the model is downloaded the first time).
    """

    def __init__(self, model="base", timeout=5, phrase_time_limit=5):
        """
        model: whisper model size -> "tiny", "base", "small", "medium", "large"
        timeout: max seconds to wait for the person to START speaking.
        phrase_time_limit: max seconds to record ONE phrase once they start.
        """
        self.recognizer = sr.Recognizer()
        self.model = model
        self.timeout = timeout
        self.phrase_time_limit = phrase_time_limit

        try:
            self.microphone = sr.Microphone()
            self._mic_available = True
        except OSError as e:
            # No microphone connected/detected - don't crash, just report it.
            print(f"Microphone unavailable: {e}")
            self.microphone = None
            self._mic_available = False

    def listen_and_transcribe(self, language=None):
        """
        Listens through the microphone and returns the transcribed text,
        or None if nothing was understood / no speech was detected / no
        microphone is available.

        language: 'ar', 'en', or None.
            None -> uses LANGUAGE_MODE from config:
                - AUTO: Whisper auto-detects the spoken language.
                - ENGLISH / ARABIC: forces that language for better accuracy.
        """
        if not self._mic_available:
            print("No microphone available - cannot listen.")
            return None

        whisper_language = self._resolve_language(language)

        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
            print("[Listening]...")

            try:
                audio = self.recognizer.listen(
                    source,
                    timeout=self.timeout,
                    phrase_time_limit=self.phrase_time_limit
                )
            except sr.WaitTimeoutError:
                print("No speech detected.")
                return None

        print("[Transcribing]...")

        try:
            kwargs = {"model": self.model}
            if whisper_language:
                kwargs["language"] = whisper_language

            text = self.recognizer.recognize_whisper(audio, **kwargs)
            text = text.strip()

            return text if text else None

        except sr.UnknownValueError:
            print("Could not understand the audio.")
            return None
        except Exception as e:
            print(f"Speech recognition error: {e}")
            return None

    def _resolve_language(self, explicit_language):
        if explicit_language:
            return STT_LOCALES.get(explicit_language, explicit_language)

        if LANGUAGE_MODE == LanguageMode.ENGLISH:
            return STT_LOCALES["en"]
        if LANGUAGE_MODE == LanguageMode.ARABIC:
            return STT_LOCALES["ar"]

        return None  # AUTO -> let Whisper auto-detect the spoken language

    @property
    def microphone_available(self):
        return self._mic_available