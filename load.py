# -*- coding: utf-8 -*-
#
# Teletry: An EDMC Plugin to relay dashboard status and/or journal entries via MQTT
# 
# Written by Edward Wright (https://github.com/fasteddy516)
# Available at https://github.com/fasteddy516/EDMC-Telemetry
#
# Requires the Elite Dangerous Market Connector: https://github.com/Marginal/EDMarketConnector/wiki
# Uses the MQTT protocol (http://mqtt.org/) and Eclipse Paho MQTT Python Client (https://github.com/eclipse/paho.mqtt.python)

'''
- add ability to set topics for discrete pips (put it on the dashboard settings tab)
- add individual flag filtering and topic naming (requires its own settings notebook tab)
- journal processing - right now there is literally none

'''

import requests
import sys
import ttk
import Tkinter as tk
import myNotebook as nb
from config import config
from ttkHyperlinkLabel import HyperlinkLabel

import paho.mqtt.client as mqtt
import json

TELEMETRY_VERSION = "0.1.0"
TELEMETRY_CLIENTID = "EDMCTelemetryPlugin"

# default values for initial population of configuration
DEFAULT_BROKER_ADDRESS = "127.0.0.1"
DEFAULT_BROKER_PORT = 1883
DEFAULT_BROKER_KEEPALIVE = 60
DEFAULT_BROKER_QOS = 0
DEFAULT_ROOT_TOPIC = 'telemetry'

DEFAULT_DASHBOARD_FORMAT = 'raw'
DEFAULT_DASHBOARD_TOPIC = 'dashboard'
DEFAULT_DASHBOARD_FILTER_JSON = "{\"Flags\": [1, \"flags\"], \"Pips\": [0, \"pips\"], \"FireGroup\": [0, \"firegroup\"], \"GuiFocus\": [0, \"guifocus\"], \"Latitude\": [0, \"latitude\"], \"Longitude\": [0, \"longitude\"], \"Heading\": [0, \"heading\"], \"Altitude\": [0, \"altitude\"]}"

DEFAULT_FLAG_FORMAT = 'combined'
DEFAULT_FLAG_TOPIC = 'flag'
DEFAULT_FLAG_STATUS_TOPICS = ['Docked', 'Landed', 'LandingGear', 'Shields', 'Supercruise', 'FlightAssistOff', 'Hardpoints', 'InWing',
    'Lights', 'CargoScoop', 'SilentRunning', 'Scooping', 'SrvHandbrake', 'SrvTurret', 'SrcUnderShip', 'SrvDriveAssist',
    'FsdMassLocked', 'FsdCharging', 'FsdCooldown', 'LowFuel', 'OverHeating', 'HasLatLong', 'IsInDanger', 'BeingInterdicted',
    'InMainShip', 'InFighter', 'InSrv', 'Bit27', 'Bit28', 'Bit29', 'Bit30', 'Bit31']
DEFAULT_PIP_FORMAT = 'combined'
DEFAULT_PIP_TOPIC = 'pips'

DEFAULT_JOURNAL_FORMAT = 'raw'
DEFAULT_JOURNAL_TOPIC = 'journal'

this = sys.modules[__name__] # for holding globals

# Plugin startup
def plugin_start():
    loadConfiguration()
    initializeTelemetry()
    print "Telemetry: Started"
    return "Telemetry"

# Plugin shutdown
def plugin_stop():
    stopTelemetry()
    print "Telemetry: Stopped"

def plugin_app(parent):
    label = tk.Label(parent, text="Telemetry")
    this.status = tk.Label(parent, anchor=tk.W, text="Offline", state=tk.DISABLED)
    return (label, this.status)
    
