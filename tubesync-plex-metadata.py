import os
import configparser
import argparse
from plexapi.server import PlexServer
import lxml.etree as ET

def main(config_path, silent, syncAll, subtitles):

    config = configparser.ConfigParser()
    config.read(config_path)

    plex_base_url = config['DEFAULT']['plex_base_url']
    plex_token = config['DEFAULT']['plex_token']
    plex_library_name = config['DEFAULT']['plex_library_name']

    plex = PlexServer(plex_base_url, plex_token)
    section = plex.library.section(plex_library_name)

    title_filter = '' if syncAll else 'Episode '

    updated_count = 0

    for ep in section.search(title=title_filter, libtype='episode'):
        for part in ep.iterParts():
            nfo_data_file_path = part.file.replace(".mkv", ".nfo")

            if not os.path.exists(nfo_data_file_path):
                continue

            try:
                parser = ET.XMLParser(recover=True)
                tree = ET.parse(nfo_data_file_path, parser=parser)
            except IOError as e:
                print(f"[ERROR] IOError: Could not open NFO file '{nfo_data_file_path}'. Details: {e}")
                continue
            except ET.XMLSyntaxError as e:
                print(f"[ERROR] XMLSyntaxError: Malformed NFO file '{nfo_data_file_path}'. Details: {e}")
                continue
            except Exception as e:
                print(f"[ERROR] Unexpected error while parsing NFO '{nfo_data_file_path}': {e}")
                continue

            root = tree.getroot()
            if root is None:
                print(f"[ERROR] Empty NFO file '{nfo_data_file_path}'")
                continue

            title = root.findtext('title', default='')
            aired = root.findtext('aired', default='')
            plot = root.findtext('plot', default='')

            if not silent:
                print(f"[-] Updating title: {title} - Aired: {aired}")

            ep.editTitle(title, locked=True)
            ep.editSortTitle(aired, locked=True)
            ep.editSummary(plot, locked=True)
            updated_count += 1

            # NFO 삭제
            try:
                os.remove(nfo_data_file_path)
                if not silent:
                    print(f"[-] Deleted NFO: {nfo_data_file_path}")
            except Exception as e:
                print(f"[WARN] Failed to delete NFO '{nfo_data_file_path}': {e}")

    if not silent:
        print(f"{updated_count} metadata items updated.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='TubeSync Plex Media Metadata sync tool')
    parser.add_argument('-c', '--config', type=str, default='./config.ini', help='Path to the config file')
    parser.add_argument('-s', '--silent', action='store_true', help='Run in silent mode')
    parser.add_argument('--all', action='store_true', help='Update everything in the library')
    parser.add_argument('--subtitles', action='store_true', help='Find subtitles for the video and upload them to Plex')
    args = parser.parse_args()
    main(args.config, args.silent, args.all, args.subtitles)
