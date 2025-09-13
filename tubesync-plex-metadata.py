import os
import configparser
import argparse
from plexapi.server import PlexServer
import lxml.etree as ET

def main(config_path, silent, syncAll, subtitles, detail):

    config = configparser.ConfigParser()
    config.read(config_path)

    plex_base_url = config['DEFAULT']['plex_base_url']
    plex_token = config['DEFAULT']['plex_token']
    plex_library_name = config['DEFAULT']['plex_library_name']

    plex = PlexServer(plex_base_url, plex_token)
    section = plex.library.section(plex_library_name)

    title_filter = '' if syncAll else 'Episode '

    updated_count = 0  # Count of metadata items updated

    for ep in section.search(title=title_filter, libtype='episode'):
        for part in ep.iterParts():
            nfo_data_file_path = part.file.replace(".mkv", ".nfo")

            if os.path.exists(nfo_data_file_path):
                if detail:
                    print('[-] Trying to parse NFO file')
                try:
                    parser = ET.XMLParser(recover=True)
                    tree = ET.parse(nfo_data_file_path, parser=parser)
                except Exception as e:
                    if detail:
                        print(f"[!] Failed to parse NFO: {e}")
                    continue

                root = tree.getroot()
                if root is None:
                    continue

                # Extract metadata from NFO
                title = root.findtext('title', default='')
                aired = root.findtext('aired', default='')
                plot = root.findtext('plot', default='')

                if detail:
                    print(f"[-] Updating title: {title} - Aired: {aired}")

                # Update Plex metadata
                ep.editTitle(title, locked=True)
                ep.editSortTitle(aired, locked=True)
                ep.editSummary(plot, locked=True)
                updated_count += 1

                # Delete NFO after successful update
                try:
                    os.remove(nfo_data_file_path)
                    if detail:
                        print(f"[-] Deleted NFO: {nfo_data_file_path}")
                except Exception as e:
                    if detail:
                        print(f"[!] Failed to delete NFO: {e}")

    # Summary output
    if not silent and not detail:
        print(f"{updated_count} metadata items updated.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='TubeSync Plex Media Metadata sync tool')
    parser.add_argument('-c', '--config', type=str, default='./config.ini', help='Path to the config file')
    parser.add_argument('-s', '--silent', action='store_true', help='Run in silent mode')
    parser.add_argument('-d', '--detail', action='store_true', help='Show detailed update logs')
    parser.add_argument('--all', action='store_true', help='Update everything in the library')
    parser.add_argument('--subtitles', action='store_true', help='Find subtitles for the video and upload them to Plex')
    
    args = parser.parse_args()

    # --silent and --detail cannot be used together
    if args.silent and args.detail:
        print("Error: --silent and --detail options cannot be used together.")
        exit(1)

    main(args.config, args.silent, args.all, args.subtitles, args.detail)
