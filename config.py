import json
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()] 
)

logger = logging.getLogger(__name__)

class Config(object):
    _instance = None 
    
    def __init__(self):
        raise RuntimeError('Call instance() instead')
    
    @classmethod 
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls.__new__(cls)
            cls._instance.init()
        return cls._instance
    
    def init(self):
        with open('config.json', 'r') as file:
            raw = file.read()
            self.config = json.loads(raw)
            
    def getTenants(self) -> list:
        return self.config["tenants"]
    
    def get(self, key: str):
        if not key in self.config:
            return None
        return self.config[key]