import os
import configparser
import argparse
from plexapi.server import PlexServer
import lxml.etree as ET

video_extensions = (".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".m4v")

def main(config_path, silent, detail, syncAll, subtitles):
    config = configparser.ConfigParser()
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

            nfo_data_file_path = os.path.splitext(part.file)[0] + ".nfo"

            if os.path.exists(nfo_data_file_path):
                if detail:
                    print(f"[-] Parsing NFO: {nfo_data_file_path}")

                try:
                    parser = ET.XMLParser(recover=True)
                    tree = ET.parse(nfo_data_file_path, parser=parser)
                except ET.XMLSyntaxError as e:
                    print(f"[ERROR] Malformed NFO '{nfo_data_file_path}': {e}")
                    continue
                except Exception as e:
                    print(f"[ERROR] Failed to read NFO '{nfo_data_file_path}': {e}")
                    continue

                root = tree.getroot()
                if root is None:
                    continue

                title = root.findtext('title', default='')
                aired = root.findtext('aired', default='')
                plot = root.findtext('plot', default='')

                if detail:
                    print(f"[-] Updating Plex metadata: {title} - Aired: {aired}")

                try:
                    ep.editTitle(title, locked=True)
                    ep.editSortTitle(aired, locked=True)
                    ep.editSummary(plot, locked=True)
                    updated_count += 1
                except Exception as e:
                    print(f"[ERROR] Failed to update Plex for '{part.file}': {e}")
                    continue

                # NFO 삭제
                try:
                    os.remove(nfo_data_file_path)
                    if detail or not silent:
                        print(f"[-] Deleted NFO: {nfo_data_file_path}")
                except Exception as e:
                    print(f"[ERROR] Failed to delete NFO '{nfo_data_file_path}': {e}")

    # 완료 메시지
    if not silent:
        print(f"[INFO] {updated_count} metadata items updated.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='TubeSync Plex Media Metadata sync tool')
    parser.add_argument('-c', '--config', type=str, default='./config.ini', help='Path to the config file')
    parser.add_argument('-s', '--silent', action='store_true', help='Run in silent mode')
    parser.add_argument('-d', '--detail', action='store_true', help='Show detailed update logs')
    parser.add_argument('--all', action='store_true', help='Update everything in the library')
    parser.add_argument('--subtitles', action='store_true', help='Find subtitles for the video and upload them to plex')
    args = parser.parse_args()

    if args.silent and args.detail:
        print("Error: --silent and --detail cannot be used together.")
        exit(1)

    main(args.config, args.silent, args.detail, args.all, args.subtitles)
