# TubeSync Plex Metadata Sync (Personal Update)

This repository is a **personal fork** of [tgouverneur/tubesync-plex](https://github.com/tgouverneur/tubesync-plex) and has been updated for **personal use**.

## Key Changes in this Fork
- Simplified default log output.
- Added `-d / --detail` option for detailed metadata updates.
- Added `subtitles` option to automatically extract and upload embedded subtitles to Plex.
- Disallow simultaneous use of `-s / --silent` and `-d / --detail` options.
- Supports Windows, Linux, and Docker environments with automatic ffmpeg/ffprobe path detection.
- Handles multiple subtitle tracks and automatically maps language codes to Plex-compatible ISO 639-1 codes.
- Fully handles extraction failures: PGS/VobSub or other non-text subtitle tracks are safely ignored with warnings.
- Ensures all NFO updates are performed for all supported video files, even if `subtitles=false`.
- Added Batch JSON to NFO Converter for `info.json` to `.nfo` conversion.

> ⚠️ **Note:** This fork is maintained for personal purposes and may differ from the original repository.

---

# TubeSync-Plex

TubeSync-Plex is a Python script to automatically sync episode metadata from `.nfo` files into your Plex libraries and optionally upload embedded subtitles. It supports multiple libraries and can safely remove processed `.nfo` files.

## Features

- Sync metadata (title, aired date, plot) from `.nfo` files to Plex.
- Supports multiple Plex libraries.
- Automatically deletes `.nfo` files after successful update.
- Extracts embedded subtitles (MKV or other formats) and uploads them to Plex.
  - Only extractable tracks (SRT, ASS) are uploaded.
  - Non-extractable tracks (PGS, VobSub) are safely ignored with warnings.
- Handles multiple subtitle tracks with proper language mapping (ISO 639-1 codes).
- NFO updates are performed for all supported video files, regardless of subtitle extraction.
- Handles malformed NFO files gracefully.
- Configurable logging (`silent` and `detail` modes).
- Cross-platform: Windows, Linux, Docker.
- Works in Docker or host environments.
- Supports converting JSON metadata to NFO files using the included Batch JSON to NFO Converter.

## Requirements

- Python 3.10+  
- pip (Python package manager)  
- python3-venv for virtual environment creation  
- ffmpeg / ffprobe installed and in PATH (or set via `FFMPEG_PATH` / `FFPROBE_PATH`)  
- Plex server with valid `plex_token`

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

## Configuration

Edit `config.json` with your Plex server details:

```json
{
    "plex_base_url": "http://localhost:32400",
    "plex_token": "YOUR_PLEX_TOKEN",
    "plex_library_names": ["TV Shows", "Anime"],
    "silent": false,
    "detail": true,
    "subtitles": true
}
```

- `plex_base_url`: URL to your Plex server  
- `plex_token`: Your Plex server token  
- `plex_library_names`: List of Plex libraries to sync  
- `silent`: Suppress logs if true  
- `detail`: Show detailed update logs if true  
- `subtitles`: Extract embedded subtitles and upload to Plex; safely ignores non-extractable tracks with warnings

## Bash Options

- `--base-dir <path>`: Set the base directory where the repository and virtual environment are located.  
- `--config-file <path>`: (Optional) Specify a custom `config.json` path. If omitted, the script assumes `config.json` is in the base directory.  

Example:

```bash
bash tubesync-plex.sh --base-dir /tubesync-plex --config-file /tubesync-plex/config.json
```

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
6. Safely ignore non-extractable subtitle tracks with warning messages.

## Cron Job Example

Automate updates every day at 2:00 AM:

```cron
0 2 * * * /bin/bash /tubesync-plex/tubesync-plex.sh --base-dir /tubesync-plex >> /tubesync-plex/tubesync.log 2>&1
```

## Additional Tools

### Batch JSON to NFO Converter (UTF-8 Support)

A simple script to convert `info.json` files into `.nfo` files.  
Supports UTF-8 encoded JSON files.  

See the [`json_to_nfo`](https://github.com/kman0001/tubesync-plex/tree/main/json_to_nfo) folder for details and usage examples.


### TubeSync-Plex NFO Watch Docker

This Docker container watches your Plex library for .nfo files and automatically applies metadata.

See the [`READMD.md`](https://github.com/kman0001/tubesync-plex/blob/main/entrypoint/READMD.md)) for details.

## Notes

- The script will **never overwrite existing local files**, except processed `.nfo` files which it deletes after sync.  
- For repository updates, the script resets the repository to match the remote `main` branch to avoid local conflicts.  
- Use `silent` mode to reduce console output in automated environments.  
- The `subtitles` feature supports multiple tracks per video file, uploads only extractable tracks, and automatically maps language codes to Plex-compatible ISO 639-1 codes.  
- Compatible with Windows, Linux, and Docker environments. If ffmpeg/ffprobe are not in PATH, set `FFMPEG_PATH` / `FFPROBE_PATH` in environment variables.

## License

MIT License
