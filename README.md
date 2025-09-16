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

* Python 3.10+
* pip (Python package manager)
* python3-venv for virtual environment creation
* ffmpeg / ffprobe installed and in PATH (or via `FFMPEG_PATH` / `FFPROBE_PATH`)
* Plex server with valid `plex_token`

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

> **Note:** Set `watch_folders` to `false` when running via cron.

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
