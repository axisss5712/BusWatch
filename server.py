from datetime import datetime, date
import hashlib
import json
import math
import os
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean, Text, DateTime, ForeignKey, func, text
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
import uvicorn

# Automatically use XAMPP Unix Socket on Ubuntu if present, otherwise standard TCP
XAMPP_SOCKET = "/opt/lampp/var/mysql/mysql.sock"
if os.path.exists(XAMPP_SOCKET):
    SQLALCHEMY_DATABASE_URL = f"mysql+pymysql://root:@localhost/bus_db?unix_socket={XAMPP_SOCKET}"
else:
    SQLALCHEMY_DATABASE_URL = "mysql+pymysql://root:@127.0.0.1:3306/bus_db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

OFFICIAL_ROUTE = "Bongabon Terminal - Cabanatuan City Central Transport Terminal (via Palayan City)"

# Persistent file to store Inactive bus IDs without altering the MySQL ENUM column
INACTIVE_BUSES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inactive_buses.json")


def load_inactive_buses() -> set:
    if os.path.exists(INACTIVE_BUSES_FILE):
        try:
            with open(INACTIVE_BUSES_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_inactive_buses(bus_ids: set):
    try:
        with open(INACTIVE_BUSES_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(list(bus_ids)), f)
    except Exception:
        pass


INACTIVE_BUS_IDS = load_inactive_buses()

# ------------------ SQLAlchemy Models ------------------

class User(Base):
    __tablename__ = "users"
    user_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(120), nullable=False)
    role = Column(String(30), nullable=False, default="Passenger")  # Dispatcher, Conductor, Passenger
    contact_number = Column(String(30), nullable=True)
    license_number = Column(String(40), nullable=True)
    assigned_bus_id = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.now)


class BusStop(Base):
    __tablename__ = "bus_stops"
    stop_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    stop_name = Column(String(120), nullable=False)
    municipality = Column(String(80), nullable=False)
    route_name = Column(String(150), nullable=False, default=OFFICIAL_ROUTE)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    stop_order = Column(Integer, nullable=False)


class Bus(Base):
    __tablename__ = "buses"
    bus_id = Column(String(50), primary_key=True, index=True)
    plate_number = Column(String(30), nullable=False)
    operator_name = Column(String(150), nullable=False, default="Bongabon Primemovers TSC")
    driver_name = Column(String(100), nullable=False)
    conductor_name = Column(String(100), nullable=False)
    route_name = Column(String(150), nullable=False, default=OFFICIAL_ROUTE)
    lat = Column(Float, nullable=False, default=15.6284456)
    lng = Column(Float, nullable=False, default=121.1461240)
    current_passengers = Column(Integer, nullable=False, default=0)
    max_seated = Column(Integer, nullable=False, default=30)
    max_standing = Column(Integer, nullable=False, default=15)
    status = Column(String(50), nullable=False, default="Seats Available")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class Ticket(Base):
    __tablename__ = "tickets"
    ticket_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    bus_id = Column(String(50), ForeignKey("buses.bus_id", ondelete="CASCADE"), nullable=False, index=True)
    issued_by_user_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    origin_stop_id = Column(Integer, ForeignKey("bus_stops.stop_id"), nullable=False)
    destination_stop_id = Column(Integer, ForeignKey("bus_stops.stop_id"), nullable=False)
    distance_km = Column(Float, nullable=False)
    passenger_type = Column(String(30), nullable=False, default="Regular")
    passenger_count = Column(Integer, nullable=False, default=1)
    fare_amount = Column(Float, nullable=False)
    is_onboard = Column(Boolean, default=True)
    issued_at = Column(DateTime, default=datetime.now)
    alighted_at = Column(DateTime, nullable=True)


class PassengerLog(Base):
    __tablename__ = "passenger_logs"
    log_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    bus_id = Column(String(50), ForeignKey("buses.bus_id", ondelete="CASCADE"), nullable=False, index=True)
    event_source = Column(String(40), default="Dispatcher")
    passenger_delta = Column(Integer, nullable=False, default=0)
    current_passengers = Column(Integer, nullable=False)
    available_seats = Column(Integer, nullable=False)
    standing_count = Column(Integer, nullable=False)
    status = Column(String(50), nullable=False)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    logged_at = Column(DateTime, default=datetime.now)


class Feedback(Base):
    __tablename__ = "feedback"
    feedback_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    bus_id = Column(String(50), ForeignKey("buses.bus_id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    passenger_name = Column(String(100), nullable=False, default="Anonymous")
    category = Column(String(60), nullable=False, default="General Concern")
    message = Column(Text, nullable=False)
    status = Column(String(30), nullable=False, default="Pending")
    resolved_by_user_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.now)


# ------------------ Helper Functions ------------------

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def compute_capacity(current_pax: int, max_seated: int, max_standing: int):
    current_pax = max(0, current_pax)
    avail_seats = max(0, max_seated - current_pax)
    standing = max(0, current_pax - max_seated)
    if current_pax >= (max_seated + max_standing):
        status = "Full Capacity"
    elif current_pax >= max_seated:
        status = "Standing Only"
    else:
        status = "Seats Available"
    return avail_seats, standing, status


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    straight_km = r * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))
    # Road curvature factor so Bongabon -> Cabanatuan = 30.20 km
    return straight_km * 1.1625


