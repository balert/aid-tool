import json
from collections import defaultdict
import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()] 
)

logger = logging.getLogger(__name__)

class Metadata(object):
    _instance = None 
    
    def __init__(self):
        raise RuntimeError('Call instance() instead')
    
    @classmethod 
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls.__new__(cls)
            cls._instance.load_metadata()   
        return cls._instance
    
    def load_metadata(self):
        self.metafilename = "data/metadata.dat"
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
        if not os.path.exists("data/"):
            os.mkdir("data")
            
        with open(self.metafilename, "w") as f:
            f.write(json.dumps(self.metadata))