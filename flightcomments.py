import os , json

class FlightComments:
    def __init__(self):
        self.filename = 'comments.dat'
        if os.path.exists(self.filename):
            with open(self.filename, "r") as f:
                file_contents = f.read()
                if len(file_contents) > 0:
                    self.data = json.loads(file_contents)
                else: 
                    self.data = dict()
        else:
            self.data = dict()
    
    def set_comment(self, flightid: str, comment: str):
        self.data[flightid] = comment
    
    def get_comment(self, flightid: str) -> str:
        return self.data[flightid]
    
    def save(self):
        with open(self.filename, "w") as f:
            f.write(json.dumps(self.data))