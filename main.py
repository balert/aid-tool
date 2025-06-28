#!/usr/bin/env python3
import logging, re, json, os
import datetime
from fastapi import FastAPI, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
import matplotlib.pyplot as plt
import io
from collections import defaultdict
import pandas

from config import *
from aid import AID
from flightlog import FlightLog
from notes import Notes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()] 
)

logger = logging.getLogger(__name__)

notesfilename = "flightlog_merged_notes.dat"

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
    merge_data()

def flight_id(flight):
    return "%s%s" % (flight['tenant'], flight['flightid'])

def flight_notesId(flight):
    date = datetime.datetime.fromtimestamp(flight['flightdate']['sortval'], datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S') 
    return "%s %10s #%s %s %s>>>%s" % (date, flight['tenant'], flight['flightid'], flight['callsign'], flight['departure'], flight['destination'])

def flight_toString(flight, notes=""):
    date = datetime.datetime.fromtimestamp(flight['flightdate']['sortval'], datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S') 
    crew = re.sub(r'<[^>]+>', '', flight['crew'])
    return "%s %s [%s>>>%s] (%s) [%10s #%s] %25s | %s" % (flight['callsign'], date, flight['departure'], flight['destination'], flight['airtime'], flight['tenant'], flight['flightid'], crew, notes.strip())

def display_data(tenant=None):
    if tenant == None:
        tenant = "merged"

    notes = Notes(notesfilename)
    for flight in FlightLog(tenant).get():
        print(flight_toString(flight, notes.get(flight_notesId(flight))))

def merge_data():
    notes = Notes(notesfilename)
    merged = FlightLog('merged')
    for tenant in tenants:
        flightlog = FlightLog(tenant['name'])
        data = flightlog.get_all()
        for flight in data:
            flight['tenant'] = tenant['name']
            notes.insert(flight_notesId(flight))
        merged.store(data)
    merged.sort()
    notes.write()
    
def timedelta_toString(delta : datetime.timedelta) -> str:
    total_minutes = int(delta.total_seconds() // 60)
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{hours:02d}:{minutes:02d}"

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.get("/")
async def root(request: Request):
    flightlog = FlightLog()
    data = flightlog.get_all()
    data.reverse()

    stat = {}
    stat["blocktime"] = timedelta_toString(flightlog.get_blocktime())
    stat["airtime"] = timedelta_toString(flightlog.get_airtime())
    stat["landings"] = f"{flightlog.get_landings()}"
    stat["aircraft"] = ", ".join(flightlog.get_aircraft_types())
    
    grouped = flightlog.get_flights_groupedby_month()
    blocktimes = defaultdict(datetime.timedelta)
    for k,v in grouped.items():
        time = datetime.timedelta(0)
        for flight in v:
            blocktime = datetime.datetime.strptime(flight["blocktime"], "%H:%M")
            delta = datetime.timedelta(hours=blocktime.hour, minutes=blocktime.minute)
            time += delta
        blocktimes[k] = time
    stat["avg_blocktime_month"] = round(pandas.Series(blocktimes.values()).mean().total_seconds()/3600,1)
    
    return templates.TemplateResponse(
        request=request, name="main.html", context={"data": data, "statistics": stat}
    )

@app.get("/flight/{flight_id}")
async def get_flight(request: Request, flight_id: int):
    flightlog = FlightLog()
    flightdata = flightlog.get_flight(flight_id)
    for k,v in flightdata.items():
        logger.info(f"{k}: {v}")
    return templates.TemplateResponse(
        request=request, name="flight.html", context={"flight": flightdata}
    )

@app.get("/refresh")
async def root(request: Request):
    print("refresh")
    refresh_data()
    return RedirectResponse(url="/")

@app.get("/graph/blocktimes")
async def get_graph_blocktimes(request: Request, aircraft : str = None):
    flightlog = FlightLog()
    grouped = flightlog.get_flights_groupedby_month(aircraft)
    
    # accumulate blocktimes
    blocktimes = defaultdict(datetime.timedelta)
    for k,v in grouped.items():
        time = datetime.timedelta(0)
        for flight in v:
            blocktime = datetime.datetime.strptime(flight["blocktime"], "%H:%M")
            delta = datetime.timedelta(hours=blocktime.hour, minutes=blocktime.minute)
            time += delta
        blocktimes[k] = time
    
    # prepare keys and values
    dates = [f"{year}-{month:02d}" for (year, month) in blocktimes.keys()]
    values = [x.total_seconds()/3600 for x in blocktimes.values()]
  
    # generate graph
    fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
    ax.bar(dates, values)
    plt.xticks(rotation=90)
    plt.title(f"Blocktimes {aircraft}" if aircraft else "Blocktimes")
    plt.tight_layout(pad=2)

    # write graph to buffer and return 
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    plt.close() 
    buf.seek(0) 

    return Response(content=buf.read(), media_type="image/png")