import math
import socket
import time
import requests

def get_local_lan_url() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return f"http://{ip}:8000"
    except Exception:
        return "http://127.0.0.1:8000"

# Candidate URLs to check automatically (Localhost -> Auto LAN IP -> Saved IPs)
CANDIDATE_URLS = [
    "http://127.0.0.1:8000",
    get_local_lan_url(),
    "http://192.168.1.8:8000",
    "http://192.168.1.6:8000",
    "http://192.168.137.1:8000",
    "http://172.24.209.224:8000",
    "http://192.168.1.224:8000",
]

SERVER_URL = CANDIDATE_URLS[0]

# Realistic Road Timing & Movement Settings
TICK_SECONDS = 2.0          # Seconds between each GPS broadcast
STEPS_PER_KM = 3            # Simulation steps per kilometer of road
MIN_SEGMENT_STEPS = 14      # Minimum steps between nearby stops
MAX_SEGMENT_STEPS = 50      # Maximum steps between distant stops
STOP_DWELL_TICKS = 4        # Pause at regular stops (4 ticks = 8 seconds)
TERMINAL_DWELL_TICKS = 7    # Pause at Bongabon/Cabanatuan terminals (7 ticks = 14 seconds)

HTTP_HEADERS = {"User-Agent": "BusWatchSimulator/1.0"}

bus_states = {}
smooth_waypoints = []
last_stops_signature = None


