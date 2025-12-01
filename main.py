import uvicorn
import os
from datetime import datetime
from typing import Optional, List
import logging

from fastapi import FastAPI, Request, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# --- IMPORTACIONES DE BASE DE DATOS PRO ---
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# --- CONFIGURACIÓN & LOGS ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("HotManager")

app = FastAPI(title="HotManager SaaS")

# --- PERMISOS (CORS) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CONFIGURACIÓN DE CONEXIÓN A LA NUBE ---
# Render nos pasará la URL de la base de datos por una "Variable de Entorno"
DATABASE_URL = os.environ.get("DATABASE_URL")

# Si estamos probando en local y no hay URL configurada, usamos un archivo local temporal
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./prueba_local.db"
    logger.warning("⚠️ Usando base de datos LOCAL (SQLite). Configura DATABASE_URL en Render.")
else:
    # Pequeño ajuste porque Render da la URL con 'postgres://' y Python quiere 'postgresql://'
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Creamos el motor de la base de datos
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- DEFINICIÓN DE LA TABLA (EL MOLDE) ---
class LeadDB(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String)  # SALE, ABANDONMENT
    name = Column(String)
    email = Column(String)
    product = Column(String)
    price = Column(Float)
    phone = Column(String, nullable=True)
    status = Column(String)
    saved_at = Column(DateTime, default=datetime.utcnow)

# Crear las tablas automáticamente si no existen
Base.metadata.create_all(bind=engine)

# Dependencia para conectar y desconectar en cada petición
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- LÓGICA DE PROCESAMIENTO ---
def procesar_evento_hotmart(data: dict):
    """Esta función corre en segundo plano y guarda en la BD"""
    db = SessionLocal() # Abrimos conexión propia
    try:
        event_type = data.get("event")
        
        # Preparamos el nuevo registro
        new_lead = LeadDB(
            name=data.get("name_client", "Desconocido"),
            email=data.get("email_client", "no-email"),
            product=data.get("prod_name", "Producto"),
            phone=data.get("phone_number", None),
            saved_at=datetime.utcnow()
        )

        if event_type in ["PURCHASE_APPROVED", "PURCHASE_COMPLETE", "APPROVED"]:
            logger.info(f"💰 GUARDANDO VENTA: {new_lead.name}")
            new_lead.type = "SALE"
            new_lead.status = "approved"
            new_lead.price = float(data.get("value", 0.0))
            
            db.add(new_lead)
            db.commit()

        elif event_type == "CART_ABANDONMENT":
            logger.warning(f"🛒 GUARDANDO ABANDONO: {new_lead.name}")
            new_lead.type = "ABANDONMENT"
            new_lead.status = "abandoned"
            new_lead.price = 0.0
            
            db.add(new_lead)
            db.commit()
            
    except Exception as e:
        logger.error(f"Error guardando en BD: {e}")
    finally:
        db.close() # Cerramos conexión siempre

# --- RUTAS ---

@app.get("/", response_class=HTMLResponse)
def read_root():
    if os.path.exists("dashboard.html"):
        with open("dashboard.html", "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>HotManager SaaS Activo 🚀</h1>"

@app.post("/webhook/hotmart")
async def handle_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        payload = await request.json()
    except:
        form_data = await request.form()
        payload = dict(form_data)
    
    # Enviamos la tarea al fondo para responder rápido a Hotmart
    background_tasks.add_task(procesar_evento_hotmart, payload)
    
    return {"status": "recibido", "message": "Procesando en segundo plano"}

@app.get("/api/leads")
def get_leads(db: Session = Depends(get_db)):
    # Traemos los últimos 100 registros, el más nuevo primero
    leads = db.query(LeadDB).order_by(LeadDB.saved_at.desc()).limit(100).all()
    return leads

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
