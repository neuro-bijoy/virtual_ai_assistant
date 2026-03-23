import speech_recognition as sr
import pyttsx3
import requests
import os
import webbrowser
import re
import threading
import time
from gtts import gTTS
import pygame
import io
import queue

# ================= CONFIG =================
OPENROUTER_API_KEY = "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"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# ================= GLOBAL STATE =================
is_speaking = False
language_mode = "english"
stop_speaking = False
speaking_lock = threading.Lock()
command_queue = queue.Queue()  # FIX: Use a proper queue instead of a single variable + lock

# ================= INIT ENGINE ONCE =================
try:
    engine = pyttsx3.init('sapi5')
    engine.setProperty('rate', 165)
    engine.setProperty('volume', 1.0)
    voices = engine.getProperty('voices')
    if voices:
        engine.setProperty('voice', voices[0].id)
    engine_lock = threading.Lock()
    print("Speech engine initialized successfully")
except Exception as e:
    print(f"Error initializing speech engine: {e}")
    engine = None
    engine_lock = threading.Lock()

# ================= CLEAN TEXT =================
def clean_text(text):
    text = re.sub(r"http\S+", "", text)
    text = re.sub(r"[#*_`]", "", text)
    return text.strip()

# ================= SPEAK FUNCTION =================
def speak(text):
    global is_speaking, stop_speaking, language_mode

    if not text:
        return
    text = clean_text(text)
    print("JARVIS:", text)

    if language_mode != "hindi" and engine is None:
        print("Speech engine not available")
        return

    try:
        with speaking_lock:
            is_speaking = True
            stop_speaking = False

        if language_mode == "hindi":
            tts = gTTS(text=text, lang='hi')
            mp3_fp = io.BytesIO()
            tts.write_to_fp(mp3_fp)
            mp3_fp.seek(0)
            pygame.mixer.init()
            pygame.mixer.music.load(mp3_fp)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                if stop_speaking:
                    pygame.mixer.music.stop()
                    break
                time.sleep(0.1)
        else:
            # FIX: Split into sentences but check stop flag between each
            sentences = re.split(r'(?<=[.!?])\s+', text)
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                if stop_speaking:
                    print(">>> Speech interrupted by user")
                    break
                with engine_lock:
                    engine.say(sentence)
                    engine.runAndWait()

    except Exception as e:
        print(f"Speech error: {e}")
        try:
            engine.stop()
        except:
            pass
    finally:
        with speaking_lock:
            is_speaking = False
            stop_speaking = False

# ================= SPEECH RECOGNITION =================
recognizer = sr.Recognizer()

# FIX: Tuned thresholds for noisy environments
recognizer.pause_threshold = 1.2
recognizer.non_speaking_duration = 0.8
recognizer.dynamic_energy_threshold = False   # FIX: DISABLED — dynamic mode was crashing threshold to 0
recognizer.energy_threshold = 1500            # FIX: Fixed safe value that works in quiet AND noisy rooms
# dynamic_energy_ratio NOT used since dynamic mode is off


def calibrate_microphone():
    """
    One-time mic calibration at startup.
    FIX: Do NOT call adjust_for_ambient_noise in every listen loop —
    that was the cause of energy threshold collapsing to 0 each iteration.
    """
    print("Calibrating microphone for ambient noise... please be quiet for 2 seconds.")
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=2.0)
    # After calibration, lock the threshold — never let it drift to 0 again
    if recognizer.energy_threshold < 300:
        recognizer.energy_threshold = 1500
    print(f"Calibration done. Energy threshold set to: {int(recognizer.energy_threshold)}")


def listen_for_command():
    """
    Listen for a single command.
    FIX: No recalibration inside the loop — threshold stays stable.
    """
    with sr.Microphone() as source:
        try:
            print(f"[Listening... energy threshold: {int(recognizer.energy_threshold)}]")

            # FIX: Reduced timeout to 5s; phrase limit 15s (was 30s)
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=15)

            lang = "hi-IN" if language_mode == "hindi" else "en-IN"
            text = recognizer.recognize_google(audio, language=lang)
            return text.strip()

        except sr.WaitTimeoutError:
            return None
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            print(f"Network error during recognition: {e}")
            return None
        except Exception as e:
            print(f"Listener error: {e}")
            return None


# ================= CONTINUOUS LISTENING THREAD =================
def continuous_listener():
    """
    Continuously listens and pushes commands into the queue.
    FIX: Removed the 5-second dead zone between commands.
    FIX: Interrupts speaking immediately when user speaks.
    """
    global stop_speaking, is_speaking

    print(">>> Listening mode activated")

    while True:
        try:
            user_input = listen_for_command()

            if user_input:
                print("You:", user_input)

                # Interrupt speech if JARVIS is currently talking
                if is_speaking:
                    stop_speaking = True
                    time.sleep(0.3)

                # FIX: Use queue — never lose a command, no lock contention
                command_queue.put(user_input)

        except Exception as e:
            print(f"Error in listener thread: {e}")
            time.sleep(0.5)


