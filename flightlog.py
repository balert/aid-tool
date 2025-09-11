import json, os, logging, datetime
from dateutil.relativedelta import relativedelta
from collections import defaultdict
import pandas
import re

from flight import Flight
from metadata import Metadata

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

    def virtual(tenants):
        flightlog = FlightLog()
        for t in tenants:
            tenant = FlightLog.file(t["name"])
            for flight in tenant.get_all():
                if not any(flight.getID() == f.getID() for f in flightlog.flights):
                    flightlog.flights.append(flight)
                flightlog.flights.sort(key=lambda x: x.sortval, reverse=True)
                flightlog.min = min(flightlog.flights, key=lambda x: x.sortval)
                flightlog.max = max(flightlog.flights, key=lambda x: x.sortval)
        return flightlog 
    
    def file(tenant: str):
        flightlog = FlightLog()
        flightlog.tenant = tenant
        flightlog.load_tenant()
        return flightlog
    
    def __str__(self):
        tenant = self.tenant["name"] if "name" in self.tenant else "n/a"
        base = f"File <{tenant}>" if self.tenant else "Virtual"
        noflights = len(self.flights)
        return f"Flightlog {base}, {noflights} flights."
    
    def cut(self, flight_id: str):
        sortval = self.get_flight(flight_id).sortval
        self.flights = [f for f in self.flights if f.sortval <= sortval]
    
    def load_tenant(self):
        self.filename = 'data/flightlog_%s.dat' % self.tenant
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
            self.flights.append(Flight(self.tenant, flight))
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
        if not os.path.exists("data/"):
            os.mkdir("data")
        with open(self.filename, "w") as f:
            f.write(json.dumps(self.data, cls=DateTimeEncoder))
    
    def get_flight(self, flight_id: str):
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
    
    def get_blocktime_dual(self) -> datetime.timedelta:
        return self.get_blocktime() - self.get_blocktime_pic()
    
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
        
        # fill gaps -> defaultdict
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
    
    def get_airports(self):
        airports = dict()
        for flight in self.flights:
            if not flight.departure in airports:
                airports[flight.departure] = 0
            airports[flight.departure] += 1
            
            if not flight.departure == flight.destination:
                if not flight.destination in airports:
                    airports[flight.destination] = 0
                airports[flight.destination] += 1
        return airports
            