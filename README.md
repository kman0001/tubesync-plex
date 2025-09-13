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

A tool to sync metadata from NFO files to your Plex library automatically.

---

## Requirements

* Python 3.10+
* `python3-venv` package installed
* Plex server with a valid token
* Permissions to read/write Plex library metadata
* Bash shell for running `tubesync-plex.sh`

---

## Setup

1. **Clone or download the repository**
   You can either clone the repo manually or let the shell script handle it:

```bash
export CONFIG_FILE="./config.json"
/bin/bash tubesync-plex.sh
```

2. **Python virtual environment**
   The script will automatically create a `venv` in the same folder as `tubesync-plex.sh` and install dependencies from `requirements.txt`.

3. **Configuration file (`config.json`)**
   The first time you run the Python script, a default `config.json` will be created if it does not exist.
   Edit it to provide your Plex server details:

```json
{
    "_comment": {
        "plex_base_url": "Your Plex server base URL, e.g., http://localhost:32400",
        "plex_token": "Your Plex server token",
        "plex_library_name": "Name of the library to sync metadata",
        "silent": "true or false, whether to suppress logs",
        "detail": "true or false, whether to show detailed update logs",
        "syncAll": "true or false, whether to update all items",
        "subtitles": "true or false, whether to upload subtitles if available"
    },
    "plex_base_url": "",
    "plex_token": "",
    "plex_library_name": "",
    "silent": false,
    "detail": false,
    "syncAll": false,
    "subtitles": false
}
```

4. **Permissions**
   Ensure the user running the script has read/write access to:

   * Plex library folder for metadata updates
   * NFO files in the library
   * Log file location

---

## Running

Run the shell script:

```bash
/bin/bash tubesync-plex.sh
```

* It will clone or update the repository.
* Check/install Python virtual environment.
* Install/update dependencies.
* Run the Python script using the JSON configuration.

### Options in `config.json`

* `silent`: Suppress console logs if true.
* `detail`: Show detailed logs for each NFO processed.
* `syncAll`: Update all items in the library instead of filtering by default title.
* `subtitles`: Automatically upload subtitles if available.

---

## NFO Handling

* Only video files with common extensions (`.mkv`, `.mp4`, `.avi`, `.mov`, `.wmv`, `.flv`, `.m4v`) are processed.
* Metadata (title, aired date, plot) is read from NFO files and applied to Plex.
* NFO files are **deleted only after successful metadata update**.
* If parsing fails or Plex update fails, NFO files are **not deleted**.
* Errors are logged, depending on the `silent` and `detail` options.

---

## Running Periodically with Cron

1. Open the cron editor:

```bash
crontab -e
```

2. Add a line like this to run the script every day at 3 AM:

```bash
0 3 * * * /bin/bash /path/to/tubesync-plex.sh >> /path/to/tubesync.log 2>&1
```

* Replace `/path/to/tubesync-plex.sh` with the full path to your script.
* `>> /path/to/tubesync.log 2>&1` logs all output including errors.
* Adjust the schedule as needed:

  * `*/30 * * * *` → every 30 minutes
  * `0 0 * * 0` → every Sunday at midnight

---

## Notes

* `tubesync-plex.sh` should have execution permission:

```bash
chmod +x tubesync-plex.sh
```

* Ensure Plex library user has sufficient permissions to update metadata and delete NFO files.
* Python virtual environment and dependencies are automatically handled by the shell script.