def detect_active_server() -> str:
    """Finds which Server URL is reachable so you don't have to edit IPs manually."""
    print("Scanning for active FastAPI Bus Server...")
    seen = []
    for u in CANDIDATE_URLS:
        if u not in seen:
            seen.append(u)

    while True:
        for url in seen:
            try:
                res = requests.get(f"{url}/api/stops", timeout=2)
                if res.status_code == 200:
                    print(f"Connected to FastAPI Server at: {url}\n")
                    return url
            except requests.exceptions.RequestException:
                pass

        print("Server not reachable yet. Make sure 'python server.py' is running...")
        time.sleep(2)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates real-world distance in km between two GPS coordinates."""
    r = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return r * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def smooth_step_fraction(t: float) -> float:
    """Slows the bus down as it approaches a stop and accelerates smoothly leaving it."""
    cosine_ease = 0.5 * (1.0 - math.cos(math.pi * t))
    return 0.35 * t + 0.65 * cosine_ease


def fetch_road_path(start_stop: dict, end_stop: dict) -> list:
    """
    Fetches exact highway geometry between two stops from OSRM.
    Falls back to a direct line only if there is no internet connection.
    """
    lat1, lng1 = float(start_stop["lat"]), float(start_stop["lng"])
    lat2, lng2 = float(end_stop["lat"]), float(end_stop["lng"])
    osrm_url = (
        f"https://router.project-osrm.org/route/v1/driving/"
        f"{lng1},{lat1};{lng2},{lat2}?overview=full&geometries=geojson"
    )
    try:
        res = requests.get(osrm_url, headers=HTTP_HEADERS, timeout=4)
        if res.status_code == 200:
            data = res.json()
            routes = data.get("routes", [])
            if routes:
                coords = routes[0]["geometry"]["coordinates"]
                road_pts = [(float(c[1]), float(c[0])) for c in coords]
                if len(road_pts) >= 2:
                    return road_pts
    except requests.exceptions.RequestException:
        pass

    return [(lat1, lng1), (lat2, lng2)]


def sample_point_along_road(road_pts: list, cumulative_km: list, target_km: float) -> tuple:
    """Finds the exact (lat, lng) on the road polyline at a given distance from the start stop."""
    total_km = cumulative_km[-1]
    if total_km <= 0.0 or target_km <= 0.0:
        return road_pts[0]
    if target_km >= total_km:
        return road_pts[-1]

    for i in range(len(cumulative_km) - 1):
        d0 = cumulative_km[i]
        d1 = cumulative_km[i + 1]
        if d0 <= target_km <= d1:
            seg_len = d1 - d0
            if seg_len <= 1e-9:
                return road_pts[i]
            local_frac = (target_km - d0) / seg_len
            lat = road_pts[i][0] + (road_pts[i + 1][0] - road_pts[i][0]) * local_frac
            lng = road_pts[i][1] + (road_pts[i + 1][1] - road_pts[i][1]) * local_frac
            return (lat, lng)

    return road_pts[-1]


def build_waypoints_from_server() -> bool:
    """Fetches official stops from /api/stops and builds a road-snapped round-trip loop."""
    global smooth_waypoints, last_stops_signature
    try:
        res = requests.get(f"{SERVER_URL}/api/stops", timeout=3)
        if res.status_code != 200:
            return False

        stops = res.json()
        if len(stops) < 2:
            return False

        last_stops_signature = tuple((s["stop_id"], round(float(s["lat"]), 5), round(float(s["lng"]), 5)) for s in stops)

        first_stop_id = stops[0]["stop_id"]
        last_stop_id = stops[-1]["stop_id"]

        # Round-trip ping-pong order: Stop 1 -> Stop N -> Stop 1
        full_cycle = stops + list(reversed(stops[1:-1]))
        waypoints = []

        print("Building road-snapped highway path from OpenStreetMap (OSRM)...")
        for i in range(len(full_cycle)):
            start_stop = full_cycle[i]
            end_stop = full_cycle[(i + 1) % len(full_cycle)]

            road_pts = fetch_road_path(start_stop, end_stop)

            cumulative_km = [0.0]
            for j in range(1, len(road_pts)):
                seg_d = haversine_km(
                    road_pts[j - 1][0],
                    road_pts[j - 1][1],
                    road_pts[j][0],
                    road_pts[j][1],
                )
                cumulative_km.append(cumulative_km[-1] + seg_d)

            total_road_km = max(0.2, cumulative_km[-1])
            segment_steps = max(
                MIN_SEGMENT_STEPS,
                min(MAX_SEGMENT_STEPS, int(round(total_road_km * STEPS_PER_KM))),
            )

            is_terminal = start_stop["stop_id"] in (first_stop_id, last_stop_id)
            dwell_ticks = TERMINAL_DWELL_TICKS if is_terminal else STOP_DWELL_TICKS

            for step in range(segment_steps):
                raw_t = step / float(segment_steps)
                fraction = 0.0 if step == 0 else smooth_step_fraction(raw_t)
                target_km = fraction * total_road_km

                if step == 0:
                    lat, lng = float(start_stop["lat"]), float(start_stop["lng"])
                else:
                    lat, lng = sample_point_along_road(road_pts, cumulative_km, target_km)

                if step == 0:
                    speed_state = "TERMINAL LAYOVER" if is_terminal else "STOPPED AT STATION"
                    label = f"{start_stop['stop_name']} ({speed_state})"
                elif step <= 2:
                    label = f"Departing {start_stop['stop_name']} -> {end_stop['stop_name']}"
                elif step >= segment_steps - 2:
                    label = f"Approaching {end_stop['stop_name']} (Slowing down)"
                else:
                    label = f"On Highway -> {end_stop['stop_name']}"

                waypoints.append({
                    "lat": round(lat, 7),
                    "lng": round(lng, 7),
                    "at_stop_id": start_stop["stop_id"] if step == 0 else None,
                    "stop_name": start_stop["stop_name"] if step == 0 else None,
                    "dwell_ticks": dwell_ticks if step == 0 else 0,
                    "stop_label": label,
                })

        smooth_waypoints = waypoints
        print(f"Loaded {len(smooth_waypoints)} road-snapped GPS waypoints!\n")
        return True
    except requests.exceptions.RequestException:
        return False


def find_closest_waypoint_index(lat: float, lng: float) -> int:
    """Finds the road waypoint closest to a bus's current coordinates."""
    best_idx = 0
    best_dist = float("inf")
    for idx, wp in enumerate(smooth_waypoints):
        dist = (wp["lat"] - lat) ** 2 + (wp["lng"] - lng) ** 2
        if dist < best_dist:
            best_dist = dist
            best_idx = idx
    return best_idx


def post_bus_position(bus_data: dict, lat: float, lng: float) -> bool:
    """Sends the updated GPS coordinates to the FastAPI server and checks for errors."""
    res = requests.post(
        f"{SERVER_URL}/api/buses/update",
        json={
            "bus_id": bus_data["bus_id"],
            "route_name": bus_data["route_name"],
            "lat": lat,
            "lng": lng,
            "current_passengers": bus_data["current_passengers"],
            "max_seated": bus_data["max_seated"],
            "max_standing": bus_data["max_standing"],
            "event_source": "GPS Simulator",
        },
        timeout=3,
    )
    if res.status_code != 200:
        print(f"Server rejected GPS update for {bus_data['bus_id']} (HTTP {res.status_code}): {res.text}")
        return False
    return True


