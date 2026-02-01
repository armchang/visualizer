import os
import ast
from datetime import datetime

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

def log(best_config, best_result):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Unique filename with timestamp
    log_file = os.path.join(LOG_DIR, f"best_configs_{best_config['pair']}.log")
    with open(log_file, "a") as f:
        f.write(f"[{timestamp}] Pair Name: {best_config['pair']}, Best Balance={best_result:.2f}, Config={best_config}\n")


import re
import ast

def load_best_config_from_log(filepath):
    best_balance = float('-inf')
    best_config = None

    with open(filepath, "r") as f:
        contents = f.read()

    # Split by pattern: every occurrence of a timestamped entry
    entries = re.findall(r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\][^\[]+", contents)

    for entry in entries:
        try:
            # Extract Best Balance
            match = re.search(r"Best Balance=([\d\.]+)", entry)
            if not match:
                continue
            balance = float(match.group(1))

            # Extract config dictionary
            config_pos = entry.find("Config=")
            if config_pos == -1:
                continue
            config_str = entry[config_pos + len("Config="):]
            config_dict = ast.literal_eval(config_str)

            if balance > best_balance:
                best_balance = balance
                best_config = config_dict

        except Exception as e:
            print(f"Error parsing entry:\n{entry}\n{e}")
            continue

    if best_config is None:
        raise ValueError("No valid best config found in log.")

    return best_config