# settings tab for plugin
def plugin_prefs(parent):
    
    # set up the primary frame for our assigned notebook tab
    frame = nb.Frame(parent) 
    frame.columnconfigure(1, weight=1)
    frame.rowconfigure(1, weight=1)

    # create a style that will be used for telemetry's settings notebook
    style = ttk.Style()
    style.configure('TNB.TNotebook', background=nb.Label().cget('background'))
    style.configure('TNB.TLabelFrame', background=nb.Label().cget('background'))
    PADX = 10
    PADY = 2

    # add our own notebook to hold all the telemetry options
    tnb = ttk.Notebook(frame, style='TNB.TNotebook')
    tnb.grid(columnspan=2, padx=8, sticky=tk.NSEW)
    tnb.columnconfigure(1, weight=1)
    
    # telemetry settings tab for mqtt options
    tnbMain = nb.Frame(tnb)
    tnbMain.columnconfigure(1, weight=1)
    nb.Label(tnbMain, text="Broker Address").grid(padx=PADX, row=1, sticky=tk.W)
    nb.Entry(tnbMain, textvariable=this.cfg_brokerAddress).grid(padx=PADX, pady=PADY, row=1, column=1, sticky=tk.EW)
    nb.Label(tnbMain, text="Port").grid(padx=PADX, row=2, sticky=tk.W)
    nb.Entry(tnbMain, textvariable=this.cfg_brokerPort).grid(padx=PADX, pady=PADY, row=2, column=1, sticky=tk.EW)
    nb.Label(tnbMain, text="Keepalive").grid(padx=PADX, row=3, sticky=tk.W)
    nb.Entry(tnbMain, textvariable=this.cfg_brokerKeepalive).grid(padx=PADX, pady=PADY, row=3, column=1, sticky=tk.EW)
    nb.Label(tnbMain, text='QoS').grid(padx=PADX, row=4, sticky=tk.W)
    nb.OptionMenu(tnbMain, this.cfg_brokerQoS, this.cfg_brokerQoS.get(), 0, 1, 2).grid(padx=PADX, pady=PADY, row=4, column=1, sticky=tk.W)
    nb.Label(tnbMain, text="Root Topic").grid(padx=PADX, row=5, sticky=tk.W)
    nb.Entry(tnbMain, textvariable=this.cfg_rootTopic).grid(padx=PADX, pady=PADY, row=5, column=1, sticky=tk.EW)    

    # telemetry settings tab for dashboard status items    
    tnbDashboard = nb.Frame(tnb) 
    tnbDashboard.columnconfigure(1, weight=1)
    nb.Label(tnbDashboard, text='Publish Format').grid(padx=PADX, row=1, column=0, sticky=tk.W)
    dbOptions = ['none', 'raw', 'processed']
    nb.OptionMenu(tnbDashboard, this.cfg_dashboardFormat, this.cfg_dashboardFormat.get(), *dbOptions, command=prefStateChange).grid(padx=PADX, row=1, column=1, sticky=tk.W)
    dbTopic_label = nb.Label(tnbDashboard, text='Topic')
    dbTopic_label.grid(padx=PADX, row=1, column=2, sticky=tk.W)
    dbTopic_entry = nb.Entry(tnbDashboard, textvariable=this.cfg_dashboardTopic)
    dbTopic_entry.grid(padx=PADX, row=1, column=3, sticky=tk.W)

    this.tnbDbStatus = tk.LabelFrame(tnbDashboard, text='Status', bg=nb.Label().cget('background'))
    tnbDbStatus.grid(padx=PADX, row=2, column=0, columnspan=4, sticky=tk.NSEW)
    tnbDbStatus.columnconfigure(1, weight=1)
    
    nb.Checkbutton(tnbDbStatus, text="Flags", variable=this.cfg_dashboardFilters['Flags'], command=prefStateChange).grid(padx=PADX, row=1, sticky=tk.W)
    nb.Entry(tnbDbStatus, textvariable=this.cfg_dashboardTopics['Flags']).grid(padx=PADX, row=1, column=1, sticky=tk.W)
    nb.Checkbutton(tnbDbStatus, text="GuiFocus", variable=this.cfg_dashboardFilters['GuiFocus'], command=prefStateChange).grid(padx=PADX, row=1, column=2, sticky=tk.W)
    nb.Entry(tnbDbStatus, textvariable=this.cfg_dashboardTopics['GuiFocus']).grid(padx=PADX, row=1, column=3, sticky=tk.W)

    nb.Label(tnbDbStatus, text="Flag Format").grid(padx=PADX, row=2, sticky=tk.W)
    nb.OptionMenu(tnbDbStatus, this.cfg_dashboardFlagFormat, this.cfg_dashboardFlagFormat.get(), 'combined', 'discrete').grid(padx=PADX, row=2, column=1, sticky=tk.W)
    nb.Checkbutton(tnbDbStatus, text="Latitude", variable=this.cfg_dashboardFilters['Latitude'], command=prefStateChange).grid(padx=PADX, row=2, column=2, sticky=tk.W)
    nb.Entry(tnbDbStatus, textvariable=this.cfg_dashboardTopics['Latitude']).grid(padx=PADX, row=2, column=3, sticky=tk.W)

    nb.Checkbutton(tnbDbStatus, text="Pips", variable=this.cfg_dashboardFilters['Pips'], command=prefStateChange).grid(padx=PADX, row=3, sticky=tk.W)
    nb.Entry(tnbDbStatus, textvariable=this.cfg_dashboardTopics['Pips']).grid(padx=PADX, row=3, column=1, sticky=tk.W)
    nb.Checkbutton(tnbDbStatus, text="Longitude", variable=this.cfg_dashboardFilters['Longitude'], command=prefStateChange).grid(padx=PADX, row=3, column=2, sticky=tk.W)
    nb.Entry(tnbDbStatus, textvariable=this.cfg_dashboardTopics['Longitude']).grid(padx=PADX, row=3, column=3, sticky=tk.W)

    nb.Label(tnbDbStatus, text="Pip Format").grid(padx=PADX, row=4, sticky=tk.W)
    nb.OptionMenu(tnbDbStatus, this.cfg_dashboardPipFormat, this.cfg_dashboardPipFormat.get(), 'combined', 'discrete').grid(padx=PADX, row=4, column=1, sticky=tk.W)
    nb.Checkbutton(tnbDbStatus, text="Heading", variable=this.cfg_dashboardFilters['Heading'], command=prefStateChange).grid(padx=PADX, row=4, column=2, sticky=tk.W)
    nb.Entry(tnbDbStatus, textvariable=this.cfg_dashboardTopics['Heading']).grid(padx=PADX, row=4, column=3, sticky=tk.W)
    
    nb.Checkbutton(tnbDbStatus, text="FireGroup", variable=this.cfg_dashboardFilters['FireGroup'], command=prefStateChange).grid(padx=PADX, row=5, sticky=tk.W)
    nb.Entry(tnbDbStatus, textvariable=this.cfg_dashboardTopics['FireGroup']).grid(padx=PADX, row=5, column=1, sticky=tk.W)
    nb.Checkbutton(tnbDbStatus, text="Altitude", variable=this.cfg_dashboardFilters['Altitude'], command=prefStateChange).grid(padx=PADX, row=5, column=2, sticky=tk.W)
    nb.Entry(tnbDbStatus, textvariable=this.cfg_dashboardTopics['Altitude']).grid(padx=PADX, row=5, column=3, sticky=tk.W)

    # telemetry settings tab for journal entry items    
    tnbJournal = nb.Frame(tnb)
    tnbJournal.columnconfigure(1, weight=1)
    nb.Label(tnbJournal, text="Journal-specific settings have not been implemented yet.").grid(sticky=tk.EW)
    
    # add the preferences tabs we've created to our assigned EDMC settings tab
    tnb.add(tnbMain, text = "MQTT")
    tnb.add(tnbDashboard, text = "Dashboard")
    tnb.add(tnbJournal, text = "Journal")
            
    # footer with github link and plugin version
    HyperlinkLabel(frame, text='https://github.com/fasteddy516/EDMC-Telemetry/', background=nb.Label().cget('background'), url='https://github.com/fasteddy516/EDMC-Telemetry/', underline=True).grid(padx=PADX, pady=(1,4), row=2, column=0, sticky=tk.W)
    nb.Label(frame, text="Plugin Version " + TELEMETRY_VERSION).grid(padx=PADX, pady=(1, 4), row=2, column=1, sticky=tk.E)

    prefStateChange()

    return frame



