#!/usr/bin/env python3
import logging, re, json, os
import datetime
from fastapi import FastAPI, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
import matplotlib.pyplot as plt
import io

from config import *
from aid import AID
from flightlog import FlightLog
from notes import Notes

logger = logging.getLogger(__name__)
logging.basicConfig(filename='aid.log', level=logging.DEBUG)

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
        data = flightlog.get()
        for flight in data:
            flight['tenant'] = tenant['name']
            notes.insert(flight_notesId(flight))
        merged.store(data)
    merged.sort()
    notes.write()

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.get("/")
async def root(request: Request):
    flightlog = FlightLog("merged")
    data = flightlog.get()
    data.reverse()
    return templates.TemplateResponse(
        request=request, name="main.html", context={"data": data}
    )

@app.get("/flight/{flight_id}")
async def get_flight(request: Request, flight_id: int):
    return "flight %s " %flight_id

@app.get("/refresh")
async def root(request: Request):
    print("refresh")
    refresh_data()
    return RedirectResponse(url="/")

@app.get("/graph")
async def get_graph(request: Request):
    # Beispiel-Diagramm erstellen
    plt.figure()
    plt.plot([1, 2, 3, 4], [10, 20, 25, 30])
    plt.title("Testgraph")

    # Diagramm in BytesIO-Puffer schreiben
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    plt.close()  # Speicher freigeben
    buf.seek(0)  # Anfang des Puffers setzen

    # Antwort mit Bildinhalt zurückgeben
    return Response(content=buf.read(), media_type="image/png")