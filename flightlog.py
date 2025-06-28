import json, os, logging, datetime
from collections import defaultdict
import pandas
import typing

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()] 
)

logger = logging.getLogger(__name__)

class FlightLog():
    data = []
    
    def __init__(self, tenant=None):
        if not tenant:
            tenant = "merged"
        self.filename = 'flightlog_%s.dat' % tenant
        if os.path.exists(self.filename):
            with open(self.filename, "r") as f:
                self.data = json.loads(f.read())
    
    def store(self, data):
        for flight in data:
            if flight['flightid'] == 0:
                # print("Skipping: ", flight)
                continue
            
            flightids = [f['flightid'] for f in self.data]
            if flight['flightid'] in flightids:
                # print("Skipping %s because already exists in data." % flight['flightid'])
                continue
            self.data.append(flight)
        self.write()
    
    def get_flight(self, flight_id: int):
        flight = next((f for f in self.data if int(f["flightid"]) == flight_id), None)
        return flight
    
    def get_all(self):
        return self.data
    
    def sort(self):
        self.data.sort(key=lambda x: x['flightdate']['sortval'])
        self.write()
        
    def write(self):
        with open(self.filename, "w") as f:
            f.write(json.dumps(self.data))

    def get_blocktime(self) -> datetime.timedelta: 
        acc_time = datetime.timedelta(0)
        for flight in self.data:
            blocktime = datetime.datetime.strptime(flight["blocktime"], "%H:%M")
            delta = datetime.timedelta(hours=blocktime.hour, minutes=blocktime.minute)
            acc_time += delta
        return acc_time

    def get_airtime(self) -> datetime.timedelta:
        acc_time = datetime.timedelta(0)
        for flight in self.data:
            airtime = datetime.datetime.strptime(flight["airtime"], "%H:%M")
            delta = datetime.timedelta(hours=airtime.hour, minutes=airtime.minute)
            acc_time += delta
        return acc_time
    
    def get_landings(self) -> int:
        return sum(int(l["landings"]) for l in self.data)
    
    def get_flights_groupedby_month(self, f_aircraft=None):
        grouped = defaultdict(list)
        for flight in self.data:
            if f_aircraft and not f_aircraft.lower() in flight["actype"].lower():
                continue
            flightdate = datetime.datetime.fromtimestamp(flight["flightdate"]["sortval"])
            grouped[(flightdate.year, flightdate.month)].append(flight)
            
        # fill gaps (empty months)
        if len(grouped) <= 0:
            return dict()
        
        (miny, minm) = min(grouped.keys())
        (maxy, maxm) = max(grouped.keys())
       
        start_date = pandas.to_datetime(f"{miny}-{minm}-01")
        end_date = pandas.to_datetime(f"{maxy}-{maxm}-01")

        all_months = pandas.date_range(start=start_date, end=end_date, freq='MS').to_period('M')
        for month in all_months:
            len(grouped[month.year,month.month])
            
        return dict(sorted(grouped.items()))
    
    def get_aircraft_types(self):
        aircraft = set()
        for flight in self.data:
            aircraft.add(flight["actype"])
        return aircraft
    