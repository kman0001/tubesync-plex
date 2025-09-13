# TubeSync Plex Metadata Sync (Personal Update)

This repository is a **personal fork** of [tgouverneur/tubesync-plex](https://github.com/tgouverneur/tubesync-plex) and has been updated for **personal use**.

## Key Changes in this Fork
- Simplified default log output
- Added `-d / --detail` option for detailed metadata updates
- Disallow simultaneous use of `-s / --silent` and `-d / --detail` options

> ⚠️ **Note:** This fork is maintained for personal purposes and may differ from the original repository.


# Tubesync-Plex

Automate updating, dependency management, and running Tubesync-Plex on your system.

---

## Features

- Automatically updates repository if changes exist.
- Creates Python virtual environment if missing.
- Installs or updates dependencies only if needed.
- Runs `tubesync-plex-metadata.py --all` automatically.

---

## Requirements

- Bash shell
- Python 3.x
- `git` installed
- `python3-venv` package

---

## Setup

1. Clone this repository:

```bash
git clone https://github.com/kman0001/tubesync-plex.git
cd tubesync-plex
```

2. Make the update script executable:

```bash
chmod +x update-tubesync.sh
```

---

## Usage

Run the script:

```bash
./update-tubesync.sh
```

### What the script does:

1. **Clone or update the repo**  
   - If the repository exists and has changes, it pulls updates.
   - If the repository doesn’t exist, it clones it.

2. **Check Python virtual environment**  
   - Creates a `venv` folder if missing.

3. **Install or update Python dependencies**  
   - Installs packages listed in `requirements.txt` only if updates are needed.

4. **Run Tubesync-Plex**  
   - Executes `tubesync-plex-metadata.py --all`.

> ⚡ Running the script multiple times will only update files when there are actual changes.

---

## Logging

Each run prints logs with timestamps:

```text
[YYYY-MM-DD HH:MM:SS] START
[YYYY-MM-DD HH:MM:SS] Updating repository...
[YYYY-MM-DD HH:MM:SS] Installing Python dependencies...
[YYYY-MM-DD HH:MM:SS] Running tubesync-plex...
[YYYY-MM-DD HH:MM:SS] END
```

---

## Notes

- If you update scripts directly on GitHub, the script ensures the local copy is pulled automatically.
- Only updated files trigger dependency installation and script execution.







# tubesync-plex

After using TubeSync for a little while, I was frustrated that the title of my youtube videos were not synced from either the NFO or the MKV's metadata in Plex.

I've found a little snippet of code from @RtypeStudios that was updating those title through the PlexAPI.
I found the solution to be very simple and decided to build on it, here is this script.

## Prerequisites

Either run this on your plex server directly or on a VM that has the same path for the media as on the plex server.
Ensure TubeSync is writting your thumbnails and NFOs.

## Usage

```
$ python3 -m venv venv
$ pip3 install -r requirements.txt 
$ cp config.ini-example config.ini
$ vi config.ini
# Tune the variable to suit your plex install
$ python3 tubesync-plex-metadata.py --help
usage: tubesync-plex-metadata.py [-h] [-c CONFIG] [-s] [--all]

TubeSync Plex Media Metadata sync tool

options:
  -h, --help            show this help message and exit
  -c CONFIG, --config CONFIG
                        Path to the config file
  -s, --silent          Run in silent mode
  --subtitles           Find subtitles for the video and upload them to plex
  --all                 Update everything in the library

$ python3 tubesync-plex-metadata.py --all
```

## Caveats

The `--subtitles` option seems to not work on my systems for some reason it returns 400. If anyone get it to work, I'm interested to know...
