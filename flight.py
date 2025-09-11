import datetime
import logging
from astral.sun import Observer, sun
import re

from airports import Airports
from config import Config
from metadata import Metadata

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()] 
)

logger = logging.getLogger(__name__)

class Flight():
    def __init__(self, tenant, data):
        self.tenant = tenant
        self.id = data['flightid']
        self.sortval = data["flightdate"]["sortval"]
        self.date = datetime.datetime.fromtimestamp(self.sortval)
        self.actype = data['actype']
        self.callsign = data['callsign']
        self.crew = data['crew']
        self.departure = data['departure']
        self.destination = data['destination']
        self.takeoff = data['takeoff']
        self.landing = data['landing']
        self.blockoff = data['blockoff']
        self.blockon = data['blockon']
        self.landings = data['landings']
        self.airtime = data['airtime']
        self.blocktime = data['blocktime']
        self.pricecat = data['pricecat']
    
    def getID(self) -> str:
        return str(f"{self.tenant}-{self.id}")

    def isPIC(self) -> bool:
        #TODO: move to config
        if self.getID() in ["ffg-1668", "ffg-3575", "ffg-5269"]:
            return False
        if self.getID() in ["ffg-4853", "ffg-4854", "ffg-4855"]:
            return True
    
        # charter flights are always PIC
        if not "charter" in self.pricecat.lower():
            if f"<b>{Config.instance().get('myself').lower() }</b>" in self.crew.lower():
                return True
            if Config.instance().get('myself').lower() == self.crew.lower():
                return True
            return False
        return True
    
    def remove_html_tags(self, text):
        return re.sub(r'<[^>]*>', '', text)
    
    def getCrew(self):
        crew = self.remove_html_tags(self.crew)
        crew = re.sub(r'[0-9]+', '', crew)
        crew = crew.split("/")
        crew = [x for x in crew if not Config.instance().get('myself').lower() in x.lower()]
        crew = [x.strip() for x in crew]
        return crew or []
    
    def getPax(self):
        pax = self.getMetadata("pax")
        if not pax:
            return []
        return pax.split(",")
    
    def getComment(self) -> str:
        return self.getMetadata("comment") or ""
    
    def getPricecat(self) -> str:
        return {
            "Charterflug": "Charter",
            "Schulungsflug": "Schulung",
            "Check-/Einweisungs-/&Uuml;bungsflug": "Check/Einw.",
            "Charterflug mit Kurzfristbuchungsrabatt": "Kurzfristrabatt" 
        }.get(self.pricecat, self.pricecat)
        
    def getMetadata(self, attr: str):
        meta = Metadata.instance().get_metadata(self.getID())
        if meta and attr in meta:
            return meta[attr]
        return None
    
    def getBlocktime(self) -> datetime.timedelta:
        (hours, minutes) = self.blocktime.split(":")
        return datetime.timedelta(hours=int(hours), minutes=int(minutes))
    
    def isNight(self) -> str:
        departure = Airports.instance().airports[self.departure]
        destination = Airports.instance().airports[self.destination]
        sun_dep = sun(Observer(departure['lat'], departure['lon'], departure['elevation']/3.28084), self.date)
        sun_dest = sun(Observer(destination['lat'], destination['lon'], destination['elevation']/3.28084), self.date)
        
        blockoff = datetime.datetime.strptime(self.blockoff, "%H:%M").replace(year=self.date.year,month=self.date.month,day=self.date.day,tzinfo=datetime.timezone.utc)
        blockon = datetime.datetime.strptime(self.blockon, "%H:%M").replace(year=self.date.year,month=self.date.month,day=self.date.day,tzinfo=datetime.timezone.utc)

        if blockoff > sun_dep['dusk'] and blockon > sun_dest['dusk']:
            return True
        return False
