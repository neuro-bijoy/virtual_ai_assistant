import speech_recognition as sr
import pyttsx3
import requests
import os
import webbrowser
import re                                                                                           
import threading
import time

# ================= CONFIG ================  
OPENROUTER_API_KEY = ("")
OPENROUTER_URL = ""

# ================= GLOBAL STATE =================
is_speaking = False
stop_speaking = False
speaking_lock = threading.Lock()
last_command_time = time.time()
current_command = None
command_lock = threading.Lock()

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
    print("Speech functionality may not work")
    engine = None
    engine_lock = threading.Lock()

# ================= CLEAN TEXT =================
def clean_text(text):
    text = re.sub(r"http\S+", "", text)
    text = re.sub(r"[#*_`]", "", text)
    return text.strip()

# ================= SPEAK FUNCTION (INTERRUPTIBLE) =================
def speak(text):
    global is_speaking, stop_speaking
    
    if not text:
        return
    text = clean_text(text)
    print("JARVIS:", text)
    
    if engine is None:
        print("Speech engine not available")
        return
    
    try:
        with speaking_lock:
            is_speaking = True
            stop_speaking = False
        
        # Split text into smaller chunks for better interruptibility
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            
            # Check if we should stop speaking
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
recognizer.pause_threshold = 2.0
recognizer.dynamic_energy_threshold = True
recognizer.energy_threshold = 4000  # Adjust based on your environment

def listen_for_command():
    """Listen for a command without printing error messages"""
    global last_command_time
    
    with sr.Microphone() as source:
        try:
            # Quick ambient noise adjustment
            recognizer.adjust_for_ambient_noise(source, duration=0.7)
            
            # Listen with timeout
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=30)
            
            # Try to recognize
            text = recognizer.recognize_google(audio, language="en-IN")
            last_command_time = time.time()
            return text.strip()
            
        except sr.WaitTimeoutError:
            # Timeout is normal, no error message
            return None
        except sr.UnknownValueError:
            # Could not understand, but don't print error
            return None
        except Exception as e:
            # Only print for unexpected errors
            if "RequestError" in str(type(e)):
                print(f"Network error: {e}")
            return None

# ================= CONTINUOUS LISTENING THREAD =================
def continuous_listener():
    """Continuously listens for commands"""
    global current_command, stop_speaking, is_speaking, last_command_time
    
    print(">>> Listening mode activated")
    
    while True:
        try:
            # Check if we've been idle for too long (5 seconds)
            if not is_speaking and (time.time() - last_command_time) > 5:
                print("Listening...")
                last_command_time = time.time()  # Reset timer
            
            # Listen for command
            user_input = listen_for_command()
            
            if user_input:
                print("You:", user_input)
                
                # If Jarvis is speaking, interrupt immediately
                if is_speaking:
                    stop_speaking = True
                    time.sleep(0.2)  # Brief pause to let speech stop
                
                # Set the new command
                with command_lock:
                    current_command = user_input
                
        except Exception as e:
            print(f"Error in listener: {e}")
            time.sleep(0.5)

# ================= AI =================
def ask_ai(prompt):
    prompt_lower = prompt.lower()
    intro_keywords = ["who are you", "tell me about yourself", "about yourself", 
                     "introduce yourself", "what are you", "who designed you"]
    
    if any(keyword in prompt_lower for keyword in intro_keywords):
        return "I am JARVIS, an intelligent systems interface designed by Mr.Bijoy Kumar. My purpose is to assist, analyze and execute tasks efficiently."
    
    if not OPENROUTER_API_KEY:
        return "Sir, please set your OpenRouter API key in the environment variable OPENROUTER_API_KEY"
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    data = {
        "model": "deepseek/deepseek-r1",
        "messages": [
            {"role": "system", "content": "You are JARVIS, an intelligent systems interface designed by Mr.Bijay Kumar. Keep responses concise."},
            {"role": "user", "content": prompt}
        ]
    }
    
    try:
        response = requests.post(
            OPENROUTER_URL,
            headers=headers,
            json=data,
            timeout=60
        )
        response.raise_for_status()
        result = response.json()
        
        if "choices" in result and len(result["choices"]) > 0:
            return result["choices"][0]["message"]["content"]
        else:
            return f"Sir, unexpected response format: {result}"
            
    except requests.exceptions.Timeout:
        return "Sir, the request timed out. Please try again."
    except requests.exceptions.RequestException as e:
        return f"Sir, network error: {str(e)}"
    except KeyError as e:
        return f"Sir, response format error: {str(e)}"
    except Exception as e:
        return f"Sir, an error occurred: {str(e)}"

# ================= SYSTEM COMMANDS =================
def system_commands(command):
    command = command.lower()
    
    # Shutdown command - MUST BE FIRST
    if any(word in command for word in ["shutdown", "shut down"]) and any(word in command for word in ["pc", "laptop", "computer", "system"]):
        speak("Shutting down the system in 3 seconds, sir.")
        os.system("shutdown /s /t 3")
        return True
    
    if "open chrome" in command:
        try:
            os.system("start chrome")
            speak("Opening Chrome, sir.")
            return True
        except:
            speak("Unable to open Chrome, sir.")
            return True
    
    if "open notepad" in command:
        try:
            os.system("notepad")
            speak("Opening Notepad, sir.")
            return True
        except:
            speak("Unable to open Notepad, sir.")
            return True
    
    if "open calculator" in command:
        try:
            os.system("calc")
            speak("Opening Calculator.")
            return True
        except:
            speak("Unable to open Calculator, sir.")
            return True
    
    if "search" in command:
        query = command.replace("search", "").strip()
        if query:
            webbrowser.open(f"https://www.google.com/search?q={query}")
            speak(f"Searching Google for {query}.")
        else:
            speak("What would you like me to search for, sir?")
        return True
    
    return False

# ================= MAIN =================
def main():
    global current_command, last_command_time
    
    speak("Hello sir. Jarvis online and ready.")
    
    # Start continuous listening in background
    listener_thread = threading.Thread(target=continuous_listener, daemon=True)
    listener_thread.start()
    
    # Update last command time
    last_command_time = time.time()
    
    while True:
        try:
            # Check if there's a new command
            with command_lock:
                if current_command:
                    user_input = current_command
                    current_command = None  # Clear the command
                else:
                    user_input = None
            
            # If no command, just wait a bit
            if not user_input:
                time.sleep(0.1)
                continue
            
            # Process the command
            if "exit" in user_input.lower() or "stop" in user_input.lower() or "goodbye" in user_input.lower():
                speak("Ok. Goodbye sir.")
                break
            
            if system_commands(user_input):
                continue
            speak("Let me think, sir.")
            reply = ask_ai(user_input)
            speak(reply)
            
        except KeyboardInterrupt:
            speak("Interrupted. Shutting down sir.")
            break
        except Exception as e:
            print(f"Error in main loop: {e}")
            speak("An error occurred, but I'm still operational sir.")

if __name__ == "__main__":
    main()  
