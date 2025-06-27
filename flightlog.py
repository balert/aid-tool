import json, os, logging, datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()] 
)

logger = logging.getLogger(__name__)

class FlightLog():
    data = []
    
    def __init__(self, tenant):
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

    def get_blocktime(self):
        acc_time = datetime.timedelta(0)
        for flight in self.data:
            blocktime = datetime.datetime.strptime(flight["blocktime"], "%H:%M")
            delta = datetime.timedelta(hours=blocktime.hour, minutes=blocktime.minute)
            acc_time += delta
        return acc_time

    def get_airtime(self):
        acc_time = datetime.timedelta(0)
        for flight in self.data:
            airtime = datetime.datetime.strptime(flight["airtime"], "%H:%M")
            delta = datetime.timedelta(hours=airtime.hour, minutes=airtime.minute)
            acc_time += delta
        return acc_time
    
    def get_landings(self):
        return sum(int(l["landings"]) for l in self.data)