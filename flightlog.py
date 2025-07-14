import json, os, logging, datetime
from collections import defaultdict
import pandas
import typing
import re

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

class FlightLog():
    acc_blocktime = None 
    acc_blocktime_pic = None 
    acc_airtime = None 
    landings = None
    flights = list()
    
    def __init__(self, tenant=None):
        if not tenant:
            tenant = "merged"
        self.tenant = tenant
        self.filename = 'flightlog_%s.dat' % tenant
        if os.path.exists(self.filename):
            with open(self.filename, "r") as f:
                file_contents = f.read()
                if len(file_contents) > 0:
                    self.data = json.loads(file_contents)
                    self.process()
                else: 
                    self.data = list()
        else:
            self.data = list()
    
    def get_persons(self, flight):
        persons = FlightLog.remove_html_tags(flight["crew"])
        persons = re.sub(r'[0-9]+', '', persons)
        persons = persons.split("/")
        persons = [x for x in persons if not "brenner" in x.lower()]
        persons = [x.strip() for x in persons]
        return persons
    
    def process(self):
        self.flights = []
        for flight in self.data:
            flight["pic"] = self.is_pic(flight)
            flight["date"] = datetime.datetime.fromtimestamp(flight["flightdate"]["sortval"])
            flight["year"] = flight["date"].year
            flight["month"] = flight["date"].month
            flight["persons"] = ", ".join(self.get_persons(flight))
            self.flights.append(flight)
        self.min = min(self.flights, key=lambda x: x["flightdate"]["sortval"])
        self.max = max(self.flights, key=lambda x: x["flightdate"]["sortval"])
    
    def store(self, data):
        flightids = [f"{f['tenant']}-{f['flightid']}" for f in self.data]
        for flight in data:
            if flight['flightid'] == 0:
                # print("Skipping: ", flight)
                continue
            
            flightid = f"{flight['tenant']}-{flight['flightid']}"

            if flightid in flightids:
                # print("Skipping %s because already exists in data." % flight['flightid'])
                continue
            self.data.append(flight)
        self.write()
    
    def get_flight(self, flight_id: str):
        logger.info(flight_id)
        flight = next((f for f in self.flights if f"{f['tenant']}-{f['flightid']}" == flight_id), None)
        return flight
    
    def get_all(self):
        return self.flights if self.flights else list()
    
    def sort(self):
        if not hasattr(self, "data"):
            return
        self.data.sort(key=lambda x: x['flightdate']['sortval'])
        self.write()
        
    def write(self):
        if not hasattr(self, "data"):
            return
        with open(self.filename, "w") as f:
            f.write(json.dumps(self.data, cls=DateTimeEncoder))

    def get_blocktime(self) -> datetime.timedelta: 
        if not self.acc_blocktime:
            self.acc_blocktime = datetime.timedelta(0)
            for flight in self.flights:
                blocktime = datetime.datetime.strptime(flight["blocktime"], "%H:%M")
                delta = datetime.timedelta(hours=blocktime.hour, minutes=blocktime.minute)
                self.acc_blocktime += delta
        return self.acc_blocktime
    
    def get_blocktime_pic(self) -> datetime.timedelta: 
        if not self.acc_blocktime_pic:
            self.acc_blocktime_pic = datetime.timedelta(0)
            for flight in self.flights:
                if not self.is_pic(flight):
                    continue
                blocktime = datetime.datetime.strptime(flight["blocktime"], "%H:%M")
                delta = datetime.timedelta(hours=blocktime.hour, minutes=blocktime.minute)
                self.acc_blocktime_pic += delta
        return self.acc_blocktime_pic

    def get_airtime(self) -> datetime.timedelta:
        if not self.acc_airtime:
            self.acc_airtime = datetime.timedelta(0)
            for flight in self.flights:
                airtime = datetime.datetime.strptime(flight["airtime"], "%H:%M")
                delta = datetime.timedelta(hours=airtime.hour, minutes=airtime.minute)
                self.acc_airtime += delta
        return self.acc_airtime
    
    def get_landings(self) -> int:
        if not self.landings:
            self.landings = sum(int(l["landings"]) for l in self.flights)
        return self.landings
    
    def is_pic(self, flight: dict) -> bool:
        #TODO: respect tenant ID
        if flight["flightid"] in [
            "1668", 
            "3575", 
            "5269"
            ]:
            # blacklist flight id as non-PIC
            return False
        if flight["flightid"] in ["4853", "4854", "4855"]:
            # whitelist flight id as PIC
            return True
        
        # charter flights are always PIC
        if not "charter" in flight["pricecat"].lower():
            crew = flight["crew"]
            if "<b>Brenner</b>" in crew:
                return True
            if "Brenner" == crew:
                return True
            return False
        return True
    
    def remove_html_tags(text):
        return re.sub(r'<[^>]*>', '', text)
    
    def get_flights_groupedby_person(self):
        grouped = defaultdict(list)
        for flight in self.flights:     
            other = FlightLog.remove_html_tags(flight["crew"])
            other = re.sub(r'[0-9]+', '', other)
            other = other.split("/")
            other = [x for x in other if not "brenner" in x.lower()]
            other = [x.strip() for x in other]
            other = ", ".join(other)
            grouped[other].append(flight)   
        return grouped 
    
    def get_flights_groupedby_month(self, f_aircraft=None, f_pic=False):
        grouped = defaultdict(list)
        for flight in self.flights:
            if f_aircraft and not f_aircraft.lower() in flight["actype"].lower():
                continue
            
            if f_pic and not flight["pic"]:
                continue
            
            grouped[(flight["year"], flight["month"])].append(flight)
            
        # fill gaps (empty months)
        if len(grouped) <= 0:
            return (None, dict())
        
        all_months = pandas.date_range(start=self.min["date"].replace(day=1), end=self.max["date"], freq='MS').to_period('M')
        for month in all_months:
            len(grouped[month.year,month.month])
            
        return (all_months, dict(sorted(grouped.items())))
    
    def get_aircraft_types(self):
        aircraft = set()
        for flight in self.flights:
            aircraft.add(flight["actype"])
        return sorted(aircraft)
    
    def get_callsigns(self):
        aircraft = set()
        for flight in self.flights:
            aircraft.add(flight["callsign"])
        return sorted(aircraft)