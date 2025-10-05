# Tado Automate Web - A free automation chain for open window detection
# Copyright (C) 2025 Martin Zettwitz
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>

import os
import sys
import time
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException, Query
from PyTado.interface import Tado

# -------------------------------------------------------------------
# Global Settings
# -------------------------------------------------------------------
TOKEN_FILE = "/tado_token/token"
LOG_FILE = "/l.log"
API_KEY = os.getenv("API_KEY", "supersecret")   # from Docker-ENV

retry_interval = 30

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)  # use FastAPI() in case you want to expose swagger docs
tado = None

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def log(message: str):
    """Log message into file + stdout"""
    timestamp = datetime.now().strftime('%d-%m-%Y %H:%M:%S')
    line = f"{timestamp} # {message}\n"
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line)
    except Exception:
        pass
    sys.stdout.write(line)
    sys.stdout.flush()

def check_auth(request: Request):
    """Easy token-auth via header"""
    if request.headers.get("X-API-KEY") != API_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")

def get_tado():
    """Get global Tado-client"""
    global tado

    if tado is None or tado.device_activation_status() != "COMPLETED":
        try:
            tado = Tado(token_file_path=TOKEN_FILE)
            status = tado.device_activation_status()
            
            TOKEN_FILE_EXISTS = os.path.isfile(TOKEN_FILE)

            if status == "PENDING":
                url = tado.device_verification_url()
                log(f"Visit this URL for authentication:")
                log(f'{url}')
                tado.device_activation()
                status = tado.device_activation_status()

            if status == "COMPLETED":
                if TOKEN_FILE_EXISTS:
                    log("Login successful.")
                else:
                    log("Login successful. Refresh token saved.")

            else:
                log(f"Login failed. Current status: {status}\nRetrying...")
                time.sleep(retry_interval)
                get_tado()

        except KeyboardInterrupt:
            log("Login interrupted by user.")
            sys.exit(0)

        except PermissionError as pe:
            log(f"Login permission error: {pe}")
            sys.exit(0)
        
        except Exception as ex:
                log(f"Connection error, retrying in {retry_interval} seconds... \n{ex}")
                time.sleep(retry_interval)
                get_tado()

    return tado

# -------------------------------------------------------------------
# Pytado logic
# -------------------------------------------------------------------
def heater_off_zone(zone_name: str):
    client = get_tado()
    zones = client.get_zones()
    found = False
    for z in zones:
        if z["name"].lower() == zone_name.lower():
            client.set_open_window(z["id"])
            log(f"{z['name']}: set to Open Window (heater off).")
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail=f"Zone '{zone_name}' not found")
    return {"status": "ok", "action": "heater_off", "zone": zone_name}

def heater_off_detected():
    client = get_tado()
    zones = client.get_zones()
    for z in zones:
        try:
            state = client.get_open_window_detected(z["id"])
            if state["openWindowDetected"]:
                client.set_open_window(z["id"])
                log(f"{z['name']}: detected open window, heater off.")
                return {"status": "ok", "action": "heater_off", "zone": z["name"]}
        except Exception as e:
            log(f"Error checking zone {z['name']}: {e}")
    raise HTTPException(status_code=404, detail="No zone with open window detected")

def heater_on_zone(zone_name: str):
    client = get_tado()
    zones = client.get_zones()
    found = False
    for z in zones:
        if z["name"].lower() == zone_name.lower():
            client.cancel_overlay(z["id"])
            log(f"{z['name']}: overlay cancelled (heater on).")
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail=f"Zone '{zone_name}' not found")
    return {"status": "ok", "action": "heater_on", "zone": zone_name}

# -------------------------------------------------------------------
# REST endpoints
# -------------------------------------------------------------------
@app.put("/heater/off")
def api_heater_off(request: Request, zone: str = Query(None, description="Optional: Zone-name")):
    """
    Heater off.
    - With ?zone=LivingRoom → turn off specific zone
    - Without zone → checks tado for 'openWindowDetected'
    """
    check_auth(request)
    if zone:
        return heater_off_zone(zone)
    else:
        return heater_off_detected()

@app.put("/heater/on")
def api_heater_on(request: Request, zone: str = Query(..., description="Zone-name necessary")):
    """Turn on heater in specific zone"""
    check_auth(request)
    return heater_on_zone(zone)

@app.get("/zones")
def api_list_zones(request: Request):
    """List all zones"""
    check_auth(request)
    client = get_tado()
    return [z["name"] for z in client.get_zones()]

@app.get("/health")
def api_health():
    return {"status": "running"}

@app.on_event("startup")
async def startup_event():
    """Login to Tado on startup"""
    import threading
    threading.Thread(target=get_tado).start()