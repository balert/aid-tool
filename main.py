#!/usr/bin/env python3
import logging, re, json, os
import datetime
import math
from fastapi import FastAPI, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import io
from collections import defaultdict
import pandas
from typing import Optional, Union

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

# plt.style.use('Solarize_Light2')
plt.style.use('fast')

def refresh_data():
    for tenant in tenants:
        currentyear = datetime.datetime.now().year
        since = "%s-01-01" % (currentyear - 3)
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
    stat["blocktime_pic"] = timedelta_toString(flightlog.get_blocktime_pic())
    stat["blocktime_dual"] = timedelta_toString(flightlog.get_blocktime() - flightlog.get_blocktime_pic())
    stat["airtime"] = timedelta_toString(flightlog.get_airtime())
    stat["landings"] = f"{flightlog.get_landings()}"
    stat["aircraft"] = ", ".join(flightlog.get_aircraft_types())
    
    # average blocktime
    _, grouped = flightlog.get_flights_groupedby_month()
    blocktimes = defaultdict(datetime.timedelta)
    for k,v in grouped.items():
        time = datetime.timedelta(0)
        for flight in v:
            blocktime = datetime.datetime.strptime(flight["blocktime"], "%H:%M")
            delta = datetime.timedelta(hours=blocktime.hour, minutes=blocktime.minute)
            time += delta
        blocktimes[k] = time
    if len(blocktimes) > 0:
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
    logger.info("refreshing data...")
    refresh_data()
    return RedirectResponse(url="/")

def graph_bar(keys : list, values : dict, title : str = None, xlabel : str = None, ylabel : str = None, stacked : bool = True, barwidth : float = 0.9, legend : bool = True) -> Response:
    fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
    
    if stacked:
        bottom = [0] * len(next(iter(values.values())))
        for x, v in values.items():
            ax.bar(keys, v, width=barwidth, label=x, bottom=bottom)
            bottom = [a + b for a, b in zip(bottom, v)]
    else:
        barwidth = barwidth / len(values)
        width = len(values) * barwidth
        c = 1
        for x, v in values.items():
            k = list(range(len(v)))
            ax.bar([x-width/2+c*barwidth-barwidth/2 for x in k], v, width=barwidth, label=x)
            c+=1
        
    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)
    if title: 
        ax.set_title(title)
        
    logger.info(ax.get_ylim())
    ax.set_ylim(top=math.ceil(max(ax.get_ylim())/0.8))
    
    ax.set_xticks(list(range(len(keys))))
    ax.set_xticklabels(keys, rotation=90)
    if legend:
        fig.legend()

    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    buf.seek(0) 

    return Response(content=buf.read(), media_type="image/png")

@app.get("/graph/blocktimes")
async def get_graph_blocktimes(request: Request, aircraft : str = None):
    flightlog = FlightLog()
    (_, grouped) = flightlog.get_flights_groupedby_month(aircraft)
    
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
  
    return graph_bar(dates, {"values": values}, title="Blocktimes", xlabel="Date", ylabel="Blocktime [h]", legend=False)

@app.get("/graph/other")
async def get_graph_other(request: Request, stacked : bool = True):
    flightlog = FlightLog()
    grouped = flightlog.get_flights_groupedby_person()

    blocktimes = defaultdict()
    for person, data in grouped.items():
        time = datetime.timedelta(0)
        for flight in data:
            blocktime = datetime.datetime.strptime(flight["blocktime"], "%H:%M")
            delta = datetime.timedelta(hours=blocktime.hour, minutes=blocktime.minute)
            time += delta
        person = "Nicht-FFG" if len(person) <= 0 else person
        blocktimes[person] = time
        
    blocktimes = dict(sorted(blocktimes.items(), key=lambda item: item[1].total_seconds(), reverse=True))
            
    persons = blocktimes.keys()
    values = [x.total_seconds()/3600 for x in blocktimes.values()]
    
    return graph_bar(persons, {"a": values}, xlabel="Crew", ylabel="Blocktime [hours]", stacked=stacked, title="FFG Mitflieger / Lehrer", legend=False)

@app.get("/graph/bt_ac")
async def get_graph_blocktimes(request: Request, pic: Optional[bool] = None):
    flightlog = FlightLog()
    aircrafts = flightlog.get_aircraft_types()
    (all_months, grouped) = flightlog.get_flights_groupedby_month(f_pic=pic)
    
    data = dict()
    for ac in sorted(aircrafts): 
        data[ac] = list()
        for month in all_months:
            time = datetime.timedelta(0)
            for flight in grouped[month.year,month.month]:
                if flight["actype"] == ac:
                    blocktime = datetime.datetime.strptime(flight["blocktime"], "%H:%M")
                    delta = datetime.timedelta(hours=blocktime.hour, minutes=blocktime.minute)
                    time += delta
            data[ac].append(time.total_seconds()/3600)
    
    all_months = [f"{month.year}-{month.month:02d}" for month in all_months]
    title = "Blocktimes by Aircraft" if not pic else "Blocktimes by Aircraft (PIC)"
    return graph_bar(all_months, data, title=title, xlabel="Date", ylabel="Blocktime [h]")

@app.get("/graph/bt_cs")
async def get_graph_blocktimes(request: Request, pic: Optional[bool] = None):
    flightlog = FlightLog()
    aircrafts = flightlog.get_callsigns()
    (all_months, grouped) = flightlog.get_flights_groupedby_month(f_pic=pic)
    
    data = dict()
    for ac in sorted(aircrafts): 
        data[ac] = list()
        for month in all_months:
            time = datetime.timedelta(0)
            for flight in grouped[month.year,month.month]:
                if flight["callsign"] == ac:
                    blocktime = datetime.datetime.strptime(flight["blocktime"], "%H:%M")
                    delta = datetime.timedelta(hours=blocktime.hour, minutes=blocktime.minute)
                    time += delta
            data[ac].append(time.total_seconds()/3600)
    
    all_months = [f"{month.year}-{month.month:02d}" for month in all_months]
    return graph_bar(all_months, data, title="Blocktimes by Callsign", xlabel="Date", ylabel="Blocktime [h]")