def run_simulation():
    global SERVER_URL
    SERVER_URL = detect_active_server()

    print(f"Road-Snapped Fleet Simulator Running on {SERVER_URL}")

    while not build_waypoints_from_server():
        print("Waiting for /api/stops...")
        time.sleep(2)

    tick_counter = 0

    while True:
        try:
            # Periodically check if Dispatcher added or removed stops
            tick_counter += 1
            if tick_counter % 5 == 0:
                stops_res = requests.get(f"{SERVER_URL}/api/stops", timeout=2)
                if stops_res.status_code == 200:
                    current_sig = tuple(
                        (s["stop_id"], round(float(s["lat"]), 5), round(float(s["lng"]), 5))
                        for s in stops_res.json()
                    )
                    if current_sig != last_stops_signature and len(current_sig) >= 2:
                        print("\nRoute stops changed! Rebuilding road-snapped waypoints...")
                        build_waypoints_from_server()
                        bus_states.clear()

            res = requests.get(f"{SERVER_URL}/api/buses", timeout=3)
            if res.status_code != 200:
                time.sleep(2)
                continue

            live_buses = res.json()
            if not live_buses:
                print("No active buses found (all buses may be marked Inactive in Dispatcher).")
                time.sleep(TICK_SECONDS)
                continue

            for idx_offset, bus_data in enumerate(live_buses):
                bus_id = bus_data["bus_id"]
                db_lat = float(bus_data["lat"])
                db_lng = float(bus_data["lng"])

                if bus_id not in bus_states:
                    start_idx = find_closest_waypoint_index(db_lat, db_lng)
                    start_wp = smooth_waypoints[start_idx]
                    initial_dwell = max(1, start_wp["dwell_ticks"] - (idx_offset % 3)) if start_wp["at_stop_id"] else 0
                    bus_states[bus_id] = {
                        "wp_idx": start_idx,
                        "dwell_remaining": initial_dwell,
                        "just_arrived": True,
                        "expected_lat": db_lat,
                        "expected_lng": db_lng,
                    }
                    print(f"Auto-detected mini-bus: {bus_id} ({bus_data['plate_number']}) — joined highway route!")

                state = bus_states[bus_id]

                # Only relocate if the database coordinates externally changed from what the simulator last set
                if (
                    abs(db_lat - state["expected_lat"]) > 0.002
                    or abs(db_lng - state["expected_lng"]) > 0.002
                ):
                    new_idx = find_closest_waypoint_index(db_lat, db_lng)
                    new_wp = smooth_waypoints[new_idx]
                    state["wp_idx"] = new_idx
                    state["dwell_remaining"] = new_wp["dwell_ticks"]
                    state["just_arrived"] = True
                    state["expected_lat"] = db_lat
                    state["expected_lng"] = db_lng
                    print(f"Dispatcher relocated {bus_id} -> syncing to {new_wp['stop_label']}")

                wp_idx = state["wp_idx"]
                wp = smooth_waypoints[wp_idx]

                # CASE 1: Bus is currently parked at a Bus Stop or Terminal
                if state["dwell_remaining"] > 0:
                    if state["just_arrived"]:
                        if post_bus_position(bus_data, wp["lat"], wp["lng"]):
                            state["expected_lat"] = wp["lat"]
                            state["expected_lng"] = wp["lng"]

                        if wp["at_stop_id"] is not None:
                            requests.post(
                                f"{SERVER_URL}/api/tickets/dropoff",
                                json={
                                    "bus_id": bus_id,
                                    "destination_stop_id": wp["at_stop_id"],
                                },
                                timeout=3,
                            )
                        state["just_arrived"] = False

                    secs_left = int(state["dwell_remaining"] * TICK_SECONDS)
                    print(
                        f"[{bus_id} | {bus_data['plate_number']}] "
                        f"PARKED AT {wp['stop_name']} (Boarding/Alighting: {secs_left}s left) | "
                        f"Pax: {bus_data['current_passengers']}"
                    )

                    state["dwell_remaining"] -= 1
                    if state["dwell_remaining"] == 0:
                        next_idx = (wp_idx + 1) % len(smooth_waypoints)
                        state["wp_idx"] = next_idx
                        state["just_arrived"] = True

                # CASE 2: Bus is driving along the road curve between stops
                else:
                    if post_bus_position(bus_data, wp["lat"], wp["lng"]):
                        state["expected_lat"] = wp["lat"]
                        state["expected_lng"] = wp["lng"]

                    print(
                        f"[{bus_id} | {bus_data['plate_number']}] "
                        f"({wp['lat']:.5f}, {wp['lng']:.5f}) | {wp['stop_label']} | "
                        f"Pax: {bus_data['current_passengers']}"
                    )

                    next_idx = (wp_idx + 1) % len(smooth_waypoints)
                    next_wp = smooth_waypoints[next_idx]
                    state["wp_idx"] = next_idx
                    state["dwell_remaining"] = next_wp["dwell_ticks"]
                    state["just_arrived"] = True

            print("-" * 92)
            time.sleep(TICK_SECONDS)

        except KeyboardInterrupt:
            print("\nSimulation stopped.")
            break
        except requests.exceptions.RequestException as ex:
            print(f"Temporary connection hiccup: {ex}. Retrying...")
            time.sleep(2)


if __name__ == "__main__":
    run_simulation()