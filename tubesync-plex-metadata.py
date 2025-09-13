import os
import json
import argparse
from plexapi.server import PlexServer
import lxml.etree as ET

# Common video file extensions
video_extensions = (".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".m4v")

def main(config_path, silent, detail, syncAll, subtitles):
    # If config.json does not exist, create a template
    if not os.path.exists(config_path):
        default_config = {
            "plex_base_url": "http://localhost:32400",
            "plex_token": "YOUR_PLEX_TOKEN",
            "plex_library_name": "MyLibrary"
        }
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=4)
        print(f"[INFO] config.json has been created: {config_path}")
        print("Please fill in the details and run the script again.")
        return

    # Load Plex configuration
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    plex_base_url = config['plex_base_url']
    plex_token = config['plex_token']
    plex_library_name = config['plex_library_name']

    plex = PlexServer(plex_base_url, plex_token)
    section = plex.library.section(plex_library_name)

    title_filter = 'Episode ' if not syncAll else ''
    updated_count = 0

    # Iterate over episodes in the Plex library
    for ep in section.search(title=title_filter, libtype='episode'):
        for part in ep.iterParts():
            # Skip non-video files
            if not part.file.lower().endswith(video_extensions):
                continue

            nfo_data_file_path = os.path.splitext(part.file)[0] + ".nfo"

            if os.path.exists(nfo_data_file_path):
                if detail:
                    print(f"[-] Parsing NFO file for {part.file}")
                try:
                    parser = ET.XMLParser(recover=True)
                    tree = ET.parse(nfo_data_file_path, parser=parser)
                except ET.XMLSyntaxError as e:
                    print(f"[ERROR] Malformed NFO for '{part.file}': {e}")
                    continue
                except Exception as e:
                    print(f"[ERROR] Failed to read NFO '{part.file}': {e}")
                    continue

                root = tree.getroot()
                if root is None:
                    continue

                title = root.findtext('title', default='')
                aired = root.findtext('aired', default='')
                plot = root.findtext('plot', default='')

                if detail:
                    print(f"[-] Updating metadata: {title} - Aired: {aired}")

                ep.editTitle(title, locked=True)
                ep.editSortTitle(aired, locked=True)
                ep.editSummary(plot, locked=True)
                updated_count += 1

                # Delete NFO after successful update
                try:
                    os.remove(nfo_data_file_path)
                    if not silent:
                        print(f"[-] Deleted NFO: {nfo_data_file_path}")
                except Exception as e:
                    print(f"[ERROR] Failed to delete NFO '{nfo_data_file_path}': {e}")

    if updated_count > 0 and not silent:
        print(f"[INFO] {updated_count} metadata items updated.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='TubeSync Plex Media Metadata Sync Tool')
    parser.add_argument('-c', '--config', type=str, default='./config.json', help='Path to config.json')
    parser.add_argument('-s', '--silent', action='store_true', help='Minimal logs')
    parser.add_argument('-d', '--detail', action='store_true', help='Show detailed logs')
    parser.add_argument('--all', action='store_true', help='Update all episodes in the library')
    parser.add_argument('--subtitles', action='store_true', help='Upload subtitles to Plex')
    args = parser.parse_args()

    if args.silent and args.detail:
        print("Error: --silent and --detail cannot be used together.")
        exit(1)

    main(args.config, args.silent, args.detail, args.all, args.subtitles)
