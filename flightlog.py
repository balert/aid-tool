import json, os, logging, datetime
from dateutil.relativedelta import relativedelta
from collections import defaultdict
import pandas
import typing
import re
from astral.sun import Observer, sun

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()] 
)

logger = logging.getLogger(__name__)

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        return super().default(obj)

class Flight():
    def __init__(self, metadata, tenant, data, airports):
        self.metadata = metadata
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
        self.airports = airports
    
    def getID(self) -> str:
        return str(f"{self.tenant}-{self.id}")

    def isPIC(self) -> bool:
        if self.getID() in ["ffg-1668", "ffg-3575", "ffg-5269"]:
            return False
        if self.getID() in ["ffg-4853", "ffg-4854", "ffg-4855"]:
            return True
    
        # charter flights are always PIC
        if not "charter" in self.pricecat.lower():
            if "<b>Brenner</b>" in self.crew:
                return True
            if "Brenner" == self.crew:
                return True
            return False
        return True
    
    def getCrew(self):
        crew = FlightLog.remove_html_tags(self.crew)
        crew = re.sub(r'[0-9]+', '', crew)
        crew = crew.split("/")
        crew = [x for x in crew if not "brenner" in x.lower()]
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
        meta = self.metadata.get_metadata(self.getID())
        if meta and attr in meta:
            return meta[attr]
        return None
    
    def getBlocktime(self) -> datetime.timedelta:
        (hours, minutes) = self.blocktime.split(":")
        return datetime.timedelta(hours=int(hours), minutes=int(minutes))
    
    def isNight(self) -> str:
        departure = self.airports[self.departure]
        destination = self.airports[self.destination]
        sun_dep = sun(Observer(departure['lat'], departure['lon'], departure['elevation']/3.28084), self.date)
        sun_dest = sun(Observer(destination['lat'], destination['lon'], destination['elevation']/3.28084), self.date)
        
        blockoff = datetime.datetime.strptime(self.blockoff, "%H:%M").replace(year=self.date.year,month=self.date.month,day=self.date.day,tzinfo=datetime.timezone.utc)
        blockon = datetime.datetime.strptime(self.blockon, "%H:%M").replace(year=self.date.year,month=self.date.month,day=self.date.day,tzinfo=datetime.timezone.utc)

        if blockoff > sun_dep['dusk'] and blockon > sun_dest['dusk']:
            return True
        return False

class Metadata:
    def __init__(self):
        self.load_metadata()    
    
    def load_metadata(self):
        self.metafilename = "metadata.dat"
        if os.path.exists(self.metafilename):
            with open(self.metafilename, "r") as f:
                file_contents = f.read()
                if len(file_contents) > 0:
                    self.metadata = json.loads(file_contents)
                    logger.info("metadata loaded.")
                    return
        self.metadata = defaultdict()
    
    def add_metadata(self, flightid: str, attribute: str, value: str):
        if not flightid in self.metadata:
            self.metadata[flightid] = dict()
        self.metadata[flightid][attribute] = value
        self.write_metadata()
        
    def get_metadata(self, flightid: str):
        if not flightid in self.metadata:
            return None
        return self.metadata[flightid]
        
    def write_metadata(self):
        with open(self.metafilename, "w") as f:
            f.write(json.dumps(self.metadata))