def compute_fare(distance_km: float, passenger_type: str, passenger_count: int) -> float:
    # Base ₱15.00 for first 4 km + ₱2.5763 per succeeding km
    unit_fare = 15.0 + max(0.0, distance_km - 4.0) * 2.5763
    if passenger_type == "Discounted":
        unit_fare = round(unit_fare * 0.80)  # ₱66.00 for 30.2 km
    else:
        unit_fare = round(unit_fare)         # ₱83.00 (or round(unit_fare, 2) for ₱82.50)
    return round(unit_fare * max(1, passenger_count), 2)


def seed_initial_data():
    Base.metadata.create_all(bind=engine)

    # Ensure existing 'users' table has all required columns for Sign-Up
    user_alter_statements = [
        "ALTER TABLE users ADD COLUMN password_hash VARCHAR(255) NOT NULL DEFAULT ''",
        "ALTER TABLE users ADD COLUMN full_name VARCHAR(120) NOT NULL DEFAULT ''",
        "ALTER TABLE users ADD COLUMN role VARCHAR(30) NOT NULL DEFAULT 'Passenger'",
        "ALTER TABLE users ADD COLUMN contact_number VARCHAR(30) DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN license_number VARCHAR(40) DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN assigned_bus_id VARCHAR(50) DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    ]
    with engine.connect() as conn:
        for stmt in user_alter_statements:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass

    db = SessionLocal()
    try:
        if db.query(BusStop).count() == 0:
            stops = [
                BusStop(stop_name="Stop 1: Bongabon Terminal", municipality="Bongabon", lat=15.6284456, lng=121.1461240, stop_order=1),
                BusStop(stop_name="Stop 2: Lusok", municipality="Bongabon", lat=15.6012827, lng=121.1415366, stop_order=2),
                BusStop(stop_name="Stop 3: Provincial Government of Nueva Ecija", municipality="Palayan City", lat=15.5565427, lng=121.0925970, stop_order=3),
                BusStop(stop_name="Stop 4: Palayan City Plaza Concepcion", municipality="Palayan City", lat=15.5428881, lng=121.0850902, stop_order=4),
                BusStop(stop_name="Stop 5: Cabu", municipality="Cabanatuan City", lat=15.5192235, lng=121.0522477, stop_order=5),
                BusStop(stop_name="Stop 6: Cabanatuan City Central Transport Terminal", municipality="Cabanatuan City", lat=15.4724379, lng=120.9656717, stop_order=6),
            ]
            db.add_all(stops)
            db.commit()

        if db.query(Bus).count() == 0:
            buses = [
                Bus(bus_id="BUS-101", plate_number="NEA-1011", operator_name="Bongabon Primemovers TSC", driver_name="Mario Santos", conductor_name="Carlo Reyes", route_name=OFFICIAL_ROUTE, lat=15.6284456, lng=121.1461240, current_passengers=18, max_seated=30, max_standing=15, status="Seats Available"),
                Bus(bus_id="BUS-102", plate_number="NEA-2045", operator_name="Bongabon Primemovers TSC", driver_name="Ramon Bautista", conductor_name="Luis Gomez", route_name=OFFICIAL_ROUTE, lat=15.6012827, lng=121.1415366, current_passengers=32, max_seated=30, max_standing=15, status="Standing Only"),
                Bus(bus_id="BUS-103", plate_number="NEA-3089", operator_name="Bongabon Primemovers TSC", driver_name="Ernesto Cruz", conductor_name="Mark Villanueva", route_name=OFFICIAL_ROUTE, lat=15.5565427, lng=121.0925970, current_passengers=8, max_seated=30, max_standing=15, status="Seats Available"),
                Bus(bus_id="BUS-104", plate_number="NEA-4521", operator_name="Bongabon Primemovers TSC", driver_name="Roberto Morales", conductor_name="Roberto Morales", route_name=OFFICIAL_ROUTE, lat=15.5428881, lng=121.0850902, current_passengers=10, max_seated=30, max_standing=15, status="Seats Available"),
                Bus(bus_id="BUS-105", plate_number="NEA-6942", operator_name="Bongabon Primemovers TSC", driver_name="Edwardo Natividad", conductor_name="Alexander Rosario", route_name=OFFICIAL_ROUTE, lat=15.5192235, lng=121.0522477, current_passengers=29, max_seated=30, max_standing=15, status="Seats Available"),
            ]
            db.add_all(buses)
            db.commit()
    finally:
        db.close()


seed_initial_data()

# ------------------ FastAPI Setup ------------------

app = FastAPI(title="Bongabon Primemovers TSC - Unified API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def serialize_bus(b: Bus) -> dict:
    is_inactive = (b.bus_id in INACTIVE_BUS_IDS) or (b.status == "Inactive")
    avail, standing, computed_status = compute_capacity(b.current_passengers, b.max_seated, b.max_standing)
    final_status = "Inactive" if is_inactive else computed_status
    return {
        "bus_id": b.bus_id,
        "plate_number": b.plate_number,
        "operator_name": b.operator_name,
        "driver_name": b.driver_name,
        "conductor_name": b.conductor_name,
        "route_name": b.route_name,
        "lat": float(b.lat),
        "lng": float(b.lng),
        "current_passengers": 0 if is_inactive else b.current_passengers,
        "max_seated": b.max_seated,
        "max_standing": b.max_standing,
        "available_seats": 0 if is_inactive else avail,
        "standing_count": 0 if is_inactive else standing,
        "status": final_status,
        "updated_at": b.updated_at.isoformat() if b.updated_at else "",
    }


# ------------------ Request Schemas ------------------

class SignUpPayload(BaseModel):
    username: str
    password: str
    full_name: str
    role: str = "Passenger"  # Dispatcher, Conductor, Passenger
    contact_number: Optional[str] = ""
    license_number: Optional[str] = ""
    assigned_bus_id: Optional[str] = "BUS-101"


class LoginPayload(BaseModel):
    username: str
    password: str
    role: Optional[str] = None
    assigned_bus_id: Optional[str] = None


class BusUpdatePayload(BaseModel):
    bus_id: str
    route_name: str = OFFICIAL_ROUTE
    lat: float
    lng: float
    current_passengers: int
    max_seated: int = 30
    max_standing: int = 15
    event_source: str = "Dispatcher"


class BusRegisterPayload(BaseModel):
    bus_id: str
    plate_number: str
    operator_name: str = "Bongabon Primemovers TSC"
    driver_name: str
    conductor_name: str
    route_name: str = OFFICIAL_ROUTE
    lat: float = 15.6284456
    lng: float = 121.1461240
    max_seated: int = 30
    max_standing: int = 15


class TicketIssuePayload(BaseModel):
    bus_id: str
    issued_by_user_id: Optional[int] = None
    origin_stop_id: int
    destination_stop_id: int
    passenger_type: str = "Regular"  # Regular or Discounted
    passenger_count: int = 1


class DropOffPayload(BaseModel):
    bus_id: str
    destination_stop_id: int


class FeedbackPayload(BaseModel):
    bus_id: str
    user_id: Optional[int] = None
    passenger_name: str = "Anonymous"
    category: str = "General Concern"
    message: str


class BusStatusPayload(BaseModel):
    bus_id: str
    status: str  # "Active" or "Inactive"


# ------------------ 1. Authentication Endpoints ------------------

@app.post("/api/auth/signup")
def signup(payload: SignUpPayload, db: Session = Depends(get_db)):
    uname = payload.username.strip()
    if not uname or not payload.password:
        raise HTTPException(status_code=400, detail="Username and password are required.")
    if db.query(User).filter(User.username == uname).first():
        raise HTTPException(status_code=400, detail="Username already exists.")

    new_user = User(
        username=uname,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip() or uname,
        role=payload.role,
        contact_number=payload.contact_number,
        license_number=payload.license_number,
        assigned_bus_id=payload.assigned_bus_id if payload.role == "Conductor" else None,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {
        "user_id": new_user.user_id,
        "username": new_user.username,
        "full_name": new_user.full_name,
        "role": new_user.role,
        "assigned_bus_id": new_user.assigned_bus_id,
    }


@app.post("/api/auth/login")
def login(payload: LoginPayload, db: Session = Depends(get_db)):
    user = db.query(User).filter(
        User.username == payload.username.strip(),
        User.password_hash == hash_password(payload.password)
    ).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    if payload.role and user.role.lower() != payload.role.lower():
        raise HTTPException(status_code=403, detail=f"Account belongs to role '{user.role}', not '{payload.role}'.")

    if payload.assigned_bus_id and user.role == "Conductor":
        user.assigned_bus_id = payload.assigned_bus_id
        db.commit()

    return {
        "user_id": user.user_id,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
        "assigned_bus_id": user.assigned_bus_id or "BUS-101",
    }


# ------------------ 2. Stops & Fleet Endpoints ------------------

@app.get("/api/stops")
def get_bus_stops(db: Session = Depends(get_db)):
    """
    Returns all stops automatically sorted by geographic location
    from Bongabon (North-East) to Cabanatuan (South-West).
    """
    all_stops = db.query(BusStop).all()
    sorted_stops = sorted(
        all_stops,
        key=lambda s: (float(s.lat) + float(s.lng)),
        reverse=True,
    )
    return [
        {
            "stop_id": s.stop_id,
            "stop_name": s.stop_name,
            "municipality": s.municipality,
            "lat": float(s.lat),
            "lng": float(s.lng),
            "stop_order": idx,
        }
        for idx, s in enumerate(sorted_stops, start=1)
    ]


@app.delete("/api/stops/{stop_id}")
def delete_bus_stop(stop_id: int, db: Session = Depends(get_db)):
    stop = db.query(BusStop).filter(BusStop.stop_id == stop_id).first()
    if not stop:
        raise HTTPException(status_code=404, detail="Stop not found.")

    db.query(Ticket).filter(
        (Ticket.origin_stop_id == stop_id) | (Ticket.destination_stop_id == stop_id)
    ).delete(synchronize_session=False)

    removed_name = stop.stop_name
    db.delete(stop)
    db.commit()

    reorder_stops_safely(db)

    return {"message": f"Removed '{removed_name}' and updated route!"}


@app.get("/api/buses")
def get_buses(include_inactive: bool = False, db: Session = Depends(get_db)):
    buses = db.query(Bus).order_by(Bus.bus_id).all()
    if not include_inactive:
        buses = [b for b in buses if b.bus_id not in INACTIVE_BUS_IDS and b.status != "Inactive"]
    return [serialize_bus(b) for b in buses]


@app.post("/api/buses/status")
def update_bus_operational_status(payload: BusStatusPayload, db: Session = Depends(get_db)):
    bus = db.query(Bus).filter(Bus.bus_id == payload.bus_id).first()
    if not bus:
        raise HTTPException(status_code=404, detail="Bus not found")

    if payload.status.strip().lower() == "inactive":
        INACTIVE_BUS_IDS.add(bus.bus_id)
        save_inactive_buses(INACTIVE_BUS_IDS)

        # Keep MySQL ENUM column valid ("Seats Available") while clearing passengers and tickets
        bus.current_passengers = 0
        bus.status = "Seats Available"
        active_tickets = db.query(Ticket).filter(
            Ticket.bus_id == bus.bus_id,
            Ticket.is_onboard == True,
        ).all()
        for t in active_tickets:
            t.is_onboard = False
            t.alighted_at = datetime.now()
    else:
        INACTIVE_BUS_IDS.discard(bus.bus_id)
        save_inactive_buses(INACTIVE_BUS_IDS)
        _, _, bus.status = compute_capacity(bus.current_passengers, bus.max_seated, bus.max_standing)

    bus.updated_at = datetime.now()
    db.commit()
    db.refresh(bus)
    return {"message": f"Updated {bus.bus_id} to {payload.status}", "bus": serialize_bus(bus)}


@app.post("/api/buses/register")
def register_bus(payload: BusRegisterPayload, db: Session = Depends(get_db)):
    bus = db.query(Bus).filter(Bus.bus_id == payload.bus_id).first()
    if not bus:
        bus = Bus(
            bus_id=payload.bus_id.strip(),
            current_passengers=0,
            lat=payload.lat,
            lng=payload.lng,
        )
        db.add(bus)

    bus.plate_number = payload.plate_number.strip()
    bus.operator_name = payload.operator_name.strip()
    bus.driver_name = payload.driver_name.strip()
    bus.conductor_name = payload.conductor_name.strip()
    bus.route_name = payload.route_name.strip()
    bus.max_seated = payload.max_seated
    bus.max_standing = payload.max_standing
    _, _, bus.status = compute_capacity(bus.current_passengers, bus.max_seated, bus.max_standing)
    bus.updated_at = datetime.now()

    db.commit()
    db.refresh(bus)
    return {"message": f"Saved {bus.bus_id}", "bus": serialize_bus(bus)}


@app.post("/api/buses/update")
def update_bus(payload: BusUpdatePayload, db: Session = Depends(get_db)):
    bus = db.query(Bus).filter(Bus.bus_id == payload.bus_id).first()
    if not bus:
        raise HTTPException(status_code=404, detail="Bus not found")

    # Ignore background GPS simulator / conductor pings if the bus is marked Inactive
    if bus.bus_id in INACTIVE_BUS_IDS:
        if payload.event_source == "Terminal Dispatch":
            INACTIVE_BUS_IDS.discard(bus.bus_id)
            save_inactive_buses(INACTIVE_BUS_IDS)
        else:
            return {"bus": serialize_bus(bus), "passenger_delta": 0}

    prev_pax = bus.current_passengers
    bus.route_name = payload.route_name
    bus.lat = payload.lat
    bus.lng = payload.lng
    bus.current_passengers = max(0, payload.current_passengers)
    bus.max_seated = payload.max_seated
    bus.max_standing = payload.max_standing

    avail, standing, status = compute_capacity(bus.current_passengers, bus.max_seated, bus.max_standing)
    bus.status = status
    bus.updated_at = datetime.now()

    delta = bus.current_passengers - prev_pax
    db.add(
        PassengerLog(
            bus_id=bus.bus_id,
            event_source=payload.event_source,
            passenger_delta=delta,
            current_passengers=bus.current_passengers,
            available_seats=avail,
            standing_count=standing,
            status=status,
            lat=bus.lat,
            lng=bus.lng,
        )
    )
    db.commit()
    db.refresh(bus)
    return {"bus": serialize_bus(bus), "passenger_delta": delta}


@app.get("/api/logs")
def get_logs(bus_id: Optional[str] = None, limit: int = 12, db: Session = Depends(get_db)):
    q = db.query(PassengerLog)
    if bus_id:
        q = q.filter(PassengerLog.bus_id == bus_id)
    logs = q.order_by(PassengerLog.log_id.desc()).limit(limit).all()
    return [
        {
            "log_id": l.log_id,
            "bus_id": l.bus_id,
            "event_source": l.event_source,
            "passenger_delta": l.passenger_delta,
            "current_passengers": l.current_passengers,
            "available_seats": l.available_seats,
            "standing_count": l.standing_count,
            "status": l.status,
            "lat": float(l.lat),
            "lng": float(l.lng),
            "logged_at": l.logged_at.isoformat() if l.logged_at else "",
        }
        for l in logs
    ]


# ------------------ 3. Ticketing, Auto-Boarding & Smart Drop-Offs ------------------

@app.post("/api/tickets/issue")
def issue_ticket(payload: TicketIssuePayload, db: Session = Depends(get_db)):
    origin = db.query(BusStop).filter(BusStop.stop_id == payload.origin_stop_id).first()
    dest = db.query(BusStop).filter(BusStop.stop_id == payload.destination_stop_id).first()
    bus = db.query(Bus).filter(Bus.bus_id == payload.bus_id).first()
    if not origin or not dest or not bus:
        raise HTTPException(status_code=404, detail="Invalid bus or route stops selected.")

    dist_km = round(max(0.5, haversine_km(origin.lat, origin.lng, dest.lat, dest.lng)), 2)

    # Philippine Mini-Bus Pricing Formula: ₱15.00 first 4 km + ₱2.20 per succeeding km
    unit_fare = 15.00 + max(0.0, dist_km - 4.0) * 2.20
    if payload.passenger_type.lower() == "discounted":
        unit_fare *= 0.80  # 20% discount for Student / Senior / PWD

    pax_count = max(1, payload.passenger_count)
    total_fare = round(unit_fare * pax_count, 2)

    ticket = Ticket(
        bus_id=bus.bus_id,
        issued_by_user_id=payload.issued_by_user_id,
        origin_stop_id=origin.stop_id,
        destination_stop_id=dest.stop_id,
        distance_km=dist_km,
        passenger_type=payload.passenger_type,
        passenger_count=pax_count,
        fare_amount=total_fare,
        is_onboard=True,
    )
    db.add(ticket)

    # Auto-Boarding: automatically increment current_passengers
    bus.current_passengers += pax_count
    avail, standing, status = compute_capacity(bus.current_passengers, bus.max_seated, bus.max_standing)
    bus.status = status
    bus.updated_at = datetime.now()

    db.add(
        PassengerLog(
            bus_id=bus.bus_id,
            event_source="Ticket Board",
            passenger_delta=pax_count,
            current_passengers=bus.current_passengers,
            available_seats=avail,
            standing_count=standing,
            status=status,
            lat=bus.lat,
            lng=bus.lng,
        )
    )
    db.commit()
    db.refresh(ticket)

    return {
        "ticket_id": ticket.ticket_id,
        "bus_id": bus.bus_id,
        "origin_stop": origin.stop_name,
        "destination_stop": dest.stop_name,
        "distance_km": dist_km,
        "passenger_type": ticket.passenger_type,
        "passenger_count": pax_count,
        "unit_fare": round(unit_fare, 2),
        "total_fare": total_fare,
        "bus": serialize_bus(bus),
    }


@app.get("/api/tickets/dropoffs/{bus_id}")
def get_active_dropoffs(bus_id: str, db: Session = Depends(get_db)):
    stops = {s.stop_id: s for s in db.query(BusStop).all()}
    active_tickets = db.query(Ticket).filter(
        Ticket.bus_id == bus_id,
        Ticket.is_onboard == True
    ).all()

    grouped = {}
    for t in active_tickets:
        st = stops.get(t.destination_stop_id)
        if not st:
            continue
        if st.stop_id not in grouped:
            grouped[st.stop_id] = {
                "destination_stop_id": st.stop_id,
                "stop_name": st.stop_name,
                "stop_order": st.stop_order,
                "lat": float(st.lat),
                "lng": float(st.lng),
                "passengers_dropping_off": 0,
                "ticket_count": 0,
            }
        grouped[st.stop_id]["passengers_dropping_off"] += t.passenger_count
        grouped[st.stop_id]["ticket_count"] += 1

    return sorted(grouped.values(), key=lambda x: x["stop_order"])


@app.post("/api/tickets/dropoff")
def clear_stop_dropoffs(payload: DropOffPayload, db: Session = Depends(get_db)):
    bus = db.query(Bus).filter(Bus.bus_id == payload.bus_id).first()
    if not bus:
        raise HTTPException(status_code=404, detail="Bus not found")

    tickets_to_clear = db.query(Ticket).filter(
        Ticket.bus_id == payload.bus_id,
        Ticket.destination_stop_id == payload.destination_stop_id,
        Ticket.is_onboard == True
    ).all()

    total_alighted = sum(t.passenger_count for t in tickets_to_clear)
    for t in tickets_to_clear:
        t.is_onboard = False
        t.alighted_at = datetime.now()

    if total_alighted > 0:
        bus.current_passengers = max(0, bus.current_passengers - total_alighted)
        avail, standing, status = compute_capacity(bus.current_passengers, bus.max_seated, bus.max_standing)
        bus.status = status
        bus.updated_at = datetime.now()
        db.add(
            PassengerLog(
                bus_id=bus.bus_id,
                event_source="Smart Alight",
                passenger_delta=-total_alighted,
                current_passengers=bus.current_passengers,
                available_seats=avail,
                standing_count=standing,
                status=status,
                lat=bus.lat,
                lng=bus.lng,
            )
        )

    db.commit()
    db.refresh(bus)
    return {
        "alighted_passengers": total_alighted,
        "bus": serialize_bus(bus),
    }


@app.get("/api/tickets")
def list_tickets(bus_id: Optional[str] = None, limit: int = 20, db: Session = Depends(get_db)):
    stops = {s.stop_id: s.stop_name for s in db.query(BusStop).all()}
    q = db.query(Ticket)
    if bus_id:
        q = q.filter(Ticket.bus_id == bus_id)
    items = q.order_by(Ticket.ticket_id.desc()).limit(limit).all()
    return [
        {
            "ticket_id": t.ticket_id,
            "bus_id": t.bus_id,
            "origin_stop": stops.get(t.origin_stop_id, f"Stop #{t.origin_stop_id}"),
            "destination_stop": stops.get(t.destination_stop_id, f"Stop #{t.destination_stop_id}"),
            "distance_km": float(t.distance_km),
            "passenger_type": t.passenger_type,
            "passenger_count": t.passenger_count,
            "fare_amount": float(t.fare_amount),
            "is_onboard": t.is_onboard,
            "issued_at": t.issued_at.isoformat() if t.issued_at else "",
        }
        for t in items
    ]


@app.get("/api/remittance")
def get_daily_remittance(bus_id: Optional[str] = None, db: Session = Depends(get_db)):
    buses = db.query(Bus).order_by(Bus.bus_id).all()
    summary = []
    for b in buses:
        if bus_id and b.bus_id != bus_id:
            continue
        tickets = db.query(Ticket).filter(Ticket.bus_id == b.bus_id).all()
        total_tickets = len(tickets)
        total_pax = sum(t.passenger_count for t in tickets)
        total_fare = round(sum(t.fare_amount for t in tickets), 2)
        summary.append({
            "bus_id": b.bus_id,
            "plate_number": b.plate_number,
            "driver_name": b.driver_name,
            "conductor_name": b.conductor_name,
            "total_tickets": total_tickets,
            "total_passengers_carried": total_pax,
            "total_fare_collected": total_fare,
        })
    return summary


# ------------------ 4. Feedback Endpoints ------------------

@app.post("/api/feedback")
def create_feedback(payload: FeedbackPayload, db: Session = Depends(get_db)):
    fb = Feedback(
        bus_id=payload.bus_id,
        user_id=payload.user_id,
        passenger_name=payload.passenger_name.strip() or "Anonymous",
        category=payload.category,
        message=payload.message.strip(),
        status="Pending",
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return {"message": "Feedback submitted", "feedback_id": fb.feedback_id}


@app.get("/api/feedback")
def get_feedback(db: Session = Depends(get_db)):
    items = db.query(Feedback).order_by(Feedback.feedback_id.desc()).limit(30).all()
    return [
        {
            "feedback_id": f.feedback_id,
            "bus_id": f.bus_id,
            "passenger_name": f.passenger_name,
            "category": f.category,
            "message": f.message,
            "status": f.status,
            "created_at": f.created_at.isoformat() if f.created_at else "",
        }
        for f in items
    ]


@app.put("/api/feedback/{feedback_id}/resolve")
def resolve_feedback(feedback_id: int, db: Session = Depends(get_db)):
    fb = db.query(Feedback).filter(Feedback.feedback_id == feedback_id).first()
    if not fb:
        raise HTTPException(status_code=404, detail="Feedback not found")
    fb.status = "Resolved"
    db.commit()
    return {"message": "Resolved", "feedback_id": feedback_id}


# ------------------ 5. Embedded Live Dispatcher Map Endpoint ------------------

class NewStopRequest(BaseModel):
    stop_name: str
    municipality: str
    lat: float
    lng: float


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


def reorder_stops_safely(db: Session):
    """
    Re-sorts all stops from Bongabon (North-East) to Cabanatuan (South-West)
    using a two-step offset (1000 + idx -> idx) so MySQL's UNIQUE constraint on
    stop_order never throws a Duplicate Entry error.
    """
    all_stops = db.query(BusStop).all()
    sorted_stops = sorted(
        all_stops,
        key=lambda s: (float(s.lat) + float(s.lng)),
        reverse=True,
    )
    for idx, s in enumerate(sorted_stops, start=1):
        s.stop_order = 1000 + idx
    db.flush()

    for idx, s in enumerate(sorted_stops, start=1):
        s.stop_order = idx
    db.commit()
    return sorted_stops


@app.post("/api/stops")
def add_new_bus_stop(payload: NewStopRequest, db: Session = Depends(get_db)):
    clean_name = payload.stop_name.strip()
    clean_muni = payload.municipality.strip() or "Nueva Ecija"
    if not clean_name:
        raise HTTPException(status_code=400, detail="Stop name is required.")

    temp_order = 9000 + db.query(BusStop).count()
    new_stop = BusStop(
        stop_name=clean_name,
        municipality=clean_muni,
        lat=round(float(payload.lat), 7),
        lng=round(float(payload.lng), 7),
        stop_order=temp_order,
    )
    db.add(new_stop)
    db.commit()
    db.refresh(new_stop)

    reorder_stops_safely(db)

    return {
        "message": f"Added {clean_name} ({clean_muni}) and updated route order!",
        "stop_id": new_stop.stop_id,
    }


@app.get("/api/map", response_class=HTMLResponse)
def get_live_leaflet_map():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8" />
        <title>BusWatch — Interactive Dispatcher Map</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
            body { margin: 0; font-family: 'Segoe UI', Tahoma, sans-serif; background: #F8F3EA; color: #2D262B; }
            .top-bar {
                background: #B47792; color: #FFFFFF; padding: 12px 18px;
                border-bottom: 4px solid #FA9EBC; display: flex; flex-wrap: wrap;
                justify-content: space-between; align-items: center; gap: 10px;
            }
            .add-stop-bar {
                background: #FFDBD1; color: #2D262B; padding: 10px 18px;
                border-bottom: 2px solid #B47792; display: flex; flex-wrap: wrap;
                align-items: center; gap: 8px; font-size: 14px;
            }
            .input-box {
                padding: 7px 10px; border: 1.5px solid #B47792; border-radius: 8px;
                background: #FFFFFF; color: #2D262B; font-weight: 600;
            }
            .mauve-btn {
                background: #B47792; color: #FFFFFF; border: none; padding: 8px 14px;
                border-radius: 8px; font-weight: 700; cursor: pointer;
            }
            .danger-btn {
                background: #b71c1c; color: #FFFFFF; border: none; padding: 8px 12px;
                border-radius: 8px; font-weight: 700; cursor: pointer;
            }
            #map { height: calc(100vh - 122px); width: 100%; cursor: crosshair; }
        </style>
    </head>
    <body>
        <div class="top-bar">
            <div>
                <strong style="font-size: 19px;"> BusWatch — Dispatcher Interactive Route Map</strong><br>
                <small>Click anywhere on the map to add a stop, or click an existing stop circle to remove it.</small>
            </div>
            <div id="statusBadge" style="background: #FFDBD1; color: #2D262B; padding: 6px 12px; border-radius: 8px; font-weight: 700;">
               Sorted by Location • Live Sync Active
            </div>
        </div>

        <div class="add-stop-bar">
            <b>Search Location:</b>
            <input
                id="mapSearchInput"
                class="input-box"
                placeholder="Search stop or place..."
                style="width: 190px;"
                onkeydown="if(event.key==='Enter') searchDispatcherMap()"
            />
            <button class="mauve-btn" onclick="searchDispatcherMap()">Search</button>
            <span>|</span>

            <b>Add Stop:</b>
            <input id="stopName" class="input-box" placeholder="Location Name (e.g. Brgy. Cruz)" style="width: 190px;" />
            <select id="stopMuni" class="input-box">
                <option value="Bongabon">Bongabon</option>
                <option value="Palayan City">Palayan City</option>
                <option value="Cabanatuan City">Cabanatuan City</option>
            </select>
            <input id="stopLat" class="input-box" placeholder="Click map Lat" style="width: 105px;" readonly />
            <input id="stopLng" class="input-box" placeholder="Click map Lng" style="width: 105px;" readonly />
            <button class="mauve-btn" onclick="saveNewStop()">➕ Add Stop</button>

            <span style="margin-left: 10px;">|</span>
            <b>Remove Stop:</b>
            <select id="removeStopSelect" class="input-box" style="width: 210px;"></select>
            <button class="danger-btn" onclick="removeSelectedStop()">Remove</button>
        </div>

        <div id="map"></div>

        <script>
            const map = L.map('map', { minZoom: 10, maxZoom: 18 }).setView([15.5565427, 121.0925970], 12);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '© OpenStreetMap contributors',
                noWrap: true
            }).addTo(map);

            const busMarkers = {};
            let stopMarkers = [];
            let cachedStops = [];
            let routePolyline = null;
            let tempClickMarker = null;

            map.on('click', function(e) {
                const lat = e.latlng.lat.toFixed(7);
                const lng = e.latlng.lng.toFixed(7);
                document.getElementById('stopLat').value = lat;
                document.getElementById('stopLng').value = lng;

                if (tempClickMarker) {
                    tempClickMarker.setLatLng(e.latlng);
                } else {
                    tempClickMarker = L.marker(e.latlng).addTo(map);
                }
                tempClickMarker.bindPopup(
                    `<b>Selected Location</b><br>Lat: ${lat}, Lng: ${lng}<br><i>Enter name above and click "➕ Add Stop"</i>`
                ).openPopup();
                document.getElementById('stopName').focus();
            });

            async function saveNewStop() {
                const name = document.getElementById('stopName').value.trim();
                const muni = document.getElementById('stopMuni').value;
                const lat = parseFloat(document.getElementById('stopLat').value);
                const lng = parseFloat(document.getElementById('stopLng').value);
                const badge = document.getElementById('statusBadge');

                if (!name) { alert('Please type a Location Name first.'); return; }
                if (isNaN(lat) || isNaN(lng)) { alert('Please click on the map or search a place first.'); return; }

                if (!confirm(`Are you sure you want to add "${name}" (${muni}) to the official route?`)) {
                    return;
                }

                const res = await fetch('/api/stops', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ stop_name: name, municipality: muni, lat, lng })
                });

                if (res.ok) {
                    document.getElementById('stopName').value = '';
                    if (tempClickMarker) {
                        map.removeLayer(tempClickMarker);
                        tempClickMarker = null;
                    }
                    badge.textContent = `Added "${name}" — Route Auto-Sorted!`;
                    badge.style.background = '#c8e6c9';
                    badge.style.color = '#1b5e20';
                    await loadRoadRoute();
                }
            }

            async function deleteStopById(stopId, stopName) {
                if (!confirm(`Are you sure you want to remove stop "${stopName}" from the route?`)) {
                    return;
                }

                const badge = document.getElementById('statusBadge');
                const res = await fetch(`/api/stops/${stopId}`, { method: 'DELETE' });
                if (res.ok) {
                    badge.textContent = `Removed "${stopName}" — Route Updated!`;
                    badge.style.background = '#ffcdd2';
                    badge.style.color = '#b71c1c';
                    await loadRoadRoute();
                }
            }

            async function removeSelectedStop() {
                const sel = document.getElementById('removeStopSelect');
                if (!sel.value) return;
                const stopId = sel.value;
                const stopName = sel.options[sel.selectedIndex].text;
                await deleteStopById(stopId, stopName);
            }

            async function loadRoadRoute() {
                const res = await fetch('/api/stops');
                const rawStops = await res.json();

                const stops = rawStops.sort((a, b) => (Number(b.lat) + Number(b.lng)) - (Number(a.lat) + Number(a.lng)));
                cachedStops = stops;

                stopMarkers.forEach(m => map.removeLayer(m));
                stopMarkers = [];

                const removeSelect = document.getElementById('removeStopSelect');
                removeSelect.innerHTML = '';

                const fallbackCoords = [];
                stops.forEach((s) => {
                    fallbackCoords.push([s.lat, s.lng]);

                    const opt = document.createElement('option');
                    opt.value = s.stop_id;
                    opt.textContent = `${s.stop_name} (${s.municipality})`;
                    removeSelect.appendChild(opt);

                    const m = L.circleMarker([s.lat, s.lng], {
                        radius: 8, fillColor: '#B47792', color: '#2D262B', weight: 2, fillOpacity: 0.95
                    }).addTo(map).bindPopup(
                        `<b>${s.stop_name}</b><br>${s.municipality}<br><br>` +
                        `<button class="danger-btn" style="padding:4px 8px;font-size:12px;" onclick="deleteStopById(${s.stop_id}, '${s.stop_name.replace(/'/g, "\\'")}')">Remove Stop</button>`
                    );
                    stopMarkers.push(m);
                });

                let routeCoords = fallbackCoords;
                try {
                    const coordStr = stops.map(s => `${s.lng},${s.lat}`).join(';');
                    const osrmRes = await fetch(`https://router.project-osrm.org/route/v1/driving/${coordStr}?overview=full&geometries=geojson`);
                    if (osrmRes.ok) {
                        const osrmData = await osrmRes.json();
                        if (osrmData.routes && osrmData.routes.length > 0) {
                            routeCoords = osrmData.routes[0].geometry.coordinates.map(c => [c[1], c[0]]);
                        }
                    }
                } catch (e) {}

                if (routePolyline) { map.removeLayer(routePolyline); }
                routePolyline = L.polyline(routeCoords, { color: '#B47792', weight: 5, opacity: 0.9 }).addTo(map);
            }

            async function searchDispatcherMap() {
                const query = document.getElementById('mapSearchInput').value.trim();
                const badge = document.getElementById('statusBadge');
                if (!query) return;

                const qLower = query.toLowerCase();
                const matchedStop = cachedStops.find(
                    s => s.stop_name.toLowerCase().includes(qLower) || s.municipality.toLowerCase().includes(qLower)
                );
                if (matchedStop) {
                    map.setView([matchedStop.lat, matchedStop.lng], 15);
                    badge.textContent = `Found: ${matchedStop.stop_name}`;
                    return;
                }

                try {
                    const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query + ', Nueva Ecija, Philippines')}&limit=1`;
                    const res = await fetch(url);
                    const results = await res.json();
                    if (results && results.length > 0) {
                        const lat = parseFloat(results[0].lat);
                        const lng = parseFloat(results[0].lon);
                        const shortName = results[0].display_name.split(',')[0];

                        map.setView([lat, lng], 15);
                        document.getElementById('stopName').value = shortName;
                        document.getElementById('stopLat').value = lat.toFixed(7);
                        document.getElementById('stopLng').value = lng.toFixed(7);

                        if (tempClickMarker) {
                            tempClickMarker.setLatLng([lat, lng]);
                        } else {
                            tempClickMarker = L.marker([lat, lng]).addTo(map);
                        }
                        tempClickMarker.bindPopup(
                            `<b>Selected Location: ${shortName}</b><br>Lat: ${lat.toFixed(7)}, Lng: ${lng.toFixed(7)}`
                        ).openPopup();
                        badge.textContent = `Found: ${shortName}`;
                    } else {
                        badge.textContent = `Location "${query}" not found`;
                    }
                } catch (e) {
                    badge.textContent = 'Search unavailable offline';
                }
            }

            async function syncBuses() {
                const res = await fetch('/api/buses');
                const buses = await res.json();

                // Remove markers for buses marked Inactive
                const activeIds = new Set(buses.map(b => b.bus_id));
                Object.keys(busMarkers).forEach(id => {
                    if (!activeIds.has(id)) {
                        map.removeLayer(busMarkers[id]);
                        delete busMarkers[id];
                    }
                });

                buses.forEach(b => {
                    const html = `<div style="background:#B47792;color:#fff;padding:4px 10px;border-radius:10px;font-weight:700;font-size:12px;border:2px solid #FA9EBC;white-space:nowrap;"> ${b.bus_id} (${b.available_seats} free)</div>`;
                    const icon = L.divIcon({ html, className: '', iconSize: [130, 26], iconAnchor: [65, 13] });
                    const popup = `<b>${b.bus_id} (${b.plate_number})</b><br>Driver: ${b.driver_name}<br>Conductor: ${b.conductor_name}<br>Onboard: ${b.current_passengers}<br>Seats Available: ${b.available_seats}<br>Status: ${b.status}`;
                    if (busMarkers[b.bus_id]) {
                        busMarkers[b.bus_id].setLatLng([b.lat, b.lng]).setIcon(icon).setPopupContent(popup);
                    } else {
                        busMarkers[b.bus_id] = L.marker([b.lat, b.lng], { icon }).addTo(map).bindPopup(popup);
                    }
                });
            }

            loadRoadRoute();
            syncBuses();
            setInterval(syncBuses, 2500);
        </script>
    </body>
    </html>
    """


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
