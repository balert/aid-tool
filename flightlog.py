import json, os

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
                print("Skipping %s because already exists in data." % flight['flightid'])
                continue
            self.data.append(flight)
        self.write()
    
    def get(self):
        return self.data
    
    def sort(self):
        self.data.sort(key=lambda x: x['flightdate']['sortval'])
        self.write()
        
    def write(self):
        with open(self.filename, "w") as f:
            f.write(json.dumps(self.data))
