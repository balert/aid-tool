#!/usr/bin/env python3
import logging, re, json, os
import datetime
from dateutil.relativedelta import relativedelta
import math
from fastapi import FastAPI, Request, Response, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import io
from collections import defaultdict
import pandas
from typing import Optional, Union
from pathlib import Path
import uvicorn

from config import *
from aid import AID
from flightlog import FlightLog, Metadata
from airports import Airports

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
        flightlog = FlightLog.file(tenant['name'])
        
        flights = flightlog.get_all()
        if len(flights) > 0:
            maxDate = max(flights, key=lambda x: x.sortval)
            maxDate = datetime.datetime.fromtimestamp(maxDate.sortval)
            
            since = maxDate.strftime("%d.%m.%Y")
        else: 
            since = "1950-01-01" 
        
        until = datetime.datetime.now().strftime("%d.%m.%Y")
        
        logger.info("Refreshing %s from %s till %s" % (tenant['name'], since, until))
        
        aid = AID(tenant['name'],tenant['username'],tenant['password'])
        ret = aid.get_flightlog(since, until)
        
        flightlog.store(ret['data'])

def flight_notesId(flight):
    date = datetime.datetime.fromtimestamp(flight.sortval, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S') 
    return "%s %10s #%s %s %s>>>%s" % (date, flight.tenant, flight.id, flight.callsign, flight.departure, flight.destination)

def flight_toString(flight, notes=""):
    date = datetime.datetime.fromtimestamp(flight.sortval, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S') 
    crew = re.sub(r'<[^>]+>', '', flight.crew)
    return "%s %s [%s>>>%s] (%s) [%10s #%s] %25s | %s" % (flight.callsign, date, flight.departure, flight.destination, flight.airtime, flight.tenant, flight.flightid, crew, notes.strip())
    
def timedelta_toString(delta : datetime.timedelta) -> str:
    total_minutes = int(delta.total_seconds() // 60)
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{hours:02d}:{minutes:02d}"

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/favicon.ico")
def favicon():
    return FileResponse("static/favicon.ico")

@app.get("/")
async def root(request: Request, edit: Optional[str] = None):
    flightlog = FlightLog.virtual(tenants)
    
    stat = {}
    stat["blocktime"] = timedelta_toString(flightlog.get_blocktime())
    stat["blocktime_pic"] = timedelta_toString(flightlog.get_blocktime_pic())
    stat["blocktime_dual"] = timedelta_toString(flightlog.get_blocktime() - flightlog.get_blocktime_pic())
    stat["blocktime_night"] = timedelta_toString(flightlog.get_blocktime_night())
    stat["airtime"] = timedelta_toString(flightlog.get_airtime())
    stat["landings"] = flightlog.get_landings()
    stat["aircraft"] = ", ".join(flightlog.get_aircraft_types())
    stat["noflights"] = len(flightlog.get_all())
    
    now = datetime.datetime.now()
    if len(flightlog.flights) > 0:
        max_delta = relativedelta(now, flightlog.min.date)
        alltime = max_delta.years*12+max_delta.months+1
    else: 
        alltime = 1

    stat["avg_blocktimes"] = list()
    stat["avg_pictimes"] = list()
    stat["avg_dualtimes"] = list()
    stat["avg_nighttimes"] = list()
    
    for x in [alltime,12,6,3,1]:
        from_date = now - relativedelta(months=x)
        flights = flightlog.get_flights_by_date_period(from_date, now)
        time = datetime.timedelta(0)
        pictime = datetime.timedelta(0)
        dualtime = datetime.timedelta(0)
        nighttime = datetime.timedelta(0)
        for flight in flights:
            time += flight.getBlocktime()
            if flight.isPIC():
                pictime += flight.getBlocktime()
            if not flight.isPIC():
                dualtime += flight.getBlocktime()
            if flight.isNight():
                nighttime += flight.getBlocktime()
                
        average = f"{int(time.total_seconds()/x//3600)}:{int(time.total_seconds()/x%3600//60):02d}"
        picaverage = f"{int(pictime.total_seconds()/x//3600)}:{int(pictime.total_seconds()/x%3600//60):02d}"
        dualaverage = f"{int(dualtime.total_seconds()/x//3600)}:{int(dualtime.total_seconds()/x%3600//60):02d}"
        nightaverage = f"{int(nighttime.total_seconds()/x//3600)}:{int(nighttime.total_seconds()/x%3600//60):02d}"
        
        stat["avg_blocktimes"].append(average)
        stat["avg_pictimes"].append(picaverage)
        stat["avg_dualtimes"].append(dualaverage)
        stat["avg_nighttimes"].append(nightaverage)
    
    return templates.TemplateResponse(
        request=request, name="main.html", context={"flightlog": flightlog, "statistics": stat, "edit": edit, "airports": Airports.instance().airports, "home_airport": "Braunschweig Wolfsburg"}
    )
    
@app.post("/submit")
async def submit(request: Request, flightid: str = Form(), comment: str = Form(), pax: str = Form()):
    logger.info(f"{flightid}: {comment}")
    
    flightlog = FlightLog.virtual(tenants)
    Metadata.instance().add_metadata(flightid, "comment", comment)
    Metadata.instance().add_metadata(flightid, "pax", pax)
    
    return RedirectResponse(url="/", status_code=303)
    
@app.get("/flight/{flight_id}")
async def get_flight(request: Request, flight_id: str):
    flightlog = FlightLog.virtual(tenants)
    flight = flightlog.get_flight(flight_id)
    
    flightlog.cut(flight_id)
    
    blocktime = timedelta_toString(flightlog.get_blocktime())
    ldg = flightlog.get_landings()
    blocktime_night = timedelta_toString(flightlog.get_blocktime_night())
    blocktime_pic = timedelta_toString(flightlog.get_blocktime_pic())
    blocktime_dual = timedelta_toString(flightlog.get_blocktime_dual())
    
    logbook = f"Blockzeit: {blocktime} | Landungen: {ldg[0]} (Tag: {ldg[0]-ldg[2]} / Nacht: {ldg[2]}) | Nacht: {blocktime_night} | PIC: {blocktime_pic} | Dual: {blocktime_dual}"
    
    return templates.TemplateResponse(
        request=request, name="flight.html", context={"flight": flight, "logbook": logbook}
    )

@app.get("/refresh")
async def root(request: Request):
    logger.info("refreshing data...")
    refresh_data()
    for p in Path(".").glob("graph-*.png"):
        p.unlink()
    return RedirectResponse(url="/")

def graph_bar(keys : list, values : dict, title : str, xlabel : str = None, ylabel : str = None, stacked : bool = True, barwidth : float = 0.9, legend : bool = True, xdates : bool = False) -> Response:
    filename = f"graph-{title.replace(' ', '-').replace('/', '-').lower()}.png"
    
    if os.path.exists(filename):
        return FileResponse(filename)
    
    fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
    
    if xdates:
        keys = [datetime.datetime.strptime(date, '%Y-%m').date() for date in keys]
        plt.gca().xaxis.set_minor_formatter(mdates.DateFormatter('%b'))
        plt.gca().xaxis.set_minor_locator(mdates.MonthLocator())
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%b'))
        plt.gca().xaxis.set_major_locator(mdates.YearLocator())
        # plt.gcf().autofmt_xdate()
        barwidth = 25
    else: 
        ax.set_xticks(list(range(len(keys))))
        ax.set_xticklabels(keys, rotation=45)
    
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
        
    ax.set_ylim(top=math.ceil(max(ax.get_ylim())/0.8))

    if legend:
        # plt.xticks(rotation=90)
        plt.setp(ax.xaxis.get_minorticklabels(), rotation=90)
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=90)
        fig.legend(loc="upper left", bbox_to_anchor=(0.05, 0.95))

    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    buf.seek(0) 
    
    with open(filename, 'wb') as file:
        file.write(buf.getbuffer())

    return Response(content=buf.read(), media_type="image/png", headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"})

@app.get("/graph/blocktimes")
async def get_graph_blocktimes(request: Request, aircraft : str = None):
    flightlog = FlightLog.virtual(tenants)
    if len(flightlog.flights) <=0:
        return FileResponse('static/under-construction.png', headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"})
    (_, grouped) = flightlog.get_flights_groupedby_month(aircraft)
    
    # accumulate blocktimes
    blocktimes = defaultdict(datetime.timedelta)
    for k,v in grouped.items():
        time = datetime.timedelta(0)
        for flight in v:
            blocktime = datetime.datetime.strptime(flight.blocktime, "%H:%M")
            delta = datetime.timedelta(hours=blocktime.hour, minutes=blocktime.minute)
            time += delta
        blocktimes[k] = time
    
    # prepare keys and values
    dates = [f"{year}-{month:02d}" for (year, month) in blocktimes.keys()]
    values = [x.total_seconds()/3600 for x in blocktimes.values()]
  
    return graph_bar(dates, {"values": values}, title="Blocktimes", xlabel="Date", ylabel="Blocktime [h]", legend=False, xdates=True)

@app.get("/graph/other")
async def get_graph_other(request: Request, stacked : bool = True):
    flightlog = FlightLog.virtual(tenants)
    if len(flightlog.flights) <=0:
        return FileResponse('static/under-construction.png', headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"})
    grouped = flightlog.get_flights_groupedby_person()

    blocktimes = defaultdict()
    for person, data in grouped.items():
        time = datetime.timedelta(0)
        for flight in data:
            blocktime = datetime.datetime.strptime(flight.blocktime, "%H:%M")
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
    flightlog = FlightLog.virtual(tenants)
    if len(flightlog.flights) <=0:
        return FileResponse('static/under-construction.png', headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"})
    aircrafts = flightlog.get_aircraft_types()
    (all_months, grouped) = flightlog.get_flights_groupedby_month(f_pic=pic)
    
    data = dict()
    for ac in sorted(aircrafts): 
        data[ac] = list()
        for month in all_months:
            time = datetime.timedelta(0)
            for flight in grouped[month.year,month.month]:
                if flight.actype == ac:
                    blocktime = datetime.datetime.strptime(flight.blocktime, "%H:%M")
                    delta = datetime.timedelta(hours=blocktime.hour, minutes=blocktime.minute)
                    time += delta
            data[ac].append(time.total_seconds()/3600)
    
    all_months = [f"{month.year}-{month.month:02d}" for month in all_months]
    title = "Blocktimes by Aircraft" if not pic else "Blocktimes by Aircraft (PIC)"
    return graph_bar(all_months, data, title=title, xlabel="Date", ylabel="Blocktime [h]", xdates=True)

@app.get("/graph/bt_cs")
async def get_graph_blocktimes(request: Request, pic: Optional[bool] = None):
    flightlog = FlightLog.virtual(tenants)
    if len(flightlog.flights) <=0:
        return FileResponse('static/under-construction.png', headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"})
    aircrafts = flightlog.get_callsigns()
    (all_months, grouped) = flightlog.get_flights_groupedby_month(f_pic=pic)
    
    data = dict()
    for ac in sorted(aircrafts): 
        data[ac] = list()
        for month in all_months:
            time = datetime.timedelta(0)
            for flight in grouped[month.year,month.month]:
                if flight.callsign == ac:
                    blocktime = datetime.datetime.strptime(flight.blocktime, "%H:%M")
                    delta = datetime.timedelta(hours=blocktime.hour, minutes=blocktime.minute)
                    time += delta
            data[ac].append(time.total_seconds()/3600)
    
    all_months = [f"{month.year}-{month.month:02d}" for month in all_months]
    return graph_bar(all_months, data, title="Blocktimes by Callsign", xlabel="Date", ylabel="Blocktime [h]", xdates=True)

@app.get("/graph/airports")
async def get_graph_airports(request: Request):
    flightlog = FlightLog.virtual(tenants)
    if len(flightlog.flights) <=0:
        return FileResponse('static/under-construction.png', headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"})
    airports = flightlog.get_airports()
    airports = dict(sorted(airports.items(), key=lambda x: x[1], reverse=True))
    logger.info(airports)
    return graph_bar(airports.keys(),{"a": airports.values()},"Airports", legend=False)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)