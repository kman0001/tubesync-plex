# TubeSync Plex Metadata Sync (Personal Update)

This repository is a **personal fork** of [tgouverneur/tubesync-plex](https://github.com/tgouverneur/tubesync-plex) and has been updated for **personal use**.

## Key Changes in this Fork

* Simplified default log output.
* Added `-d / --detail` option for detailed metadata updates.
* Added `subtitles` option to automatically extract and upload embedded subtitles to Plex.
* Disallow simultaneous use of `-s / --silent` and `-d / --detail` options.
* Handles multiple subtitle tracks and automatically maps language codes to Plex-compatible ISO 639-1 codes.
* Fully handles extraction failures: PGS/VobSub or other non-text subtitle tracks are safely ignored with warnings.
* Ensures all NFO updates are performed for all supported video files, even if `subtitles=false`.
* Added Batch JSON to NFO Converter for `info.json` to `.nfo` conversion.
* **Added optional folder watching** (`watch_directories`) to automatically process new `.nfo` files.

> ⚠️ **Note:** This fork is maintained for personal purposes and may differ from the original repository.

---

# TubeSync-Plex

TubeSync-Plex is a Python script to automatically sync episode metadata from `.nfo` files into your Plex libraries and optionally upload embedded subtitles. It supports multiple libraries and can safely remove processed `.nfo` files.

## Features

* Sync metadata (title, aired date, plot) from `.nfo` files to Plex.
* Supports multiple Plex libraries.
* Automatically deletes `.nfo` files after successful update.
* Extracts embedded subtitles (MKV or other formats) and uploads them to Plex.

  * Only extractable tracks (SRT, ASS) are uploaded.
  * Non-extractable tracks (PGS, VobSub) are safely ignored with warnings.
* Handles multiple subtitle tracks with proper language mapping (ISO 639-1 codes).
* NFO updates are performed for all supported video files, regardless of subtitle extraction.
* Handles malformed NFO files gracefully.
* Configurable logging (`silent` and `detail` modes).
* Optional folder watching for new `.nfo` files (`watch_directories` in `config.json`).
* Cross-platform: Windows, Linux, Docker.
* Works in Docker or host environments.
* Supports converting JSON metadata to NFO files using the included Batch JSON to NFO Converter.

---

## Requirements

* Python 3.10+
* pip (Python package manager)
* python3-venv for virtual environment creation
* ffmpeg / ffprobe installed and in PATH (or set via `FFMPEG_PATH` / `FFPROBE_PATH`)
* Plex server with valid `plex_token`

---

## Installation

1. Create a directory for TubeSync-Plex:

```bash
mkdir -p /tubesync-plex
cd /tubesync-plex
```

2. Download `tubesync-plex.sh` from this repository.

3. Run the setup script (inside Docker or on host):

```bash
bash /tubesync-plex.sh --base-dir /tubesync-plex
```

> The script will create a virtual environment, install required Python packages, and create a default `config.json` if it does not exist.

---

## Configuration (`config.json`)

Example:

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
    "request_delay": 0.1,
    "retry_count": 3,
    "retry_delay": 1,
    "watch_directories": false
}
```

* `plex_base_url`: URL to your Plex server
* `plex_token`: Your Plex server token
* `plex_library_names`: List of Plex libraries to sync
* `silent`: Suppress logs if true
* `detail`: Show detailed update logs if true
* `subtitles`: Extract embedded subtitles and upload to Plex
* `threads`: Number of concurrent threads for metadata processing
* `max_concurrent_requests`: Maximum simultaneous Plex API calls
* `request_delay`: Delay between Plex API requests (seconds)
* `retry_count`: Number of retries if Plex API edit fails
* `retry_delay`: Delay between retries (seconds)
* `watch_directories`: **Enable automatic folder watching** for new `.nfo` files (`true` or `false`)

> ⚠️ **Important:** When running the script via **cron**, set `"watch_directories": false` to prevent the script from blocking indefinitely waiting for file system events.

---

## Usage

Run manually:

```bash
bash /tubesync-plex.sh --base-dir /tubesync-plex
```

The script will:

1. Update the repository (git fetch + reset to remote `main`).
2. Create a Python virtual environment if missing.
3. Install/update required Python packages.
4. Run metadata sync using `tubesync-plex-metadata.py`.
5. Optionally extract embedded subtitles and upload them to Plex if `subtitles=true`.
6. Optionally watch configured directories for new `.nfo` files (`watch_directories=true`).
7. Safely ignore non-extractable subtitle tracks with warning messages.

---

## Cron Job Example

Automate updates every day at 2:00 AM:

```cron
0 2 * * * /bin/bash /tubesync-plex/tubesync-plex.sh --base-dir /tubesync-plex >> /tubesync-plex/tubesync.log 2>&1
```

> ⚠️ **Note:** Make sure `"watch_directories": false` in `config.json` when running via cron.

---

## Additional Tools

### Batch JSON to NFO Converter (UTF-8 Support)

A simple script to convert `info.json` files into `.nfo` files.
Supports UTF-8 encoded JSON files.

See the [`json_to_nfo`](https://github.com/kman0001/tubesync-plex/tree/main/json_to_nfo) folder for details and usage examples.

---

## License

MIT License
