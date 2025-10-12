import json
from pathlib import Path
import sys

def load_config(config_file: Path, default_config: dict):
    if not config_file.exists():
        config_file.parent.mkdir(parents=True, exist_ok=True)
        with config_file.open("w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=4, ensure_ascii=False)
        print(f"[INFO] {config_file} created. Please edit it and rerun.")
        sys.exit(0)

    with config_file.open("r", encoding="utf-8") as f:
        config = json.load(f)
    return config
