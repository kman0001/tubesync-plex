# TubeSync Plex Metadata Sync (Personal Update)

This repository is a **personal fork** of [tgouverneur/tubesync-plex](https://github.com/tgouverneur/tubesync-plex) and has been updated for **personal use**.

## Key Changes in this Fork
- Simplified default log output
- Added `-d / --detail` option for detailed metadata updates
- Disallow simultaneous use of `-s / --silent` and `-d / --detail` options

> ⚠️ **Note:** This fork is maintained for personal purposes and may differ from the original repository.



---
---


# TubeSync-Plex

TubeSync-Plex is a Python script to automatically sync episode metadata from `.nfo` files into your Plex libraries. It supports multiple libraries and can safely remove processed `.nfo` files.

## Features

- Sync metadata (title, aired date, plot) from `.nfo` files to Plex.
- Supports multiple Plex libraries.
- Automatically deletes `.nfo` files after successful update.
- Handles malformed NFO files gracefully.
- Configurable logging and silent mode.
- Works in Docker or host environments.

## Requirements

- Python 3.10+  
- pip (Python package manager)  
- python3-venv for virtual environment creation  
- Plex server with valid `plex_token`

## Installation

1. Create a directory for TubeSync-Plex:

```bash
mkdir -p /volume1/docker/tubesync/tubesync-plex
cd /volume1/docker/tubesync/tubesync-plex
```

2. Download `tubesync-plex.sh` and `tubesync-plex-metadata.py` from this repository.

3. Run the setup script (inside Docker or on host):

```bash
bash /volume1/docker/tubesync/tubesync-plex/tubesync-plex.sh --base-dir /volume1/docker/tubesync/tubesync-plex
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
    "subtitles": false
}
```

- `plex_base_url`: URL to your Plex server
- `plex_token`: Your Plex server token
- `plex_library_names`: List of Plex libraries to sync
- `silent`: Suppress logs if true
- `detail`: Show detailed update logs if true
- `subtitles`: Upload subtitles if available

## Bash Options

- `--base-dir <path>`: Set the base directory where the repository and virtual environment are located. Default: `/volume1/docker/tubesync/tubesync-plex`.
- `--config-file <path>`: (Optional) Specify a custom `config.json` path. If omitted, the script assumes `config.json` is in the base directory.

Example:

```bash
bash tubesync-plex.sh --base-dir /volume1/docker/tubesync/tubesync-plex --config-file /volume1/docker/tubesync/tubesync-plex/config.json
```

## Usage

Run manually:

```bash
bash /volume1/docker/tubesync/tubesync-plex/tubesync-plex.sh --base-dir /volume1/docker/tubesync/tubesync-plex
```

The script will:

1. Update the repository (git fetch + reset to remote `main`).
2. Create a Python virtual environment if missing.
3. Install/update required Python packages.
4. Run metadata sync using `tubesync-plex-metadata.py`.

## Cron Job Example

Automate updates every day at 2:00 AM:

```cron
0 2 * * * /bin/bash /volume1/docker/tubesync/tubesync-plex/tubesync-plex.sh --base-dir /volume1/docker/tubesync/tubesync-plex >> /volume1/docker/tubesync/tubesync-plex/tubesync.log 2>&1
```

## Notes

- The script will **never overwrite existing local files**, except processed `.nfo` files which it deletes after sync.
- For repository updates, the script resets the repository to match the remote `main` branch to avoid local conflicts.
- Use `silent` mode to reduce console output in automated environments.

## License

MIT License