# ================= AI =================
def ask_ai(prompt):
    global language_mode

    prompt_lower = prompt.lower()
    intro_keywords = [
        "who are you", "tell me about yourself", "about yourself",
        "introduce yourself", "what are you", "who designed you",
        "आप कौन हो", "आपको किसने बनाया", "अपने बारे में बताओ"
    ]

    if any(keyword in prompt_lower for keyword in intro_keywords):
        if language_mode == "hindi":
            return "मैं जार्विस हूँ, श्रीमान बिजय कुमार द्वारा डिज़ाइन किया गया एक बुद्धिमान सिस्टम इंटरफेस।"
        return "I am JARVIS, an intelligent systems interface designed by Mr.Bijoy Kumar."

    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY.startswith("sk-or-v1-"):
        # Warn if using the default/placeholder key from source code
        print("⚠️  WARNING: API key may be invalid or expired. Get a new one from https://openrouter.ai/keys")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "JARVIS Assistant"
    }
    data = {
        "model": "deepseek/deepseek-r1",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are JARVIS, an intelligent systems interface designed by Mr. Bijoy Kumar. "
                    "Keep responses concise — under 3 sentences unless detail is necessary. "
                    + ("Respond only in Hindi." if language_mode == "hindi" else "")
                )
            },
            {"role": "user", "content": prompt}
        ],
        # FIX: Limit tokens to get faster responses
        "max_tokens": 300
    }

    try:
        response = requests.post(OPENROUTER_URL, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        result = response.json()

        if "choices" in result and result["choices"]:
            return result["choices"][0]["message"]["content"]
        return "Sir, unexpected response format."

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            return "Sir, API key is invalid or expired. Please get a new key from openrouter.ai/keys and update the OPENROUTER_API_KEY in the code."
        return f"Sir, HTTP error: {str(e)}"
    except requests.exceptions.Timeout:
        return "सर, अनुरोध का समय समाप्त हो गया।" if language_mode == "hindi" else "Sir, the request timed out. Please try again."
    except requests.exceptions.RequestException as e:
        return f"Sir, network error: {str(e)}"
    except Exception as e:
        return f"Sir, an error occurred: {str(e)}"


# ================= SYSTEM COMMANDS =================
def system_commands(command):
    global language_mode
    cmd = command.lower()

    if any(w in cmd for w in ["shutdown", "shut down", "band karo", "बंद करो"]) and \
       any(w in cmd for w in ["pc", "laptop", "computer", "system"]):
        speak("सिस्टम 3 सेकंड में बंद हो रहा है सर।" if language_mode == "hindi" else "Shutting down the system in 3 seconds, sir.")
        os.system("shutdown /s /t 3")
        return True

    if "open chrome" in cmd or "chrome kholo" in cmd:
        os.system("start chrome")
        speak("क्रोम खोल रहा हूँ सर।" if language_mode == "hindi" else "Opening Chrome, sir.")
        return True

    if "open notepad" in cmd or "notepad kholo" in cmd:
        os.system("notepad")
        speak("नोटपैड खोल रहा हूँ सर।" if language_mode == "hindi" else "Opening Notepad, sir.")
        return True

    if "open calculator" in cmd or "calculator kholo" in cmd:
        os.system("calc")
        speak("कैलकुलेटर खोल रहा हूँ सर।" if language_mode == "hindi" else "Opening Calculator, sir.")
        return True

    if "search" in cmd or "khojo" in cmd:
        query = cmd.replace("search", "").replace("khojo", "").strip()
        if query:
            webbrowser.open(f"https://www.google.com/search?q={query}")
            speak(f"Searching Google for {query}." if language_mode != "hindi" else f"गूगल पर {query} खोज रहा हूँ।")
        else:
            speak("Sir, what would you like me to search for?" if language_mode != "hindi" else "सर, क्या खोजना है?")
        return True

    return False


# ================= MAIN =================
def main():
    global language_mode, stop_speaking

    calibrate_microphone()  # FIX: One-time calibration at startup
    speak("Hello sir. JARVIS online and ready for your command.")

    # Start background listener thread
    listener_thread = threading.Thread(target=continuous_listener, daemon=True)
    listener_thread.start()

    while True:
        try:
            # FIX: Block until a command arrives — no busy-wait, no 5s dead zones
            try:
                user_input = command_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if not user_input:
                continue

            # Exit
            if any(w in user_input.lower() for w in ["exit", "goodbye", "alvida", "band karo jarvis"]):
                speak("ठीक है सर, अलविदा।" if language_mode == "hindi" else "Ok. Goodbye sir.")
                break

            # Switch to Hindi
            if "language mode on" in user_input.lower() or "hindi mein bolo" in user_input.lower():
                language_mode = "hindi"
                speak("ठीक है सर, अब मैं हिंदी में बात करूंगा।")
                continue

            # Switch to English
            if any(w in user_input.lower() for w in [
                "language mode off", "language band karo", "angrezi mein bolo",
                "english mode on", "english mein bolo", "अंग्रेजी", "बंद", "रुको", "चेंज करो", "बदलो"
            ]):
                language_mode = "english"
                speak("Ok sir, switching back to English.")
                continue

            # System commands
            if system_commands(user_input):
                continue

            # AI query — give immediate audio feedback before the slow API call
            speak("ठीक है सर।" if language_mode == "hindi" else "On it, sir.")
            reply = ask_ai(user_input)
            speak(reply)

        except KeyboardInterrupt:
            speak("Interrupted. Shutting down sir.")
            break
        except Exception as e:
            print(f"Error in main loop: {e}")
            speak("An error occurred, but I am still operational sir." if language_mode != "hindi" else "एक त्रुटि हुई सर।")


if __name__ == "__main__":
    main()
