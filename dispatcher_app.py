import webbrowser
import flet as ft
import requests

# Pastel Pink, Warm Cream & Dark Neutral Palette
BG_CREAM = "#F8F3EA"
CARD_WHITE = "#FFFFFF"
ACCENT_MAUVE = "#B47792"
SOFT_PEACH = "#FFDBD1"
PASTEL_PINK = "#FA9EBC"
TEXT_DARK = "#2D262B"

OFFICIAL_ROUTE = "Bongabon Terminal - Cabanatuan City Central Transport Terminal (via Palayan City)"


def input_border(color: str = ACCENT_MAUVE):
    return ft.OutlineInputBorder(side=ft.BorderSide(width=2, color=color))


def table_card(title: str, table_control: ft.Control) -> ft.Container:
    """Wraps any DataTable inside a full-width responsive container card."""
    return ft.Container(
        padding=18,
        bgcolor=CARD_WHITE,
        border_radius=14,
        border=ft.Border.all(2, PASTEL_PINK),
        content=ft.Column(
            spacing=12,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                ft.Text(title, size=18, weight=ft.FontWeight.BOLD, color=ACCENT_MAUVE),
                table_control,
            ],
        ),
    )


def main(page: ft.Page):
    page.title = "BusWatch - Cooperative Dispatcher Console"
    page.window.width = 1080
    page.window.height = 920
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = BG_CREAM
    page.scroll = ft.ScrollMode.AUTO
    page.padding = 24
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH

    current_user = {"user_id": None, "full_name": "Guest", "username": ""}
    stops_list = []
    stops_cache = {}
    buses_cache = {}

    server_ip = ft.TextField(
        label="Server Address (Change IP here if network changes)",
        value="http://192.168.1.8:8000",
        expand=True,
        visible=False,  # Hidden by default
        text_size=15,
        border=input_border(ACCENT_MAUVE),
        color=TEXT_DARK,
    )

    def toggle_server_ip(e=None):
        server_ip.visible = not server_ip.visible
        page.update()

    status_banner = ft.Container(
        padding=12,
        bgcolor=SOFT_PEACH,
        border_radius=10,
        border=ft.Border.all(1.5, ACCENT_MAUVE),
        content=ft.Text(
            "Welcome! Please log in with your Dispatcher account to begin.",
            size=15,
            weight=ft.FontWeight.BOLD,
            color=TEXT_DARK,
        ),
    )

    def set_status(msg: str, color: str = TEXT_DARK, bg: str = SOFT_PEACH):
        status_banner.bgcolor = bg
        status_banner.content.value = msg
        status_banner.content.color = color
        page.update()

    def base_url() -> str:
        return server_ip.value.strip().rstrip("/")

    # =========================================================================
    # SEPARATED AUTHENTICATION VIEW (LOG IN vs. CREATE ACCOUNT)
    # =========================================================================
    auth_title = ft.Text("Dispatcher Log In", size=24, weight=ft.FontWeight.BOLD, color=ACCENT_MAUVE)
    auth_subtitle = ft.Text(
        "Enter your cooperative username and password below:",
        size=14,
        color=TEXT_DARK,
    )

    auth_username = ft.TextField(
        label="Dispatcher Username",
        value="",
        width=380,
        text_size=16,
        border=input_border(),
    )
    auth_password = ft.TextField(
        label="Password",
        value="",
        password=True,
        can_reveal_password=True,
        width=380,
        text_size=16,
        border=input_border(),
    )
    auth_fullname = ft.TextField(
        label="Your Full Name (e.g., Juan Dela Cruz)",
        value="",
        width=380,
        text_size=16,
        visible=False,
        border=input_border(),
    )
    auth_contact = ft.TextField(
        label="Contact Mobile Number (Optional)",
        value="",
        width=380,
        text_size=16,
        visible=False,
        border=input_border(),
    )

    def toggle_auth_mode(is_signup: bool):
        auth_fullname.visible = is_signup
        auth_contact.visible = is_signup
        if is_signup:
            auth_title.value = "Create New Dispatcher Account"
            auth_subtitle.value = "Fill in all boxes below to register a new dispatcher account."
            btn_mode_login.bgcolor = BG_CREAM
            btn_mode_login.color = TEXT_DARK
            btn_mode_signup.bgcolor = ACCENT_MAUVE
            btn_mode_signup.color = CARD_WHITE
            btn_submit_login.visible = False
            btn_submit_signup.visible = True
        else:
            auth_title.value = "Dispatcher Log In"
            auth_subtitle.value = "Enter your cooperative username and password below."
            btn_mode_login.bgcolor = ACCENT_MAUVE
            btn_mode_login.color = CARD_WHITE
            btn_mode_signup.bgcolor = BG_CREAM
            btn_mode_signup.color = TEXT_DARK
            btn_submit_login.visible = True
            btn_submit_signup.visible = False
        page.update()

    def handle_login(e=None):
        uname = (auth_username.value or "").strip()
        pword = (auth_password.value or "").strip()
        if not uname or not pword:
            set_status("Please type both your Username and Password to log in.", "#b71c1c", "#ffcdd2")
            return
        try:
            res = requests.post(
                f"{base_url()}/api/auth/login",
                json={"username": uname, "password": pword, "role": "Dispatcher"},
                timeout=4,
            )
            if res.status_code == 200:
                data = res.json()
                current_user.update(data)
                auth_card.visible = False
                main_workspace.visible = True
                btn_logout.visible = True
                set_status(
                    f"Logged in as Dispatcher: {data['full_name']} (@{data['username']})",
                    "#1b5e20",
                    "#c8e6c9",
                )
                sync_all()
            else:
                err_msg = (
                    res.json().get("detail", "Invalid username or password")
                    if "application/json" in res.headers.get("content-type", "")
                    else res.text
                )
                set_status(f"Log-In Failed: {err_msg}", "#b71c1c", "#ffcdd2")
        except Exception as ex:
            set_status(f"Cannot connect to server ({base_url()}). Check Server IP above. ({ex})", "#b71c1c", "#ffcdd2")

    def handle_signup(e=None):
        uname = (auth_username.value or "").strip()
        pword = (auth_password.value or "").strip()
        fname = (auth_fullname.value or "").strip() or uname
        contact = (auth_contact.value or "").strip()
        if not uname or not pword:
            set_status("Please enter a Username and Password to create your account.", "#b71c1c", "#ffcdd2")
            return
        try:
            res = requests.post(
                f"{base_url()}/api/auth/signup",
                json={
                    "username": uname,
                    "password": pword,
                    "full_name": fname,
                    "role": "Dispatcher",
                    "contact_number": contact,
                },
                timeout=4,
            )
            if res.status_code == 200:
                data = res.json()
                current_user.update(data)
                auth_card.visible = False
                main_workspace.visible = True
                btn_logout.visible = True
                set_status(
                    f"Account Created! Welcome, Dispatcher {data['full_name']} (@{data['username']})",
                    "#1b5e20",
                    "#c8e6c9",
                )
                sync_all()
            else:
                err_msg = (
                    res.json().get("detail", "Sign-Up failed")
                    if "application/json" in res.headers.get("content-type", "")
                    else res.text
                )
                set_status(f"Sign-Up Error: {err_msg}", "#b71c1c", "#ffcdd2")
        except Exception as ex:
            set_status(f"Cannot connect to server ({base_url()}). Check Server IP above. ({ex})", "#b71c1c", "#ffcdd2")

    def handle_logout(e=None):
        current_user.update({"user_id": None, "full_name": "Guest", "username": ""})
        auth_password.value = ""
        main_workspace.visible = False
        btn_logout.visible = False
        auth_card.visible = True
        set_status("You have logged out safely.", TEXT_DARK, SOFT_PEACH)

    btn_mode_login = ft.Button(
        "1. Existing User (Log In)",
        icon=ft.Icons.LOGIN,
        height=46,
        bgcolor=ACCENT_MAUVE,
        color=CARD_WHITE,
        on_click=lambda _: toggle_auth_mode(False),
    )
    btn_mode_signup = ft.Button(
        "2. New Dispatcher (Create Account)",
        icon=ft.Icons.PERSON_ADD,
        height=46,
        bgcolor=BG_CREAM,
        color=TEXT_DARK,
        on_click=lambda _: toggle_auth_mode(True),
    )

    btn_submit_login = ft.Button(
        "Log In to Dispatcher Console",
        icon=ft.Icons.LOCK_OPEN,
        width=380,
        height=50,
        bgcolor=ACCENT_MAUVE,
        color=CARD_WHITE,
        on_click=handle_login,
    )
    btn_submit_signup = ft.Button(
        "Register & Open Console",
        icon=ft.Icons.CHECK_CIRCLE,
        width=380,
        height=50,
        visible=False,
        bgcolor=PASTEL_PINK,
        color=TEXT_DARK,
        on_click=handle_signup,
    )

    auth_card = ft.Container(
        visible=True,
        padding=32,
        bgcolor=CARD_WHITE,
        border_radius=18,
        border=ft.Border.all(2.5, PASTEL_PINK),
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=14,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=12,
                    controls=[btn_mode_login, btn_mode_signup],
                ),
                ft.Divider(color=PASTEL_PINK),
                auth_title,
                auth_subtitle,
                auth_username,
                auth_password,
                auth_fullname,
                auth_contact,
                btn_submit_login,
                btn_submit_signup,
            ],
        ),
    )

    # =========================================================================
    # WORKSPACE 1: TERMINAL SEND-OFF, SHIFT CREW ASSIGNMENT & LIVE CORRIDOR
    # =========================================================================
    route_corridor_row = ft.Row(wrap=True, spacing=10)

    bus_selector = ft.Dropdown(
        label="Step 1: Select Mini-Bus Unit",
        value="BUS-101",
        options=[
            ft.DropdownOption("BUS-101"),
            ft.DropdownOption("BUS-102"),
            ft.DropdownOption("BUS-103"),
            ft.DropdownOption("BUS-104"),
            ft.DropdownOption("BUS-105"),
        ],
        width=260,
    )

    # Read-Only Ticket-Driven Occupancy Banner (No Ghost Passengers Allowed)
    live_occupancy_banner = ft.Container(
        padding=12,
        bgcolor=SOFT_PEACH,
        border_radius=10,
        border=ft.Border.all(1.5, ACCENT_MAUVE),
        content=ft.Text("", size=14, weight=ft.FontWeight.BOLD, color=TEXT_DARK),
    )

    # Temporary Shift Crew Fields (Can be changed per shift/trip)
    shift_driver_input = ft.TextField(
        label="Driver on Duty",
        value="",
        expand=True,
        text_size=15,
        border=input_border(),
    )
    shift_conductor_input = ft.TextField(
        label="Conductor on Duty",
        value="",
        expand=True,
        text_size=15,
        border=input_border(),
    )

    # Terminal Send-Off Selector
    terminal_dropdown = ft.Dropdown(
        label="Step 3: Select Departure Terminal for Send-Off",
        expand=True,
    )
    
    remove_stop_dropdown = ft.Dropdown(
        label="Select Location to Remove from Route",
        expand=True,
    )

    logs_table = ft.DataTable(
        width=float("inf"),
        heading_row_color=SOFT_PEACH,
        column_spacing=20,
        columns=[
            ft.DataColumn(ft.Text("Time", weight=ft.FontWeight.BOLD, color=TEXT_DARK)),
            ft.DataColumn(ft.Text("Bus Unit", weight=ft.FontWeight.BOLD, color=TEXT_DARK)),
            ft.DataColumn(ft.Text("Event Source", weight=ft.FontWeight.BOLD, color=TEXT_DARK)),
            ft.DataColumn(ft.Text("Ticket Delta", weight=ft.FontWeight.BOLD, color=TEXT_DARK)),
            ft.DataColumn(ft.Text("Onboard", weight=ft.FontWeight.BOLD, color=TEXT_DARK)),
            ft.DataColumn(ft.Text("Seats Available", weight=ft.FontWeight.BOLD, color=TEXT_DARK)),
            ft.DataColumn(ft.Text("Standing", weight=ft.FontWeight.BOLD, color=TEXT_DARK)),
            ft.DataColumn(ft.Text("Capacity Status", weight=ft.FontWeight.BOLD, color=TEXT_DARK)),
        ],
        rows=[],
    )

    # =========================================================================
    # WORKSPACE 2: PERMANENT FLEET REGISTRATION & VEHICLE SPECS
    # =========================================================================
    reg_bus_id = ft.TextField(label="Bus Unit Number (e.g. BUS-106)", value="BUS-106", expand=True, border=input_border())
    reg_plate = ft.TextField(label="Plate Number", value="NEA-7890", expand=True, border=input_border())
    reg_operator = ft.TextField(label="Cooperative / Operator", value="Bongabon Primemovers TSC", expand=True, border=input_border())
    reg_driver = ft.TextField(label="Default Assigned Driver", value="", expand=True, border=input_border())
    reg_conductor = ft.TextField(label="Default Assigned Conductor", value="", expand=True, border=input_border())
    reg_seated = ft.TextField(label="Max Seated Capacity", value="30", width=170, border=input_border())
    reg_standing = ft.TextField(label="Max Standing Capacity", value="15", width=170, border=input_border())

    fleet_table = ft.DataTable(
        width=float("inf"),
        heading_row_color=SOFT_PEACH,
        column_spacing=20,
        columns=[
            ft.DataColumn(ft.Text("Bus ID", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Plate #", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Operator", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Active Driver", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Active Conductor", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Ticketed Load", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Status", weight=ft.FontWeight.BOLD)),
        ],
        rows=[],
    )

    # =========================================================================
    # WORKSPACE 3: DAILY REMITTANCE & AUDITING
    # =========================================================================
    remittance_table = ft.DataTable(
        width=float("inf"),
        heading_row_color=SOFT_PEACH,
        column_spacing=20,
        columns=[
            ft.DataColumn(ft.Text("Bus ID", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Plate #", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Crew (Driver / Conductor)", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Tickets Issued", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Passengers Carried", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Total Fare Collected (PHP)", weight=ft.FontWeight.BOLD)),
        ],
        rows=[],
    )

    tickets_table = ft.DataTable(
        width=float("inf"),
        heading_row_color=SOFT_PEACH,
        column_spacing=16,
        columns=[
            ft.DataColumn(ft.Text("Ticket #", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Bus", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Origin -> Destination", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Distance", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Fare Type", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Pax", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Amount", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Trip State", weight=ft.FontWeight.BOLD)),
        ],
        rows=[],
    )

    # =========================================================================
    # WORKSPACE 4: PASSENGER FEEDBACK & INCIDENT RESOLUTION
    # =========================================================================
    feedback_table = ft.DataTable(
        width=float("inf"),
        heading_row_color=SOFT_PEACH,
        column_spacing=16,
        columns=[
            ft.DataColumn(ft.Text("ID", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Bus", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Commuter Name", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Concern Type", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Message / Details", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Status", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Action", weight=ft.FontWeight.BOLD)),
        ],
        rows=[],
    )

    # =========================================================================
    # CORE FUNCTIONS & LOGICAL DISPATCH HANDLERS
    # =========================================================================
    def render_visual_route_corridor():
        route_corridor_row.controls.clear()
        for s in stops_list:
            buses_here = [
                f"{b['bus_id']} ({b['current_passengers']} pax)"
                for b in buses_cache.values()
                if abs(float(b["lat"]) - float(s["lat"])) < 0.008 and abs(float(b["lng"]) - float(s["lng"])) < 0.008
            ]
            badge_text = f"At Stop: {', '.join(buses_here)}" if buses_here else "No bus currently at stop"
            route_corridor_row.controls.append(
                ft.Container(
                    padding=12,
                    bgcolor=SOFT_PEACH if buses_here else CARD_WHITE,
                    border_radius=12,
                    border=ft.Border.all(2.5 if buses_here else 1.5, ACCENT_MAUVE if buses_here else PASTEL_PINK),
                    width=310,
                    content=ft.Column(
                        spacing=4,
                        controls=[
                            ft.Text(s["stop_name"], weight=ft.FontWeight.BOLD, size=14, color=TEXT_DARK),
                            ft.Text(f"Municipality: {s['municipality']}", size=12, color=ACCENT_MAUVE),
                            ft.Text(
                                badge_text,
                                size=13,
                                weight=ft.FontWeight.BOLD,
                                color="#1b5e20" if buses_here else "#616161",
                            ),
                        ],
                    ),
                )
            )

    def populate_selected_bus(e=None):
        b = buses_cache.get(bus_selector.value)
        if b:
            shift_driver_input.value = b["driver_name"]
            shift_conductor_input.value = b["conductor_name"]
            live_occupancy_banner.content.value = (
                f"{b['bus_id']} ({b['plate_number']})   |   "
                f"Ticketed Onboard: {b['current_passengers']} pax   |   "
                f"Seats Available: {b['available_seats']} / {b['max_seated']}   |   "
                f"Standing: {b['standing_count']} / {b['max_standing']}   |   "
                f"Status: {b['status']}"
            )
        fetch_logs()
        page.update()

    if hasattr(bus_selector, "on_select"):
        bus_selector.on_select = populate_selected_bus
    else:
        bus_selector.on_change = populate_selected_bus

    def fetch_stops():
        res = requests.get(f"{base_url()}/api/stops", timeout=3)
        if res.status_code == 200:
            stops_list.clear()
            stops_cache.clear()
            terminal_dropdown.options.clear()
            remove_stop_dropdown.options.clear()

            # Automatically sort by geographic location (Bongabon -> Cabanatuan)
            all_stops = sorted(
                res.json(),
                key=lambda s: float(s["lat"]) + float(s["lng"]),
                reverse=True,
            )
            for s in all_stops:
                stops_list.append(s)
                # Clean location name + municipality (no "Stop 1:" prefix)
                label = f"{s['stop_name']} ({s['municipality']})"
                stops_cache[label] = s
                terminal_dropdown.options.append(ft.DropdownOption(label))
                remove_stop_dropdown.options.append(ft.DropdownOption(label))

            if stops_list:
                first_lbl = terminal_dropdown.options[0].key
                if not terminal_dropdown.value or terminal_dropdown.value not in stops_cache:
                    terminal_dropdown.value = first_lbl
                if not remove_stop_dropdown.value or remove_stop_dropdown.value not in stops_cache:
                    remove_stop_dropdown.value = first_lbl
            render_visual_route_corridor()

    def remove_selected_stop(e=None):
        lbl = remove_stop_dropdown.value
        target_stop = stops_cache.get(lbl)
        if not target_stop:
            set_status("Please select a stop to remove first.", "#b71c1c", "#ffcdd2")
            return
        if len(stops_list) <= 2:
            set_status("Cannot remove stop: Route must have at least 2 locations.", "#b71c1c", "#ffcdd2")
            return
        res = requests.delete(f"{base_url()}/api/stops/{target_stop['stop_id']}", timeout=3)
        if res.status_code == 200:
            set_status(f"🗑️ Removed '{target_stop['stop_name']}' and re-sorted route!", "#1b5e20", "#c8e6c9")
            remove_stop_dropdown.value = None
            sync_all()
        else:
            set_status(f"Failed to remove stop: {res.text}", "#b71c1c", "#ffcdd2")

    def fetch_buses():
        res = requests.get(f"{base_url()}/api/buses", timeout=3)
        if res.status_code == 200:
            buses_cache.clear()
            bus_selector.options.clear()
            fleet_table.rows.clear()
            for b in res.json():
                buses_cache[b["bus_id"]] = b
                bus_selector.options.append(ft.DropdownOption(b["bus_id"]))
                fleet_table.rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(b["bus_id"], weight=ft.FontWeight.BOLD, size=14)),
                            ft.DataCell(ft.Text(b["plate_number"], size=14)),
                            ft.DataCell(ft.Text(b["operator_name"], size=13)),
                            ft.DataCell(ft.Text(b["driver_name"], size=14)),
                            ft.DataCell(ft.Text(b["conductor_name"], size=14)),
                            ft.DataCell(
                                ft.Text(
                                    f"{b['current_passengers']} onboard (Max {b['max_seated']}+{b['max_standing']})",
                                    size=13,
                                )
                            ),
                            ft.DataCell(ft.Text(b["status"], weight=ft.FontWeight.BOLD, size=13)),
                        ]
                    )
                )
            render_visual_route_corridor()
            populate_selected_bus()

    def fetch_logs():
        res = requests.get(f"{base_url()}/api/logs", params={"bus_id": bus_selector.value, "limit": 8}, timeout=3)
        if res.status_code == 200:
            logs_table.rows.clear()
            for l in res.json():
                d = l["passenger_delta"]
                d_str = f"+{d}" if d > 0 else str(d)
                t_str = l["logged_at"].split("T")[-1][:8] if "T" in l["logged_at"] else l["logged_at"][-8:]
                logs_table.rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(t_str, size=13)),
                            ft.DataCell(ft.Text(l["bus_id"], weight=ft.FontWeight.BOLD, size=13)),
                            ft.DataCell(ft.Text(l.get("event_source", "System"), size=13)),
                            ft.DataCell(ft.Text(d_str, weight=ft.FontWeight.BOLD, size=13)),
                            ft.DataCell(ft.Text(str(l["current_passengers"]), size=13)),
                            ft.DataCell(ft.Text(str(l["available_seats"]), size=13)),
                            ft.DataCell(ft.Text(str(l["standing_count"]), size=13)),
                            ft.DataCell(ft.Text(l["status"], size=13)),
                        ]
                    )
                )

    def fetch_remittance_and_tickets():
        res_r = requests.get(f"{base_url()}/api/remittance", timeout=3)
        if res_r.status_code == 200:
            remittance_table.rows.clear()
            for r in res_r.json():
                remittance_table.rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(r["bus_id"], weight=ft.FontWeight.BOLD, size=14)),
                            ft.DataCell(ft.Text(r["plate_number"], size=14)),
                            ft.DataCell(ft.Text(f"{r['driver_name']} / {r['conductor_name']}", size=13)),
                            ft.DataCell(ft.Text(str(r["total_tickets"]), size=14)),
                            ft.DataCell(ft.Text(str(r["total_passengers_carried"]), size=14)),
                            ft.DataCell(
                                ft.Text(f"PHP {r['total_fare_collected']:.2f}", weight=ft.FontWeight.BOLD, size=14)
                            ),
                        ]
                    )
                )
        res_t = requests.get(f"{base_url()}/api/tickets", timeout=3)
        if res_t.status_code == 200:
            tickets_table.rows.clear()
            for t in res_t.json():
                tickets_table.rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(f"#{t['ticket_id']}", size=13)),
                            ft.DataCell(ft.Text(t["bus_id"], weight=ft.FontWeight.BOLD, size=13)),
                            ft.DataCell(ft.Text(f"{t['origin_stop']} -> {t['destination_stop']}", size=12)),
                            ft.DataCell(ft.Text(f"{t['distance_km']} km", size=13)),
                            ft.DataCell(ft.Text(t["passenger_type"], size=13)),
                            ft.DataCell(ft.Text(str(t["passenger_count"]), size=13)),
                            ft.DataCell(ft.Text(f"PHP {t['fare_amount']:.2f}", weight=ft.FontWeight.BOLD, size=13)),
                            ft.DataCell(ft.Text("Onboard" if t["is_onboard"] else "Alighted", size=13)),
                        ]
                    )
                )

    def resolve_fb(fb_id: int):
        requests.put(f"{base_url()}/api/feedback/{fb_id}/resolve", timeout=3)
        fetch_feedback()
        page.update()

    def fetch_feedback():
        res = requests.get(f"{base_url()}/api/feedback", timeout=3)
        if res.status_code == 200:
            feedback_table.rows.clear()
            for fb in res.json():
                done = fb["status"] == "Resolved"
                btn = (
                    ft.Text("Resolved", color="#1b5e20", weight=ft.FontWeight.BOLD, size=13)
                    if done
                    else ft.Button(
                        "Mark Resolved",
                        bgcolor=PASTEL_PINK,
                        color=TEXT_DARK,
                        on_click=lambda e, i=fb["feedback_id"]: resolve_fb(i),
                    )
                )
                feedback_table.rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(f"#{fb['feedback_id']}", size=13)),
                            ft.DataCell(ft.Text(fb["bus_id"], weight=ft.FontWeight.BOLD, size=13)),
                            ft.DataCell(ft.Text(fb["passenger_name"], size=13)),
                            ft.DataCell(ft.Text(fb["category"], size=13)),
                            ft.DataCell(ft.Text(fb["message"], size=13)),
                            ft.DataCell(ft.Text(fb["status"], weight=ft.FontWeight.BOLD, size=13)),
                            ft.DataCell(btn),
                        ]
                    )
                )

    def update_shift_crew(e=None):
        """Updates only the active shift Driver and Conductor for the selected bus."""
        b = buses_cache.get(bus_selector.value)
        if not b:
            return
        new_driver = (shift_driver_input.value or "").strip() or "Unassigned"
        new_conductor = (shift_conductor_input.value or "").strip() or "Unassigned"
        payload = {
            "bus_id": b["bus_id"],
            "plate_number": b["plate_number"],
            "operator_name": b["operator_name"],
            "driver_name": new_driver,
            "conductor_name": new_conductor,
            "route_name": OFFICIAL_ROUTE,
            "max_seated": int(b["max_seated"]),
            "max_standing": int(b["max_standing"]),
        }
        res = requests.post(f"{base_url()}/api/buses/register", json=payload, timeout=3)
        if res.status_code == 200:
            set_status(
                f"Crew Updated for {b['bus_id']}: Driver {new_driver} & Conductor {new_conductor}",
                "#1b5e20",
                "#c8e6c9",
            )
            fetch_buses()
            fetch_remittance_and_tickets()

    def dispatch_send_off_bus(e=None):
        """
        Properly dispatches (sends off) a mini-bus from the selected terminal:
        1. Saves the active Shift Driver and Conductor for this trip.
        2. Clears any completed/leftover onboard tickets from the previous trip.
        3. Positions the bus at the departure terminal with 0 ghost passengers.
        """
        b = buses_cache.get(bus_selector.value)
        if not b:
            return

        # 1. Update Shift Crew first
        update_shift_crew()

        # 2. Identify Departure Terminal
        lbl = terminal_dropdown.value
        target_stop = stops_cache.get(lbl)
        if not target_stop and stops_list:
            target_stop = stops_list[0]
        if not target_stop:
            return

        # 3. Clear any leftover onboard tickets from the finished trip so headcount is clean
        for s in stops_list:
            try:
                requests.post(
                    f"{base_url()}/api/tickets/dropoff",
                    json={"bus_id": b["bus_id"], "destination_stop_id": s["stop_id"]},
                    timeout=2,
                )
            except Exception:
                pass

        # 4. Dispatch bus from the terminal with 0 ghost passengers
        payload = {
            "bus_id": b["bus_id"],
            "route_name": OFFICIAL_ROUTE,
            "lat": float(target_stop["lat"]),
            "lng": float(target_stop["lng"]),
            "current_passengers": 0,
            "max_seated": int(b["max_seated"]),
            "max_standing": int(b["max_standing"]),
            "event_source": "Terminal Dispatch",
        }
        res = requests.post(f"{base_url()}/api/buses/update", json=payload, timeout=3)
        if res.status_code == 200:
            set_status(
                f" Dispatched {b['bus_id']} from {target_stop['stop_name']} "
                f"(Driver: {shift_driver_input.value}, Conductor: {shift_conductor_input.value}) — Ready for Conductor Ticketing!",
                "#1b5e20",
                "#c8e6c9",
            )
            fetch_buses()
            fetch_logs()
            fetch_remittance_and_tickets()
        page.update()

    def register_bus_click(e):
        payload = {
            "bus_id": reg_bus_id.value,
            "plate_number": reg_plate.value,
            "operator_name": reg_operator.value,
            "driver_name": reg_driver.value or "Unassigned",
            "conductor_name": reg_conductor.value or "Unassigned",
            "route_name": OFFICIAL_ROUTE,
            "max_seated": int(reg_seated.value or 30),
            "max_standing": int(reg_standing.value or 15),
        }
        res = requests.post(f"{base_url()}/api/buses/register", json=payload, timeout=3)
        if res.status_code == 200:
            set_status(f"Registered Mini-Bus {payload['bus_id']} ({payload['plate_number']}) to fleet!", "#1b5e20", "#c8e6c9")
            fetch_buses()

    def sync_all(e=None):
        try:
            fetch_stops()
            fetch_buses()
            fetch_logs()
            fetch_remittance_and_tickets()
            fetch_feedback()
            page.update()
        except Exception as ex:
            set_status(f"Sync Error: Cannot reach {base_url()} ({ex})", "#b71c1c", "#ffcdd2")

    # =========================================================================
    # WORKSPACE CONTAINERS & HIGHLIGHTED TAB NAVIGATION
    # =========================================================================
    view_dispatch = ft.Column(
        visible=True,
        spacing=14,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[
            ft.Container(
                padding=18,
                bgcolor=CARD_WHITE,
                border_radius=14,
                border=ft.Border.all(2, PASTEL_PINK),
                content=ft.Column(
                    spacing=10,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            controls=[
                                ft.Text(
                                    "Live Route Corridor (Bongabon - Palayan City - Cabanatuan)",
                                    size=18,
                                    weight=ft.FontWeight.BOLD,
                                    color=ACCENT_MAUVE,
                                ),
                                ft.Button(
                                    "Open Road-Snapped Live Map in Browser",
                                    icon=ft.Icons.MAP,
                                    height=42,
                                    bgcolor=ACCENT_MAUVE,
                                    color=CARD_WHITE,
                                    on_click=lambda _: webbrowser.open(f"{base_url()}/api/map"),
                                ),
                            ],
                        ),
                        route_corridor_row,
                    ],
                ),
            ),
            ft.Container(
                padding=18,
                bgcolor=CARD_WHITE,
                border_radius=14,
                border=ft.Border.all(2, PASTEL_PINK),
                content=ft.Column(
                    spacing=14,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        ft.Text(
                            "Terminal Bus Send-Off & Crew Assignment",
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=ACCENT_MAUVE,
                        ),
                        ft.Row(
                            [
                                bus_selector,
                                ft.Text(
                                    "Note: Passenger headcount is strictly controlled by Conductor E-Tickets (no manual ghost passengers).",
                                    size=13,
                                    italic=True,
                                    color=TEXT_DARK,
                                ),
                            ]
                        ),
                        live_occupancy_banner,
                        ft.Text(
                            "Step 2: Assign or Swap On-Duty Crew",
                            size=14,
                            weight=ft.FontWeight.BOLD,
                            color=ACCENT_MAUVE,
                        ),
                        ft.Row(
                            [
                                shift_driver_input,
                                shift_conductor_input,
                                ft.Button(
                                    "Save",
                                    icon=ft.Icons.BADGE,
                                    height=48,
                                    on_click=update_shift_crew,
                                    bgcolor=PASTEL_PINK,
                                    color=TEXT_DARK,
                                ),
                            ]
                        ),
                        ft.Divider(color=PASTEL_PINK),
                        ft.Text(
                            "Step 3: Official Terminal Send-Off (Starts New Trip & Clears Previous Trip Tickets)",
                            size=14,
                            weight=ft.FontWeight.BOLD,
                            color=ACCENT_MAUVE,
                        ),
                        ft.Row(
                            [
                                terminal_dropdown,
                                ft.Button(
                                    "Send Off Bus from Terminal (Start New Trip)",
                                    icon=ft.Icons.DIRECTIONS_BUS_FILLED,
                                    height=50,
                                    on_click=dispatch_send_off_bus,
                                    bgcolor=ACCENT_MAUVE,
                                    color=CARD_WHITE,
                                ), 
                            ]
                        ),
                        ft.Divider(color=PASTEL_PINK),
                        ft.Text(
                            "Route Stop Management (Remove Unneeded Stop)",
                            size=14,
                            weight=ft.FontWeight.BOLD,
                            color=ACCENT_MAUVE,
                        ),
                        ft.Row(
                            [
                                remove_stop_dropdown,
                                ft.Button(
                                    "🗑️ Remove Stop from Route",
                                    icon=ft.Icons.DELETE_FOREVER,
                                    height=48,
                                    on_click=remove_selected_stop,
                                    bgcolor="#ffcdd2",
                                    color="#b71c1c",
                                ),
                            ]
                        ),
                    ],
                ),
            ),
            table_card("Recent Dispatch, Conductor E-Ticketing & Automatic GPS Alighting Logs", logs_table),
        ],
    )

    view_fleet = ft.Column(
        visible=False,
        spacing=14,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[
            ft.Container(
                padding=18,
                bgcolor=CARD_WHITE,
                border_radius=14,
                border=ft.Border.all(2, PASTEL_PINK),
                content=ft.Column(
                    spacing=12,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        ft.Text(
                            "Register New Mini-Bus Unit or Edit Permanent Vehicle Specs",
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=ACCENT_MAUVE,
                        ),
                        ft.Row([reg_bus_id, reg_plate, reg_operator]),
                        ft.Row([reg_driver, reg_conductor, reg_seated, reg_standing]),
                        ft.Button(
                            "Save Permanent Mini-Bus Profile to Fleet",
                            icon=ft.Icons.DIRECTIONS_BUS,
                            height=48,
                            on_click=register_bus_click,
                            bgcolor=ACCENT_MAUVE,
                            color=CARD_WHITE,
                        ),
                    ],
                ),
            ),
            table_card("All Registered Cooperative Mini-Buses", fleet_table),
        ],
    )

    view_remittance = ft.Column(
        visible=False,
        spacing=14,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[
            table_card("Daily Fare Collection & Remittance Summary per Bus", remittance_table),
            table_card("All Conductor Tickets Issued Today", tickets_table),
        ],
    )

    view_feedback = ft.Column(
        visible=False,
        spacing=14,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[
            table_card("Commuter Reports, Lost & Found, and Feedback", feedback_table),
        ],
    )

    tab_btn_dispatch = ft.Button(
        "1. Terminal Send-Off & Crew",
        icon=ft.Icons.DEPARTURE_BOARD,
        height=48,
        expand=True,
        bgcolor=ACCENT_MAUVE,
        color=CARD_WHITE,
        on_click=lambda _: switch_tab("dispatch"),
    )
    tab_btn_fleet = ft.Button(
        "2. Permanent Fleet Vehicles",
        icon=ft.Icons.DIRECTIONS_BUS,
        height=48,
        expand=True,
        bgcolor=PASTEL_PINK,
        color=TEXT_DARK,
        on_click=lambda _: switch_tab("fleet"),
    )
    tab_btn_remittance = ft.Button(
        "3. Daily Fare Remittance",
        icon=ft.Icons.RECEIPT_LONG,
        height=48,
        expand=True,
        bgcolor=PASTEL_PINK,
        color=TEXT_DARK,
        on_click=lambda _: switch_tab("remittance"),
    )
    tab_btn_feedback = ft.Button(
        "4. Commuter Feedback",
        icon=ft.Icons.FEEDBACK,
        height=48,
        expand=True,
        bgcolor=PASTEL_PINK,
        color=TEXT_DARK,
        on_click=lambda _: switch_tab("feedback"),
    )

    def switch_tab(tab: str):
        view_dispatch.visible = tab == "dispatch"
        view_fleet.visible = tab == "fleet"
        view_remittance.visible = tab == "remittance"
        view_feedback.visible = tab == "feedback"

        for btn, key in [
            (tab_btn_dispatch, "dispatch"),
            (tab_btn_fleet, "fleet"),
            (tab_btn_remittance, "remittance"),
            (tab_btn_feedback, "feedback"),
        ]:
            btn.bgcolor = ACCENT_MAUVE if tab == key else PASTEL_PINK
            btn.color = CARD_WHITE if tab == key else TEXT_DARK

        sync_all()

    main_workspace = ft.Column(
        visible=False,
        spacing=14,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[
            ft.Row(
                spacing=10,
                controls=[tab_btn_dispatch, tab_btn_fleet, tab_btn_remittance, tab_btn_feedback],
            ),
            ft.Divider(color=ACCENT_MAUVE),
            view_dispatch,
            view_fleet,
            view_remittance,
            view_feedback,
        ],
    )

    btn_logout = ft.Button(
        "Log Out",
        icon=ft.Icons.LOGOUT,
        visible=False,
        height=44,
        bgcolor=SOFT_PEACH,
        color=TEXT_DARK,
        on_click=handle_logout,
    )

    page.add(
        ft.Container(
            padding=16,
            bgcolor=CARD_WHITE,
            border_radius=14,
            border=ft.Border.all(2, PASTEL_PINK),
            content=ft.Column(
                spacing=10,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Column(
                                spacing=2,
                                controls=[
                                    ft.Text(
                                        "BusWatch",
                                        size=22,
                                        weight=ft.FontWeight.BOLD,
                                        color=ACCENT_MAUVE,
                                    ),
                                    ft.Text(
                                        "Centralized Dispatcher Console  |  Bongabon - Palayan City - Cabanatuan Terminal",
                                        size=13,
                                        color=TEXT_DARK,
                                    ),
                                ],
                            ),
                            ft.Row(
                                spacing=8,
                                controls=[
                                    ft.IconButton(
                                        icon=ft.Icons.SETTINGS,
                                        tooltip="Server Address Settings",
                                        icon_color=ACCENT_MAUVE,
                                        on_click=toggle_server_ip,
                                    ),
                                    ft.Button(
                                        "Refresh Data",
                                        icon=ft.Icons.REFRESH,
                                        height=44,
                                        on_click=sync_all,
                                        bgcolor=PASTEL_PINK,
                                        color=TEXT_DARK,
                                    ),
                                    btn_logout,
                                ],
                            ),
                        ],
                    ),
                    ft.Row([server_ip]),
                ],
            ),
        ),
        status_banner,
        auth_card,
        main_workspace,
    )


if __name__ == "__main__":
    if hasattr(ft, "run"):
        ft.run(main)
    else:
        ft.app(target=main)