# Update enabled/disabled states of configuration elements
def prefStateChange(format='processed'):
    if format == 'raw':
        this.currentStatus = {}

    newState = (this.cfg_dashboardFormat.get() == 'processed') and tk.NORMAL or tk.DISABLED

    for element in this.tnbDbStatus.winfo_children():
        element['state'] = newState


def prefs_changed():
    # broker
    config.set("Telemetry-BrokerAddress", this.cfg_brokerAddress.get())
    config.set("Telemetry-BrokerPort", this.cfg_brokerPort.get())
    config.set("Telemetry-BrokerKeepalive", this.cfg_brokerKeepalive.get())
    config.set("Telemetry-BrokerQoS", this.cfg_brokerQoS.get())
    config.set("Telemetry-RootTopic", this.cfg_rootTopic.get())

    # dashboard    
    config.set("Telemetry-DashboardFormat", this.cfg_dashboardFormat.get())
    config.set("Telemetry-DashboardTopic", this.cfg_dashboardTopic.get())
    dfTemp = {}
    for key in this.cfg_dashboardFilters:
        dfTemp[key] = (this.cfg_dashboardFilters[key].get() and 1, this.cfg_dashboardTopics[key].get())
    config.set("Telemetry-DashboardFilterJSON", json.dumps(dfTemp))    
    
    # dashboard - status flags
    config.set("Telemetry-DashboardFlagFormat", this.cfg_dashboardFlagFormat.get())
    config.set("Telemetry-DashboardFlagTopic", this.cfg_dashboardFlagTopic.get())    
    
    # dashboard - pips
    config.set("Telemetry-DashboardPipFormat", this.cfg_dashboardPipFormat.get())
    config.set("Telemetry-DashboardPipTopic", this.cfg_dashboardPipTopic.get())

    stopTelemetry()
    startTelemetry()


