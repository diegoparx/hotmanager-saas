import uvicorn
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse # <-- Nuevo
from pydantic import BaseModel
import logging
import json
import os
from datetime import datetime

# --- CONFIGURACIÓN & LOGS ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("HotmartSaaS")

app = FastAPI(title="HotManager SaaS")

# --- PERMISOS (CORS) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- BASE DE DATOS SIMPLE (JSON) ---
DB_FILE = "database.json"

def save_to_db(data: dict):
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            try:
                db_data = json.load(f)
            except:
                db_data = []
    else:
        db_data = []

    data["id"] = int(datetime.now().timestamp() * 1000)
    data["saved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db_data.insert(0, data)

    with open(DB_FILE, "w") as f:
        json.dump(db_data, f, indent=4)
    
    logger.info(f"💾 Guardado: {data.get('name', 'Desconocido')}")

# --- LOGICA DE PROCESAMIENTO ---
def process_hotmart_event(data: dict):
    event_type = data.get("event")
    
    if event_type in ["PURCHASE_APPROVED", "PURCHASE_COMPLETE", "APPROVED"]:
        logger.info(f"💰 VENTA: {data.get('name_client')}")
        save_to_db({
            "type": "SALE",
            "name": data.get("name_client", "Cliente Hotmart"),
            "email": data.get("email_client", "email@test.com"),
            "product": data.get("prod_name", "Producto"),
            "price": data.get("value", 0.0),
            "phone": data.get("phone_number", None), # Ahora guardamos el telefono si viene
            "status": "approved"
        })

    elif event_type == "CART_ABANDONMENT":
        logger.warning(f"🛒 ABANDONO: {data.get('name_client')}")
        save_to_db({
            "type": "ABANDONMENT",
            "name": data.get("name_client", "Visitante"),
            "email": data.get("email_client", "email@test.com"),
            "product": data.get("prod_name", "Producto"),
            "phone": data.get("phone_number", None),
            "status": "abandoned"
        })

# --- RUTAS (ENDPOINTS) ---

# 1. RUTA PRINCIPAL: Muestra el Dashboard
@app.get("/", response_class=HTMLResponse)
def read_root():
    # Leemos el archivo dashboard.html y lo devolvemos al navegador
    if os.path.exists("dashboard.html"):
        with open("dashboard.html", "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Error: No se encontró dashboard.html</h1>"

# 2. WEBHOOK: Hotmart nos envía datos
@app.post("/webhook/hotmart")
async def handle_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        payload = await request.json()
    except:
        form_data = await request.form()
        payload = dict(form_data)
        
    background_tasks.add_task(process_hotmart_event, payload)
    return {"status": "recibido"}

# 3. API: El Dashboard pide datos
@app.get("/api/leads")
def get_leads():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            try:
                return json.load(f)
            except:
                return []
    return []

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)