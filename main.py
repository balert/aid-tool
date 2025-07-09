#!/usr/bin/env python3
import logging, re, json, os
import datetime
from fastapi import FastAPI, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import io
from collections import defaultdict
import pandas
from typing import Optional

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

@app.get("/graph/other")
async def get_graph_blocktimes(request: Request):
    flightlog = FlightLog()
    grouped = flightlog.get_flights_groupedby_person()

    blocktimes = defaultdict()
    for person, data in grouped.items():
        time = datetime.timedelta(0)
        for flight in data:
            blocktime = datetime.datetime.strptime(flight["blocktime"], "%H:%M")
            delta = datetime.timedelta(hours=blocktime.hour, minutes=blocktime.minute)
            time += delta
        blocktimes[person] = time
        
    blocktimes = dict(sorted(blocktimes.items(), key=lambda item: item[1].total_seconds(), reverse=True))
            
    persons = blocktimes.keys()
    values = [x.total_seconds()/3600 for x in blocktimes.values()]
    
    persons = ["Alone" if len(x) <= 0 else x for x in persons]
    
    for p, v in zip(persons, values):
        logger.info(f"{p}: {v}")
        
    # generate graph
    fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
    
    ax.bar(persons, values)
        
    plt.xticks(rotation=45)
    plt.title("Blocktime by person")
    plt.legend()

    # write graph to buffer and return 
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    plt.close() 
    buf.seek(0) 

    return Response(content=buf.read(), media_type="image/png")

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
    
    # generate graph
    fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
    
    bottom = [0] * len(data[list(aircrafts)[0]])
    for x, aircraft in enumerate(aircrafts):
        ax.bar([f"{x.year}-{x.month}" for x in all_months], data[aircraft], bottom=bottom, label=aircraft)
        bottom = [a + b for a, b in zip(bottom, data[aircraft])]
        
    plt.xticks(rotation=45)
    plt.ylim(0,10)
    if not pic:
        plt.title("Blocktimes by Aircraft Type")
    else: 
        plt.title("Blocktimes by Aircraft Type (PIC)")
    plt.legend()

    # write graph to buffer and return 
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    plt.close() 
    buf.seek(0) 

    return Response(content=buf.read(), media_type="image/png")

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
    
    # generate graph
    fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
    
    bottom = [0] * len(data[list(aircrafts)[0]])
    xaxis = pandas.Categorical([f"{x.year}-{x.month}" for x in all_months])
    xaxis = [datetime.datetime.strptime(val, '%Y-%m') for val in xaxis]
    for x, aircraft in enumerate(aircrafts):
        ax.bar(xaxis, data[aircraft], width=15, bottom=bottom, label=aircraft)
        bottom = [a + b for a, b in zip(bottom, data[aircraft])]
      
    # Set x-tick every month
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))  # Format like "Jan 2023"

    fig.autofmt_xdate()  # Rotate and format nicely
    plt.show()
    # ax.set_xticklabels([x.month for x in xaxis])
        
    # # Add year labels: either as minor ticks, or custom annotation
    # count = 0
    # first = True
    # for date in xaxis:
    #     month = date.month
    #     year = date.year
    #     if month == "1" or first:  # Only show year on January
    #         first = False
    #         ax.text(count,-0, str(year), ha='center', va='top')    
    #     count += 1
    
    # plt.xticks(rotation=0)
    if not pic:
        plt.title("Blocktimes by Callsign")
    else: 
        plt.title("Blocktimes by Callsign (PIC)")
    plt.legend()

    # write graph to buffer and return 
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    plt.close() 
    buf.seek(0) 

    return Response(content=buf.read(), media_type="image/png")

@app.get("/graph/test")
async def get_graph_test(request: Request):
    # prepare data
    index = [0,1,2,3,4]
    monthlabels = ["Okt", "Nov", "Dez", "Jan", "Feb"]
    yearlabels = {0: "2022", 3: "2023"}
    data = {
        "A210": [2,5,8,3,5],
        "P208": [6,3,9,1,2],
        "DA40": [2,0,9,4,1],
        "SR20": [3,5,6,7,4]
    }
    
    # graph
    fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
    barwidth=0.125
    
    stacked = False
    if stacked:
        bottom = [0] * len(next(iter(data.values())))
        for k,v in data.items():
            ax.bar(index, v, width=barwidth, label=k, bottom=bottom)
            bottom = [a + b for a, b in zip(bottom, v)]
    else:
        bars = len(data.keys())
        width = bars * barwidth
        c = 1
        for k,v in data.items():
            ax.bar([x-width/2+c*barwidth for x in index], v, width=barwidth, label=k)
            c+=1

    
    plt.xticks(ticks=index, labels=monthlabels, rotation=0)
    
    for k,v in yearlabels.items():
        ax.text(k, -0.1, v, ha='center', va='top', fontsize=10, transform=ax.get_xaxis_transform())
    
    plt.legend()
    
    # output 
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    plt.close() 
    buf.seek(0) 
    return Response(content=buf.read(), media_type="image/png")