def loadConfiguration():
    # broker
    this.cfg_brokerAddress = tk.StringVar(value=config.get("Telemetry-BrokerAddress"))
    if not cfg_brokerAddress.get():
        cfg_brokerAddress.set(DEFAULT_BROKER_ADDRESS)
    this.cfg_brokerPort = tk.IntVar(value=config.getint("Telemetry-BrokerPort"))
    if not cfg_brokerPort.get():
        cfg_brokerPort.set(DEFAULT_BROKER_PORT)
    this.cfg_brokerKeepalive = tk.IntVar(value=config.getint("Telemetry-BrokerKeepalive"))
    if not cfg_brokerKeepalive.get():
        cfg_brokerKeepalive.set(DEFAULT_BROKER_KEEPALIVE)
    this.cfg_brokerQoS = tk.IntVar(value=config.getint("Telemetry-BrokerQoS"))
    if cfg_brokerQoS.get() < 0 or cfg_brokerQoS.get() > 2:
        cfg_brokerQoS.set(DEFAULT_BROKER_QOS)
    this.cfg_rootTopic = tk.StringVar(value=config.get("Telemetry-RootTopic"))
    if not cfg_rootTopic.get():
        cfg_rootTopic.set(DEFAULT_ROOT_TOPIC)

    # dashboard
    this.cfg_dashboardFormat = tk.StringVar(value=config.get("Telemetry-DashboardFormat"))
    if not cfg_dashboardFormat.get():
        cfg_dashboardFormat.set(DEFAULT_DASHBOARD_FORMAT)
    this.cfg_dashboardTopic = tk.StringVar(value=config.get("Telemetry-DashboardTopic"))
    if not cfg_dashboardTopic.get():
        cfg_dashboardTopic.set(DEFAULT_DASHBOARD_TOPIC)
    this.cfg_dashboardFilters = {}
    this.cfg_dashboardTopics = {}
    jsonTemp = config.get("Telemetry-DashboardFilterJSON")
    if not jsonTemp:
        print "Using default dashboard filters json"
        dfTemp = json.loads(DEFAULT_DASHBOARD_FILTER_JSON)
    else:
        print "Using saved dashboard filters json"
        dfTemp = json.loads(jsonTemp)
    for key in dfTemp:
        this.cfg_dashboardFilters[key] = tk.IntVar(value=int(dfTemp[key][0]) and 1)
        this.cfg_dashboardTopics[key] = tk.StringVar(value=str(dfTemp[key][1]))
        print key + ": " + str(cfg_dashboardFilters[key].get()) + "," + cfg_dashboardTopics[key].get()
    
    # dashboard - status flags
    this.cfg_dashboardFlagFormat = tk.StringVar(value=config.get("Telemetry-DashboardFlagFormat"))
    if not cfg_dashboardFlagFormat.get():
        cfg_dashboardFlagFormat.set(DEFAULT_FLAG_FORMAT)
    this.cfg_dashboardFlagTopic = tk.StringVar(value=config.get("Telemetry-DashboardFlagTopic"))
    if not cfg_dashboardFlagTopic.get():
        cfg_dashboardFlagTopic.set(DEFAULT_FLAG_TOPIC)
    
    # dashboard - pips
    this.cfg_dashboardPipFormat = tk.StringVar(value=config.get("Telemetry-DashboardPipFormat"))
    if not cfg_dashboardPipFormat.get():
        cfg_dashboardPipFormat.set(DEFAULT_PIP_FORMAT)
    this.cfg_dashboardPipTopic = tk.StringVar(value=config.get("Telemetry-DashboardPipTopic"))
    if not cfg_dashboardPipTopic.get():
        cfg_dashboardPipTopic.set(DEFAULT_PIP_TOPIC)
    this.cfg_dashboardFilter = tk.StringVar(value=config.get("Telemetry-DashboardFilter"))

    # journal 
    this.cfg_journalTopic = tk.StringVar(value="journal")

