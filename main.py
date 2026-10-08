import logging
import re

from core.orchestrator import Orchestrator
from voice.speech_to_text import listen
from voice.text_to_speech import speak

logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # hide noisy library logs

EXIT_WORDS = ("exit", "quit", "goodbye", "goodbye jarvis", "shut down")
YES_WORDS = ("y", "yes", "yeah", "yep", "sure", "ok", "okay", "go ahead", "continue", "do it")


def clean_for_speech(text: str) -> str:
    """Remove markdown symbols so the voice doesn't read them out."""
    return re.sub(r"[*#`_]", "", text)


def ask_confirmation(description: str) -> bool:
    """Level 2 permission prompt: ask the user before a sensitive action."""
    print(f"\nJARVIS: Sir, I'd like to {description}. Would you like me to continue?")
    speak(f"I'd like to {description}. Would you like me to continue?")
    answer = input("(type yes/no, or press ENTER to answer by voice) > ").strip().lower()
    if not answer:
        print("Listening... say yes or no")
        answer = listen().strip().lower()
        print("YOU (voice):", answer)
    return answer.strip(".!? ") in YES_WORDS


def main():
    print("J.A.R.V.I.S - Just A Rather Very Intelligent System")
    print("SYSTEM ONLINE\n")

    try:
        jarvis = Orchestrator(confirm=ask_confirmation)
    except ValueError as error:
        print("ERROR:", error)
        return

    speak("J.A.R.V.I.S online. At your service, Sir.")
    print("Press ENTER to speak, or type a message. Say or type 'exit' to quit.\n")

    while True:
        typed = input("(ENTER = speak) YOU: ").strip()

        if typed:
            user_text = typed
        else:
            print("Listening... speak now")
            user_text = listen()
            if not user_text:
                message = "I didn't catch that, Sir."
                print("JARVIS:", message, "\n")
                speak(message)
                continue
            print("YOU (voice):", user_text)

        if user_text.lower().strip(".!? ") in EXIT_WORDS:
            print("JARVIS: Goodbye, Sir.")
            speak("Goodbye, Sir.")
            break

        reply = jarvis.ask(user_text)
        print("JARVIS:", reply, "\n")
        speak(clean_for_speech(reply))


if __name__ == "__main__":
    main()
