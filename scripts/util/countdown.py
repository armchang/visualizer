import threading
import time
import sys

def countdown_input(prompt, timeout=5, default="n"):
    print(f"{prompt} (auto-default to '{default}' in {timeout}s): ", end="", flush=True)
    user_input = []

    def read_input():
        try:
            inp = input()
            user_input.append(inp.strip().lower())
        except EOFError:
            pass

    t = threading.Thread(target=read_input)
    t.daemon = True
    t.start()
    t.join(timeout)

    if user_input:
        return user_input[0]
    else:
        return default