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


def load_best_config_from_log(filepath):
    with open(filepath, "r") as f:
        lines = [line.strip() for line in f if line.strip()]
    
    if not lines:
        raise ValueError("No valid config entries found in the log file.")

    last_line = lines[-1]
    
    # Find where "Config=" starts
    config_pos = last_line.find("Config=")
    if config_pos == -1:
        raise ValueError("No Config= found in the last log line.")

    config_str = last_line[config_pos + len("Config="):]

    try:
        # Safe parsing of the dictionary string
        config_dict = ast.literal_eval(config_str)
    except Exception as e:
        raise ValueError(f"Error parsing config: {e}")
    
    return config_dict
