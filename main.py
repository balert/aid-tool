#!/usr/bin/env python3
import requests, json, logging
from bs4 import BeautifulSoup

from config import *
from aid import AID

logger = logging.getLogger(__name__)
logging.basicConfig(filename='aid.log', level=logging.DEBUG)

aid = AID(config_url, config_user, config_pw)
aid.get_flightlog()
print(aid.flightlog)