class FlightLog:
    acc_blocktime = None 
    acc_blocktime_pic = None 
    acc_blocktime_night = None
    acc_airtime = None 
    landings = None
    landings_pic = None
    landings_night = None
    landings_nightpic = None
    flights = list()

    def virtual(tenants, metadata, airports):
        flightlog = FlightLog()
        flightlog.metadata = metadata
        flightlog.airports = airports
        for t in tenants:
            tenant = FlightLog.file(t["name"], metadata, airports)
            flightlog.virtual_insert(tenant.get_all())
        return flightlog 
    
    def virtual_insert(self, flights):
        for flight in flights:
            if not any(flight.getID() == f.getID() for f in self.flights):
                self.flights.append(flight)
        self.flights.sort(key=lambda x: x.sortval, reverse=True)
        self.min = min(self.flights, key=lambda x: x.sortval)
        self.max = max(self.flights, key=lambda x: x.sortval)
    
    def file(tenant: str, metadata, airports):
        flightlog = FlightLog()
        flightlog.metadata = metadata
        flightlog.airports = airports
        flightlog.tenant = tenant
        flightlog.load_tenant()
        return flightlog
    
    def __str__(self):
        tenant = self.tenant["name"] if "name" in self.tenant else "n/a"
        base = f"File <{tenant}>" if self.tenant else "Virtual"
        noflights = len(self.flights)
        return f"Flightlog {base}, {noflights} flights."
    
    def load_tenant(self):
        self.filename = 'flightlog_%s.dat' % self.tenant
        if os.path.exists(self.filename):
            with open(self.filename, "r") as f:
                file_contents = f.read()
                if len(file_contents) > 0:
                    self.data = json.loads(file_contents)
                    self.process()
                    return
        self.data = list()
    
    def process(self):
        self.flights = []
        for flight in self.data:
            self.flights.append(Flight(self.metadata, self.tenant, flight, self.airports))
        self.min = min(self.flights, key=lambda x: x.sortval)
        self.max = max(self.flights, key=lambda x: x.sortval)
    
    def store(self, data):
        ids = [f"{f['flightid']}" for f in self.data]
        for flight in data:
            if flight['flightid'] == 0:
                # print("Skipping: ", flight)
                continue
            
            if flight['flightid'] in ids:
                # print("Skipping %s because already exists in data." % flight['flightid'])
                continue
            self.data.append(flight)
        self.write()
        
    def write(self):
        if not hasattr(self, "data"):
            return
        with open(self.filename, "w") as f:
            f.write(json.dumps(self.data, cls=DateTimeEncoder))
    
    def get_flight(self, flight_id: str):
        logger.info(flight_id)
        flight = next((f for f in self.flights if f.getID() == flight_id), None)
        return flight
    
    def get_all(self):
        return self.flights if self.flights else list()
    

    def get_blocktime(self) -> datetime.timedelta: 
        if not self.acc_blocktime:
            self.acc_blocktime = datetime.timedelta(0)
            for flight in self.flights:
                blocktime = datetime.datetime.strptime(flight.blocktime, "%H:%M")
                delta = datetime.timedelta(hours=blocktime.hour, minutes=blocktime.minute)
                self.acc_blocktime += delta
        return self.acc_blocktime
    
    def get_blocktime_pic(self) -> datetime.timedelta: 
        if not self.acc_blocktime_pic:
            self.acc_blocktime_pic = datetime.timedelta(0)
            for flight in self.flights:
                if not flight.isPIC():
                    continue
                blocktime = datetime.datetime.strptime(flight.blocktime, "%H:%M")
                delta = datetime.timedelta(hours=blocktime.hour, minutes=blocktime.minute)
                self.acc_blocktime_pic += delta
        return self.acc_blocktime_pic
    
    def get_blocktime_night(self) -> datetime.timedelta: 
        if not self.acc_blocktime_night:
            self.acc_blocktime_night = datetime.timedelta(0)
            for flight in self.flights:
                if not flight.isNight():
                    continue
                blocktime = datetime.datetime.strptime(flight.blocktime, "%H:%M")
                delta = datetime.timedelta(hours=blocktime.hour, minutes=blocktime.minute)
                self.acc_blocktime_night += delta
        return self.acc_blocktime_night

    def get_airtime(self) -> datetime.timedelta:
        if not self.acc_airtime:
            self.acc_airtime = datetime.timedelta(0)
            for flight in self.flights:
                airtime = datetime.datetime.strptime(flight.airtime, "%H:%M")
                delta = datetime.timedelta(hours=airtime.hour, minutes=airtime.minute)
                self.acc_airtime += delta
        return self.acc_airtime
    
    def get_landings(self) -> int:
        if not self.landings:
            self.landings = sum(int(l.landings) for l in self.flights)
            
        if not self.landings_pic:
            self.landings_pic = sum(int(l.landings) for l in self.flights if l.isPIC())
        
        if not self.landings_night:
            self.landings_night = sum(int(l.landings) for l in self.flights if l.isNight())
        
        if not self.landings_nightpic:
            self.landings_nightpic = sum(int(l.landings) for l in self.flights if l.isNight() and l.isPIC())
            
        return (self.landings, self.landings_pic, self.landings_night, self.landings_nightpic)
    
    def remove_html_tags(text):
        return re.sub(r'<[^>]*>', '', text)
    
    def get_flights_groupedby_person(self):
        grouped = defaultdict(list)
        for flight in self.flights:     
            for person in flight.getCrew():
                person = person.strip()
                if not any(flight.getID() == f.getID() for f in grouped[person]):
                    grouped[person].append(flight)   
            for person in flight.getPax():
                person = person.strip()
                if not any(flight.getID() == f.getID() for f in grouped[person]):
                    grouped[person].append(flight)   
        return grouped 
    
    def get_flights_groupedby_month(self, f_aircraft=None, f_pic=False):
        grouped = defaultdict(list)
        for flight in self.flights:
            if f_aircraft and not f_aircraft.lower() in flight.actype.lower():
                continue
            
            if f_pic and not flight.isPIC():
                continue
            
            grouped[(flight.date.year, flight.date.month)].append(flight)
            
        # fill gaps (empty months)
        if len(grouped) <= 0:
            return (None, dict())
        
        daterange = pandas.date_range(start=self.min.date.replace(day=1), end=self.max.date+relativedelta(months=1), freq='MS', inclusive="both")
        all_months = daterange.to_period('M')
        for month in all_months:
            len(grouped[month.year,month.month])
            
        return (all_months, dict(sorted(grouped.items())))
    
    def get_flights_by_date_period(self, date_from: datetime.datetime, date_till: datetime.datetime) -> list:
        results = list()
        for flight in self.flights:
            if flight.date > date_from and flight.date < date_till:
                results.append(flight)
        return results
    
    def get_aircraft_types(self):
        aircraft = set()
        for flight in self.flights:
            aircraft.add(flight.actype)
        return sorted(aircraft)
    
    def get_callsigns(self):
        aircraft = set()
        for flight in self.flights:
            aircraft.add(flight.callsign)
        return sorted(aircraft)