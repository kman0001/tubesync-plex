import os
import configparser
import argparse
from plexapi.server import PlexServer
import lxml.etree as ET

video_extensions = (".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".m4v")

def main(config_path, silent, detail, syncAll, subtitles):
    config = configparser.ConfigParser()

    if not os.path.exists(config_path):
        # 기본 config.ini 생성
        config['DEFAULT'] = {
            'plex_base_url': 'http://localhost:32400',
            'plex_token': 'YOUR_PLEX_TOKEN',
            'plex_library_name': 'YOUR_LIBRARY_NAME'
        }
        with open(config_path, 'w', encoding='utf-8') as f:
            config.write(f)
        print(f"[INFO] Created default config file: {config_path}")
        print("Please edit this file to add your Plex server details, then run the script again.")
        return  # 생성 후 바로 종료

    config.read(config_path)

    plex_base_url = config['DEFAULT']['plex_base_url']
    plex_token = config['DEFAULT']['plex_token']
    plex_library_name = config['DEFAULT']['plex_library_name']

    plex = PlexServer(plex_base_url, plex_token)
    section = plex.library.section(plex_library_name)

    title_filter = 'Episode ' if not syncAll else ''

    updated_count = 0

    for ep in section.search(title=title_filter, libtype='episode'):
        for part in ep.iterParts():
            if not part.file.lower().endswith(video_extensions):
                continue

            nfo_path = os.path.splitext(part.file)[0] + ".nfo"

            if os.path.exists(nfo_path):
                if detail:
                    print(f"[-] Parsing NFO: {nfo_path}")
                try:
                    parser = ET.XMLParser(recover=True)
                    tree = ET.parse(nfo_path, parser=parser)
                except ET.XMLSyntaxError as e:
                    print(f"[ERROR] Malformed NFO: {nfo_path}. Details: {e}")
                    continue
                except Exception as e:
                    print(f"[ERROR] Failed to read NFO: {nfo_path}. Details: {e}")
                    continue

                root = tree.getroot()
                if root is None:
                    continue

                title = root.findtext('title', default='')
                aired = root.findtext('aired', default='')
                plot = root.findtext('plot', default='')

                if detail:
                    print(f"[-] Updating: {title} - Aired: {aired}")

                ep.editTitle(title, locked=True)
                ep.editSortTitle(aired, locked=True)
                ep.editSummary(plot, locked=True)

                updated_count += 1

                try:
                    os.remove(nfo_path)
                    if not silent:
                        print(f"[-] Deleted NFO: {nfo_path}")
                except Exception as e:
                    print(f"[ERROR] Failed to delete NFO: {nfo_path}. Details: {e}")

    if not silent:
        print(f"[INFO] {updated_count} metadata items updated.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TubeSync Plex Media Metadata sync tool")
    parser.add_argument('-c', '--config', type=str, default='./config.ini', help='Path to config file')
    parser.add_argument('-s', '--silent', action='store_true', help='Run in silent mode')
    parser.add_argument('-d', '--detail', action='store_true', help='Show detailed logs')
    parser.add_argument('--all', action='store_true', help='Update all episodes')
    parser.add_argument('--subtitles', action='store_true', help='Upload subtitles to Plex')
    args = parser.parse_args()

    if args.silent and args.detail:
        print("Error: --silent and --detail cannot be used together.")
        exit(1)

    main(args.config, args.silent, args.detail, args.all, args.subtitles)
