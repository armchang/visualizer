import os
import json

# 📁 Path to where you store your pattern rule logs
RULE_LOG_DIR = "logs/pattern_rules"
os.makedirs(RULE_LOG_DIR, exist_ok=True)

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

def load_pattern_rules(pair: str, interval: str):
    """
    Try to load existing pattern rules from a JSON log file.
    If not found or empty, return None.
    """
    file_path = os.path.join(RULE_LOG_DIR, f"{pair}_{interval}_rules.json")
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, 'r') as f:
            rules = json.load(f)
            return rules if rules else None
    except Exception as e:
        print(f"[load_pattern_rules] Failed to load rules: {e}")
        return None

def save_pattern_rules(pair: str, interval: str, rules: list):
    """
    Save extracted pattern rules into a JSON log file for reuse.
    """
    file_path = os.path.join(RULE_LOG_DIR, f"{pair}_{interval}_rules.json")
    try:
        with open(file_path, 'w') as f:
            json.dump(rules, f, indent=2)
        print(f"[save_pattern_rules] Saved {len(rules)} rules to {file_path}")
    except Exception as e:
        print(f"[save_pattern_rules] Failed to save rules: {e}")

def compile_rule_filter(rules):
    """
    Generate a should_avoid_trade(row) function from stored rules.
    """
    def should_avoid_trade(row):
        for feature, bin_label, _, _ in rules:
            try:
                val = row.get(feature.split()[0]) if " " in feature else row.get(feature)
                if val == bin_label:
                    return True
            except Exception:
                continue
        return False
    return should_avoid_trade
