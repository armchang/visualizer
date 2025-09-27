import os

def run():
    # macOS / Linux
    if os.name == "posix":
        os.system("clear")
    # Windows
    elif os.name == "nt":
        os.system("cls")