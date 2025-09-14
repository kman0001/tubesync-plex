# Batch JSON to NFO Converter (UTF-8 Support)

This script automatically generates **Plex/Kodi compatible NFO files** from `yt-dlp` downloaded `info.json` files.
It includes UTF-8 encoding to ensure Japanese, Korean, and special characters display correctly.
If an image file with the same name exists (`.jpg`, `.png`, `.jpeg`, `.webp`), it will automatically be used as the NFO thumbnail.
Both the YAML template and the JSON folder can be specified via **command-line options**.

---

## Example Folder Structure

```
/project
  ├─ videos/                     # Folder containing info.json and image files
  │    ├─ video1.info.json
  │    ├─ video1.jpg
  │    ├─ video2.info.json
  │    └─ video2.webp
  ├─ tubesync.yaml               # YAML template
  └─ json_to_nfo.py              # Conversion script (UTF-8 included)
```

---

## Requirements

* Python 3.7 or higher
* PyYAML

```bash
pip install pyyaml
```

---

## Usage

1. Place the `.info.json` files and optional image files in the `videos` folder.

2. Create a YAML template file. Example structure:

```yaml
title: "{title}"
showtitle: "{showtitle}"
season: "{season}"
episode: "{episode}"
ratings:
  - name: "youtube"
    max: 5
    default: true
    value: "{rating_value|default:0}"
    votes: "{rating_votes|default:0}"
plot: "{description}"
thumb: "{thumbnail}"
runtime: "{duration}"
id: "{id}"
uniqueid:
  type: "youtube"
  default: true
  value: "{id}"
studio: "{uploader}"
aired: "{upload_date|date:%Y-%m-%d}"
dateadded: "{dateadded|default:now:%Y-%m-%d %H:%M:%S}"
genre: "{genre}"
```

3. Run the script:

```bash
# Default options
python json_to_nfo.py

# Specify a YAML template
python json_to_nfo.py --yaml /volume1/docker/tubesync/nfo/tubesync.yaml

# Specify both JSON folder and YAML template
python json_to_nfo.py --json-folder /volume1/docker/tubesync/nfo/videos --yaml /volume1/docker/tubesync/nfo/tubesync.yaml
```

* NFO files will be generated for all `.json` files in the `videos` folder.
* The `.info` part of `.info.json` filenames is automatically removed, creating `.nfo` files.
* If an image file with the same name exists, it will be used as the `<thumb>`.
* If no image file exists, the `thumbnail` URL in the info.json will be used.

---

## Plex/Kodi Compatibility

* Generated NFO files can be used directly in Plex and Kodi for TV series and movie metadata.
* UTF-8 encoding ensures Japanese, Korean, and special characters are displayed correctly.
* Includes thumbnail, title, season/episode, plot, studio, genre, and rating information.

---

## Notes

* JSON and image filenames must match exactly for thumbnails to be applied.
* `.info` in `.info.json` filenames is automatically removed.
* All files in the folder are processed, so remove any unnecessary JSON files before running.

---

## Additional Features

* Specify YAML template and JSON folder via command-line options.
* Can be integrated as a **Post-hook** after `yt-dlp` downloads.
* UTF-8 encoding ensures multi-byte characters are safe.