def journal_entry(cmdr, system, station, entry):
    telemetry.publish(cfg_rootTopic.get() + "/" + cfg_journalTopic.get(), payload=json.dumps(entry), qos=0, retain=False)
    print "Telemetry: Journal Entry Received"

# dashboard status
def dashboard_entry(cmdr, is_beta, entry):

    dbTopic = cfg_rootTopic.get() + "/" + cfg_dashboardTopic.get()

    # if 'raw' dashboard status has been requested, publish the whole json string
    if this.cfg_dashboardFormat.get() == 'raw':
        telemetry.publish(dbTopic, payload=json.dumps(entry), qos=this.cfg_brokerQoS.get(), retain=False).wait_for_publish()
    
    # if 'processed' dashboard status has been requested, format with topics and filter as specified 
    elif this.cfg_dashboardFormat.get() == 'processed':
        for key in entry:
            # always ignore these keys
            if key == 'timestamp' or key == 'event':
                continue
        
            # publish any updated data that has been requested via configuration options
            if this.cfg_dashboardFilters.has_key(key) and this.cfg_dashboardFilters[key].get() == 1 and (not this.currentStatus.has_key(key) or this.currentStatus[key] != entry[key]):
                myTopic = dbTopic + "/" + this.cfg_dashboardTopics[key].get()
                if key == 'Flags' and this.cfg_dashboardFlagFormat.get() == 'discrete':
                    if not this.currentStatus.has_key(key):
                        oldFlags = ~entry[key] & 0x07FFFFFF
                    else:
                        oldFlags = this.currentStatus[key]
                    newFlags = entry[key]
                    for bit in xrange(32):
                        mask = 1 << bit
                        if (oldFlags ^ newFlags) & mask:
                            telemetry.publish(myTopic + "/" + STATUS_FLAG[bit], payload=(newFlags & mask) and 1, qos=this.cfg_brokerQoS.get(), retain=False).wait_for_publish()        
                elif key == 'Pips' and this.cfg_dashboardPipFormat.get() == 'discrete':
                    telemetry.publish(myTopic + "/sys", payload=str(entry[key][0]), qos=this.cfg_brokerQoS.get(), retain=False).wait_for_publish()
                    telemetry.publish(myTopic + "/eng", payload=str(entry[key][1]), qos=this.cfg_brokerQoS.get(), retain=False).wait_for_publish()
                    telemetry.publish(myTopic + "/wep", payload=str(entry[key][2]), qos=this.cfg_brokerQoS.get(), retain=False).wait_for_publish()                    
                else:                
                    telemetry.publish(myTopic, payload=str(entry[key]), qos=this.cfg_brokerQoS.get(), retain=False).wait_for_publish()
                this.currentStatus[key] = entry[key] 


def telemetryCallback_on_connect(client, userdata, flags, rc):
    this.status['text'] = 'Connected'
    this.status['state'] = tk.NORMAL
    print("Connected with result code "+str(rc))

def telemetryCallback_on_disconnect(client, userdata, rc):
    this.status['text'] = 'Offline'
    this.status['state'] = tk.DISABLED
    print("Disconnected with result code "+str(rc))

def telemetryCallback_on_message(client, userdata, msg):
    print(msg.topic+" "+str(msg.payload))

def telemetryCallback_on_publish(client, userdata, mid):
    print("> Published Message ID "+str(mid))

def initializeTelemetry():
    this.currentStatus = {}
    #this.currentStatus['Flags'] = 0
    this.telemetry = mqtt.Client(TELEMETRY_CLIENTID)
    telemetry.on_connect = telemetryCallback_on_connect
    telemetry.on_disconnect = telemetryCallback_on_disconnect
    telemetry.on_message = telemetryCallback_on_message
    telemetry.on_publish = telemetryCallback_on_publish
    startTelemetry()

def startTelemetry():
    telemetry.connect_async(this.cfg_brokerAddress.get(), this.cfg_brokerPort.get(), this.cfg_brokerKeepalive.get())
    telemetry.loop_start()

def stopTelemetry():
    telemetry.disconnect()
    telemetry.loop_stop()