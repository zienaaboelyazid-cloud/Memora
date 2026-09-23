"""
Full voice conversation with MEMORA:

    MICROPHONE -> SPEECH-TO-TEXT -> USER TEXT -> OLLAMA
    -> AI RESPONSE -> TEXT-TO-SPEECH -> VOICE RESPONSE

Run this file directly to have a natural back-and-forth spoken
conversation. Press Ctrl+C to stop.

This uses the EXACT SAME Assistant class as test_assistant.py (text
mode) - there is only one assistant pipeline, voice just feeds it
transcribed text instead of typed text.
"""

from ai.assistant import Assistant, AssistantError
from voice.speech_to_text import SpeechToText
from voice.text_to_speech import TextToSpeech
from language_utils import detect_language


ERROR_MESSAGES_EN = {
    "connection_refused": "I can't reach the Ollama server. Please make sure it's running.",
    "timeout": "That took too long to respond. Please try again.",
    "model_not_found": "The AI model isn't installed yet. Please check the setup.",
    "invalid_response": "I didn't get a proper response. Please try again.",
    "unknown": "Something went wrong. Please try again.",
}

ERROR_MESSAGES_AR = {
    "connection_refused": "مش قادر أوصل لسيرفر Ollama. اتأكد إنه شغال.",
    "timeout": "الرد استغرق وقت طويل. جرب تاني.",
    "model_not_found": "الموديل مش متثبت لسه. اتأكد من الإعداد.",
    "invalid_response": "مجتليش رد سليم. جرب تاني.",
    "unknown": "حصل خطأ غير متوقع. جرب تاني.",
}


def speak_error(speaker, error: AssistantError, last_user_language: str):
    is_arabic = last_user_language in ("ar", "mixed")
    messages = ERROR_MESSAGES_AR if is_arabic else ERROR_MESSAGES_EN
    speaker.speak(messages.get(error.error_type, messages["unknown"]),
                  language_hint="ar" if is_arabic else "en")


def main():
    print("=== MEMORA Voice Assistant ===")
    print("Press Ctrl+C to stop.\n")

    assistant = Assistant()
    listener = SpeechToText()
    speaker = TextToSpeech()

    if not listener.microphone_available:
        print("No microphone detected - voice mode can't run. "
              "Use test_assistant.py for text mode instead.")
        return

    speaker.speak("Hello! I'm ready. Go ahead and ask me anything.", language_hint="en")

    last_user_language = "en"

    try:
        while True:
            print("\n(Listening for your question...)")
            question = listener.listen_and_transcribe()

            if not question:
                # Nothing understood - just go back to listening,
                # exactly like the "empty input" case in main.py.
                continue

            last_user_language = detect_language(question)
            print(f"You said ({last_user_language}): {question}")

            try:
                answer = assistant.ask(question)
            except AssistantError as e:
                print(f"[Assistant error - {e.error_type}]: {e}")
                speak_error(speaker, e, last_user_language)
                continue

            print(f"Assistant: {answer}")

            reply_language = "ar" if detect_language(answer) in ("ar", "mixed") else "en"
            speaker.speak(answer, language_hint=reply_language)
            # engine.runAndWait() inside speak() blocks until done speaking,
            # so we're automatically ready for the next question right here.

    except KeyboardInterrupt:
        print("\nVoice assistant stopped.")


if __name__ == "__main__":
    main()