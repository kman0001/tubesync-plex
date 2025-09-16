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
      - /your/plex/library1:/plex/library1
      - /your/plex/library2:/plex/library2
      - /your/plex/library3:/plex/library3
    environment:
      - BASE_DIR=/app
      - CONFIG_FILE=/app/config/config.json
```

> Note: The container automatically detects Plex library paths from `config.json` and watches them. There is no need to specify watch directories via environment variables.

## Configuration

You need a `config.json` file. You can copy and edit the sample configuration:

```json
{
    "_comment": {
        "plex_base_url": "Plex server URL, e.g., http://localhost:32400",
        "plex_token": "Plex server token",
        "plex_library_names": "List of Plex libraries to sync, e.g., [\"TV Shows\", \"Movies\"]",
        "silent": "Suppress logs if true",
        "detail": "Show detailed logs if true",
        "subtitles": "Extract embedded subtitles and upload to Plex if true",
        "threads": "Number of threads for processing video files",
        "max_concurrent_requests": "Maximum concurrent Plex API requests",
        "request_delay": "Delay between Plex API requests in seconds",
        "watch_folders": "Enable folder watching (watchdog) if true",
        "watch_debounce_delay": "Debounce delay for folder watching in seconds"
    },
    "plex_base_url": "http://localhost:32400",
    "plex_token": "YOUR_PLEX_TOKEN",
    "plex_library_names": ["TV Shows", "Movies"],
    "silent": false,
    "detail": false,
    "subtitles": false,
    "threads": 8,
    "max_concurrent_requests": 4,
    "request_delay": 0.2,
    "watch_folders": true,
    "watch_debounce_delay": 2
}
```

```bash
cp config.sample.json config.json
```

### Notes

* Only the mounted Plex library folders need **write/delete permission** for NFO updates.
* The container runs in the foreground; it is recommended to use a process manager (like Docker Compose) to keep it running.
* Folder watching is controlled by the `watch_folders` option in `config.json`. The container automatically handles all watched libraries.
* There is no need to specify watch directories via environment variables or command-line options.
