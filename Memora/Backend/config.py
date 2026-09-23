"""
Centralized configuration for the whole assistant pipeline.
Change values HERE - nothing else in the codebase should hard-code
the Ollama URL, model name, or language settings.
"""

import os


class LanguageMode:
    AUTO = "auto"
    ENGLISH = "english"
    ARABIC = "arabic"


# ---- Database ----
# ABSOLUTE path, built from THIS file's own location (config.py), not from
# whatever folder you happened to run "python main.py" / "python api_server.py"
# from. This guarantees every part of the app (voice assistant, web API,
# migration script) always reads/writes the exact same memora.db file,
# no matter where you launch it from.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "memora.db")

# ---- MySQL ----
# The app now stores everything in a real MySQL server instead of the
# local memora.db SQLite file. You need MySQL Server INSTALLED AND RUNNING
# on this machine (or reachable over the network) before you start
# main.py / api_server.py - see the README note at the bottom of this file.
#
# Change these 5 values to match your own MySQL setup:
MYSQL_HOST = "localhost"
MYSQL_PORT = 3306
MYSQL_USER = "root"
MYSQL_PASSWORD = ""          # put your MySQL root/user password here
MYSQL_DATABASE = "memora"    # the database is created automatically if missing

# ---- Ollama ----
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3.2"
OLLAMA_TIMEOUT = 30  # seconds

# ---- Language ----
# TEMPORARILY forced to ENGLISH: this machine doesn't have an Arabic
# system voice installed yet, so Arabic replies would be silent (no
# audio, even though the text is correct). Once an Arabic voice is
# installed (see list_voices.py to check), switch this back to AUTO.
LANGUAGE_MODE = LanguageMode.ENGLISH

# Whisper (speech_recognition's recognize_whisper) language codes
STT_LOCALES = {
    "en": "english",
    "ar": "arabic",
}

# ---- Conversation memory ----
MAX_HISTORY_MESSAGES = 20  # keep context bounded so requests stay fast

# ---- Daily schedule ----
# "Today's schedule" expires after this many hours; after that the app asks
# the patient "what do you have today?" again and the AI stops presenting
# the old schedule as today's.
SCHEDULE_REFRESH_HOURS = 24

# ---- System prompt template (section 10 of the spec) ----
SYSTEM_PROMPT_TEMPLATE = """You are the AI assistant for MEMORA, a memory companion app for a patient with memory difficulties.

Understand the language used by the user.
If the user communicates in English, respond in English.
If the user communicates in Arabic, respond in Arabic.
If the user mixes Arabic and English, understand the mixed language naturally and respond naturally.
Prefer the user's language unless the user explicitly requests another language.

Be helpful, clear, concise, and conversational. Maintain conversation context.

Here is what we know about the patient - use ONLY this information for personal facts, never invent anything beyond it:
{facts}

How to use that information:
- The list includes the patient's own profile (name, age, date of birth) and every family member / person they know, each with their relationship to the patient, their age (if recorded), and any short notes/description saved about them.
- When the patient asks who someone is (for example "who is Sara?"), find that person in the list (ignore capital letters and small spelling differences, and Arabic or English spelling of the same name) and answer with how they are related to the patient, speaking to the patient as "you". Example: "Sara is your sister."
- When the patient asks how old someone is, or anything covered by that person's notes (for example their job, favorite things, or other details), answer directly from their age/notes in the list instead of saying you don't know. Only say age/notes are "not recorded" if that field truly says so.
- When the patient asks about themselves (their name, age, birthday), answer from their profile.
- If someone is not in the list, say you don't have that person saved yet. Never guess a relationship, age, or detail that isn't in the list.
- Use current_date_and_time to answer questions about today or the time.
- If today_schedule says it has not been updated yet, tell the patient that their schedule for today has not been entered yet and suggest they update it. Do not read out an old schedule as if it were today's.

If information about the patient is unavailable, clearly state that it is unavailable instead of guessing.

Pay close attention to the patient's emotional tone in what they say (word choice, complaints, expressions of confusion, fear, loneliness, or sadness - for example saying they are sad, scared, tired of everything, that no one is with them, that they want to cry, etc.), even if they do not explicitly say "I am sad".
- If the patient seems sad, upset, anxious, or distressed, respond first with warm, gentle, reassuring words before anything else. Acknowledge their feeling briefly and kindly (for example: "I'm here with you, you're not alone" / "معاك حد وانت مش لوحدك"), speak slowly and simply, and never argue with or dismiss how they feel.
- After comforting them, gently suggest something safe and grounding appropriate to a memory-care patient - for example suggesting they go home / sit somewhere familiar and safe ("يفضل تروح البيت دلوقتي وترتاح شوية"), rest, drink some water, or that a family member/caregiver is nearby and can be reached - instead of just leaving them with the sad feeling.
- Keep this comfort brief and natural, then continue answering whatever they actually asked, if anything.
- Never sound clinical, cold, or scripted when doing this - sound like someone who genuinely cares about them.
"""