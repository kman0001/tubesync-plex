# TubeSync-Plex NFO Watch Docker

This Docker container watches your Plex library for `.nfo` files and automatically applies metadata.

## Quick Start

### Docker Compose Example

```yaml
version: "3.9"
services:
  tubesync-plex:
    image: kman0001/tubesync-plex:latest
    container_name: tubesync-plex
    restart: unless-stopped
    volumes:
      - /your/tubesync-plex/config.json:/app/config/config.json:ro
      - /your/plex/library1:/your/plex/library1
      - /your/plex/library2:/your/plex/library2
      - /your/plex/library3:/your/plex/library3
    environment:
      - BASE_DIR=/app
      - WATCH_DIR1=/your/plex/library1
      - WATCH_DIR2=/your/plex/library2
      - WATCH_DIR3=/your/plex/library3
      - CONFIG_FILE=/app/config/config.json
    entrypoint: ["/app/entrypoint/entrypoint_nfo_watch.sh", "--base-dir", "/app", "--watch-dir", "/your/plex/library"]
```

## Configuration

You need a `config.json` file. You can copy and edit the sample configuration:

```json
{
  "_comment": {
    "plex_base_url": "Your Plex server base URL, e.g., http://localhost:32400",
    "plex_token": "Your Plex server token",
    "plex_library_names": "[\"TV Shows\", \"Anime\"]",
    "silent": "true or false",
    "detail": "true or false",
    "subtitles": "true or false"
  },
  "plex_base_url": "",
  "plex_token": "",
  "plex_library_names": [""],
  "silent": false,
  "detail": false,
  "subtitles": false
}
```

```bash
cp config.sample.json config.json
```

### Notes

* Only the mounted Plex library folder (`/your/plex/library`) needs **write/delete permission** for NFO updates.
* `volumes`: maps host directories into the container for access to media and configuration files; `WATCH_DIR1`, `WATCH_DIR2`, etc. specify which directories inside the container should be monitored for `.nfo` file changes.
* `WATCH_DIR1`, `WATCH_DIR2`, etc. can be added as needed, but each corresponding host folder must also be included in the `volumes` section.
* The container runs in the foreground; it is recommended to use a process manager (like Docker Compose) to keep it running.
