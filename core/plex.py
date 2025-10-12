import logging
from plexapi.server import PlexServer
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import requests


LOGGER = logging.getLogger("tubesync.plex")




class HTTPDebugSession(requests.Session):
def __init__(self, enable_debug=False):
super().__init__()
self.enable_debug = enable_debug
retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[500,502,503,504])
self.mount("http://", HTTPAdapter(max_retries=retries))
self.mount("https://", HTTPAdapter(max_retries=retries))


def send(self, request, **kwargs):
if self.enable_debug:
LOGGER.debug(f"[HTTP DEBUG] REQUEST: {request.method} {request.url}")
resp = super().send(request, **kwargs)
if self.enable_debug:
LOGGER
