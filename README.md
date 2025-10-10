# TubeSync Plex Metadata Sync (Personal Fork)

This repository is a **personal fork** of [tgouverneur/tubesync-plex](https://github.com/tgouverneur/tubesync-plex) with updates for personal use and optimization.

---

## Key Changes in This Fork

* Simplified default log output.
* Added `-d / --detail` option for detailed metadata updates.
* Added `subtitles` option to extract and upload embedded subtitles to Plex. Default: `false`.
* Supports multiple subtitle tracks and maps language codes to Plex-compatible ISO 639-1 codes.
* Fully handles extraction failures: PGS/VobSub or other non-text subtitle tracks are ignored safely with warnings.
* Added folder watching via `watchdog`, which can be enabled/disabled via `config.json` or `--disable-watchdog`.
* Folder watching is automatically disabled when running via cron.
* Batch JSON to NFO converter included for `info.json` → `.nfo`.
* Configurable threading and rate-limiting for Plex API requests to optimize performance.

> ⚠️ **Note:** This fork is maintained for personal use and may differ from the original repository.

---

## TubeSync-Plex Overview

TubeSync-Plex is a Python script that automatically syncs episode metadata from `.nfo` files into Plex libraries and optionally uploads embedded subtitles.
It supports multiple libraries, multithreading, and safe deletion of processed `.nfo` files.

### Features

* Sync metadata (title, aired date, plot) from `.nfo` files to Plex.
* Supports multiple Plex libraries.
* Automatically deletes `.nfo` files after successful sync.
* Extracts embedded subtitles (MKV or other formats) and uploads them to Plex (extractable only: SRT, ASS).
* Handles multiple subtitle tracks with proper ISO 639-1 language mapping.
* Supports malformed NFO files gracefully.
* Configurable logging (`silent` and `detail` modes).
* Folder watching support via `watchdog`.
* Cross-platform: Windows, Linux, Docker.
* JSON → NFO conversion via included batch tool.

---

## Requirements

### System Packages

The following system packages must be installed:

* `git` - for cloning/updating the repository
* `python3` (version 3.10 or higher)
* `pip3` (Python package manager; provided by `python3-pip` package on Debian/Ubuntu)
* `python3-venv` - for creating virtual environments
  *(If not available, the script can fallback to `virtualenv` installed via `pip install --user virtualenv`)*

### Installing System Packages

#### Ubuntu/Debian

```bash
sudo apt-get update
sudo apt-get install -y git python3 python3-pip python3-venv
```

#### Fedora

```bash
sudo dnf install -y git python3 python3-pip python3-virtualenv
```

#### CentOS/RHEL

```bash
sudo yum install -y git python3 python3-pip python3-virtualenv
```

#### Alpine

```bash
sudo apk add git python3 py3-pip py3-virtualenv
```

#### Arch Linux / Manjaro

```bash
sudo pacman -Sy git python python-pip python-virtualenv
```

### Python Packages

* Packages listed in `requirements.txt` will be installed automatically in the virtual environment.

### Plex Requirements

* A running Plex server
* A valid `plex_token` for accessing your Plex server

### Notes
> The script will check for required system packages before running.  
> If any system packages are missing, it will display a warning message and exit.  
> FFmpeg will be installed automatically into the virtual environment (no root permissions required).  
> On systems where `python3-venv` is not available, install `virtualenv` with `pip install --user virtualenv`.

---

## Installation

1. Create a directory for TubeSync-Plex:

```bash
mkdir -p /tubesync-plex
cd /tubesync-plex
```

2. Download `tubesync-plex.sh` from this repository.

3. Run the setup script:

```bash
bash /tubesync-plex.sh --base-dir /tubesync-plex
```

> The script will create a Python virtual environment, install required packages, and generate a default `config.json` if missing.

---

## Configuration

Edit `config.json` with your Plex server and processing settings:

```json
{
    "PLEX_BASE_URL": "http://localhost:32400",
    "PLEX_TOKEN": "YOUR_PLEX_TOKEN",
    "PLEX_LIBRARY_IDS": [1, 2],
    "SILENT": false,
    "DETAIL": false,
    "SUBTITLES": false,
    "ALWAYS_APPLY_NFO": true,
    "THREADS": 8,
    "MAX_CONCURRENT_REQUESTS": 4,
    "REQUEST_DELAY": 0.2,
    "WATCH_FOLDERS": true,
    "WATCH_DEBOUNCE_DELAY": 3,
    "DELETE_NFO_AFTER_APPLY": true
}
```

* `PLEX_BASE_URL`: Base URL of your Plex server. Example: `http://localhost:32400.`
* `PLEX_TOKEN`: Your Plex authentication token.
* `PLEX_LIBRARY_IDS`: **List of libraries to sync**List of Plex library section IDs to process.  
                      Check the Plex Web UI URL:  
                      `://localhost:32400/web/index.html#!/library/sections/1 → ID = 1.`
* `SILENT`: If `true`, only summary logs are printed. Useful for cron jobs.
* `DETAIL`: If `true`, enables verbose debugging logs.
* `SUBTITLES`: If `true`, extracts embedded subtitles and uploads them to Plex. (default `false`)
* `THREADS`: Number of worker threads used for initial scanning and processing.
* `MAX_CONCURRENT_REQUESTS`: Maximum number of concurrent Plex API requests.
* `REQUEST_DELAY`: Delay in seconds between Plex API requests to prevent rate limiting.
* `WATCH_FOLDERS`: If `true`, enables real-time folder monitoring using watchdog. (default `false`)
* `WATCH_DEBOUNCE_DELAY`: Debounce delay (in seconds) for file events to avoid duplicate processing.
* `ALWAYS_APPLY_NFO`: If `true`, NFO metadata is applied **even if the hash matches the cached value.**  
                      Useful if Plex sometimes ignores previous metadata changes. (default `false`)
* `DELETE_NFO_AFTER_APPLY`: If `true`, NFO files are automatically deleted after successful metadata application. (default `true`)

> **Note:**  
> Set WATCH_FOLDERS to false if you're running the script periodically (e.g., via cron).
> The config.json file should be located at <base_dir>/config/config.json.
> Make sure the Plex library IDs are correct; otherwise, no items will be processed.

---

### 🔧 How to Find Plex Token & Library ID

* **Find Your Plex Token**
  1. Open Plex Web App in your browser  
  2. Open Developer Tools (F12) → **Network** tab  
  3. Click any request and look for the `X-Plex-Token` value  
  4. Copy and paste it into `plex_token` in your `config.json`

* **Find Your Plex Library ID**
  1. Open `http://<plex_server>:32400/library/sections?X-Plex-Token=<plex_token>` in a browser  
  2. Look for `<Directory key="X" title="LibraryName">` entries  
  3. The value of `key="X"` is the library ID (e.g., `"1"`, `"2"`)

---

## Usage

Run manually:

```bash
bash /tubesync-plex.sh --base-dir /tubesync-plex
```

Or with command-line options:

```bash
bash /tubesync-plex.sh --base-dir /tubesync-plex --disable-watchdog
```

Python script supports:

* `--config <path>`: Use a custom `config.json` file.
* `--disable-watchdog`: Disable folder watching (useful for cron jobs).

The script will:

1. Update the repository (git fetch + reset to `main`).
2. Create Python virtual environment if missing.
3. Install/update required Python packages.
4. Run metadata sync with `tubesync-plex-metadata.py`.
5. Optionally extract and upload embedded subtitles if `subtitles=true`.
6. Watch folders for new `.nfo` files if `watch_folders=true` and not disabled by `--disable-watchdog`.

---

## Cron Job Example

Automate daily sync at 2:00 AM (with folder watching disabled):

```cron
0 2 * * * /bin/bash /tubesync-plex/tubesync-plex.sh --base-dir /tubesync-plex --disable-watchdog >> /tubesync-plex/tubesync.log 2>&1
```

---

## Docker

TubeSync-Plex can also be run in a Docker container. The container automatically runs the metadata sync and optionally watches your Plex library for new `.nfo` files.

### Quick Start (Docker)

```bash
docker run -d \
  --name tubesync-plex \
  -v /your/local/config.json:/app/config/config.json:ro \
  -v /your/plex/library1:/your/plex/library1 \
  -v /your/plex/library2:/your/plex/library2 \
  -v /your/plex/library3:/your/plex/library3 \
  -e BASE_DIR=/app \
  -e CONFIG_FILE=/app/config/config.json \
  kman0001/tubesync-plex:latest
```

### Notes

* The container will read configuration from `config.json`. Folder watching is enabled only if `"watch_folders": true` in the config.
* Only mounted Plex library folders need **write/delete permission** for NFO updates.
* To disable folder watching inside the container (e.g., for scheduled tasks), set `"watch_folders": false` in `config.json`.

### Docker Compose Example

```yaml
version: "3.9"
services:
  tubesync-plex:
    image: kman0001/tubesync-plex:latest
    container_name: tubesync-plex
    restart: unless-stopped
    volumes:
      - ./tubesync/config.:/app/config
      - /your/plex/library1:/your/plex/library1
      - /your/plex/library2:/your/plex/library2
      - /your/plex/library3:/your/plex/library3
```

> **Tip:** Docker automatically handles folder watching via the `watch_folders` option. You do not need to specify `--disable-watchdog` when running in Docker.

---

## Additional Tools

### Batch JSON → NFO Converter

Convert `info.json` files into `.nfo` files. Supports UTF-8.
See [`json_to_nfo`](https://github.com/kman0001/tubesync-plex/tree/main/json_to_nfo) folder for details.

---

## Notes

* The script **never overwrites existing local files**, except processed `.nfo` files.
* `watch_folders` should be disabled for cron jobs to avoid race conditions.
* Subtitles are uploaded only if extractable, with ISO 639-1 mapping.
* Compatible with Windows, Linux, and Docker.

---

## License

MIT License
