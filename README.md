# TubeSync Plex Metadata Sync (Personal Update)

This repository is a **personal fork** of [tgouverneur/tubesync-plex](https://github.com/tgouverneur/tubesync-plex) and has been updated for **personal use**.

## Key Changes in this Fork
- Simplified default log output
- Added `-d / --detail` option for detailed metadata updates
- Disallow simultaneous use of `-s / --silent` and `-d / --detail` options

> ⚠️ **Note:** This fork is maintained for personal purposes and may differ from the original repository.



---
---



# TubeSync Plex Metadata Sync

This project allows you to synchronize NFO metadata files with your Plex library.

## Features

* Updates Plex metadata (title, aired date, plot) from NFO files.
* Deletes NFO files after successful update.
* Supports common video file types: `.mkv`, `.mp4`, `.avi`, `.mov`, `.wmv`, `.flv`, `.m4v`.
* Supports subtitles upload (optional).
* Logs detailed updates and errors.

## Installation

Clone the repository and set up the Python environment:

```bash
git clone https://github.com/kman0001/tubesync-plex.git
cd tubesync-plex
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Configuration

The script uses a `config.json` file to store configuration options.

### config.json Example

```json
{
    "base_dir": ".",
    "plex_base_url": "http://127.0.0.1:32400",
    "plex_token": "YOUR_PLEX_TOKEN",
    "plex_library_name": "TV Shows",
    "video_extensions": [".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".m4v"]
}
```

* `base_dir`: Directory where the script resides (used for virtual environment and repo updates).
* `plex_base_url`: URL of your Plex server.
* `plex_token`: Your Plex token.
* `plex_library_name`: The Plex library to update.
* `video_extensions`: List of video file extensions to process.

**Note:** If `config.json` does not exist, the script will create it with default values and prompt you to fill in the necessary fields.

## Usage

### Python Script

Run the metadata sync:

```bash
python tubesync-plex-metadata.py [options]
```

**Options:**

* `-s, --silent` : Run in silent mode (no output except errors).
* `-d, --detail` : Show detailed logs.
* `--all`        : Update all items in the library.
* `--subtitles`  : Upload subtitles if found.

**Example:**

```bash
python tubesync-plex-metadata.py --all -d --subtitles
```

### Shell Script

The `update.sh` script automates repository updates and runs the metadata sync.

```bash
./update.sh
```

You can specify a custom config file via environment variable:

```bash
export CONFIG_FILE="/path/to/config.json"
./update.sh
```

### Modifying `update.sh`

* `BASE_DIR` is determined from `CONFIG_FILE` automatically.
* Python virtual environment is created in `BASE_DIR/venv`.
* Dependencies are installed automatically.

### Notes

* The script only deletes NFO files **after successful metadata update**.
* Malformed or unreadable NFO files are logged, but **not deleted**.
* The script processes only video files matching the extensions in `config.json`.
* The script must have network access to the Plex server.

## License

MIT License


