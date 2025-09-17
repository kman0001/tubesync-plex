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
The following system packages must be installed for the script to work:

* `git` - for cloning/updating the repository
* `curl` - for downloading FFmpeg
* `tar` and `xz-utils` - for extracting FFmpeg archive
* `python3` (version 3.10 or higher)
* `python3-pip` - Python package manager
* `python3-venv` - for creating virtual environments  
  *(If not available, the script can fallback to `virtualenv` installed via `pip install --user virtualenv`)*

### Python Packages
* Packages listed in `requirements.txt` will be installed automatically in the virtual environment.

### Plex Requirements
* A running Plex server
* A valid `plex_token` for accessing your Plex server

> **Note:**  
> The script will **check for required system packages** before running.  
> If any system packages are missing, it will **display a warning message** and exit.  
> FFmpeg will be installed automatically into the virtual environment (no root permissions required).

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

Edit `config.json` with your Plex server details:

```json
{
    "plex_base_url": "http://localhost:32400",
    "plex_token": "YOUR_PLEX_TOKEN",
    "plex_library_names": ["TV Shows", "Movies"],
    "silent": false,
    "detail": false,
    "subtitles": false,
    "threads": 8,
    "max_concurrent_requests": 4,
    "request_delay": 0.2,
    "watch_folders": false,
    "watch_debounce_delay": 2
}
```

* `plex_base_url`: Plex server URL
* `plex_token`: Plex server token
* `plex_library_names`: List of libraries to sync
* `silent`: Suppress logs if `true`
* `detail`: Show detailed logs if `true`
* `subtitles`: Extract embedded subtitles and upload to Plex (default `false`)
* `threads`: Number of threads for processing files
* `max_concurrent_requests`: Limit concurrent Plex API requests
* `request_delay`: Delay between Plex API requests (seconds)
* `watch_folders`: Enable folder watching (default `false`)
* `watch_debounce_delay`: Debounce delay for folder watching in seconds

> **Note:**  
> Set `watch_folders` to `false` when running via cron.  
> `config.json` file is located at `<base_dir>/config/config.json`.

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
