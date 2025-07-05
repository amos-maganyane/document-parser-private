from typing import Dict
import yaml
import os

def load_config() -> Dict:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_files = {
        "parsing": "parsing_rules.yaml",
        "nlp": "nlp_config.yaml",
        "pii": "pii_config.yaml"
    }
    
    config = {}
    for key, filename in config_files.items():
        filepath = os.path.join(base_dir, filename)
        try:
            with open(filepath, 'r') as f:
                config[key] = yaml.safe_load(f)
        except FileNotFoundError:
            print(f"Warning: Config file {filename} not found")
            config[key] = {}
    
    return config