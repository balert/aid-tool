#!/usr/bin/env python3
import logging, json
import datetime

from config import *
from aid import AID
from flightlog import FlightLog

logger = logging.getLogger(__name__)
logging.basicConfig(filename='aid.log', level=logging.DEBUG)

def refresh_data():
    for tenant in tenants:
        currentyear = datetime.datetime.now().year
        since = "%s-01-01" % (currentyear - 1)
        until = "%s-01-01" % (currentyear + 1)
        
        logger.debug("Refreshing %s from %s till %s" % (tenant['name'], since, until))
        
        aid = AID(tenant['name'],tenant['username'],tenant['password'])
        ret = aid.get_flightlog(since, until)

        flightlog = FlightLog(tenant['name'])
        flightlog.store(ret['data'])

def display_data(tenant=None):
    if tenant == None:
        tenant = "merged"
    flightlog = FlightLog(tenant)
    data = flightlog.get()

    for flight in data:
        ts = flight['flightdate']['sortval']
        date = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S') 
        t = flight['tenant'] if "tenant" in flight else tenant
        print("flight %s #%s: %s (%s) %s)" % (t, flight['flightid'], flight['actype'], flight['callsign'], date))

def merge_data():
    merged = FlightLog('merged')
    for tenant in tenants:
        flightlog = FlightLog(tenant['name'])
        data = flightlog.get()
        for flight in data:
            flight['tenant'] = tenant['name']
        merged.store(data)
    merged.sort()

# refresh_data()
# merge_data()
display_data()