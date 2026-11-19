import threading
import time
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
AUTO_REFRESH_SECONDS = 5


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
    sync_lock = threading.Lock()
    stop_auto_refresh = threading.Event()
    auto_refresh_enabled = {"value": True}

    server_ip = ft.TextField(
        label="Server Address (Change IP here if network changes)",
        value="http://192.168.1.8:8000",
        expand=True,
        visible=False,
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
            "Welcome! Please log in with your account to begin.",
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
        raw = (server_ip.value or "").strip().rstrip("/")
        if raw and not raw.startswith(("http://", "https://")):
            raw = "http://" + raw
        return raw

    # =========================================================================
    # BUILT-IN CONFIRMATION CARD (WORKS ACROSS ALL FLET VERSIONS)
    # =========================================================================
    pending_confirm = {"callback": None, "from_auth": False}
    confirm_title = ft.Text("", size=20, weight=ft.FontWeight.BOLD, color=ACCENT_MAUVE)
    confirm_message = ft.Text("", size=15, color=TEXT_DARK)

    def close_confirm_card(e=None):
        confirm_card.visible = False
        if pending_confirm["from_auth"]:
            auth_card.visible = True
        else:
            main_workspace.visible = True
        page.update()

    def proceed_confirm_card(e=None):
        cb = pending_confirm["callback"]
        confirm_card.visible = False
        if pending_confirm["from_auth"]:
            auth_card.visible = True
        else:
            main_workspace.visible = True
        page.update()
        if cb:
            cb()

    confirm_card = ft.Container(
        visible=False,
        padding=28,
        bgcolor=CARD_WHITE,
        border_radius=16,
        border=ft.Border.all(2.5, ACCENT_MAUVE),
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=16,
            controls=[
                confirm_title,
                confirm_message,
                ft.Row(
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=14,
                    controls=[
                        ft.Button(
                            "Cancel",
                            icon=ft.Icons.CLOSE,
                            height=46,
                            bgcolor=SOFT_PEACH,
                            color=TEXT_DARK,
                            on_click=close_confirm_card,
                        ),
                        ft.Button(
                            "Yes, Proceed",
                            icon=ft.Icons.CHECK_CIRCLE,
                            height=46,
                            bgcolor=ACCENT_MAUVE,
                            color=CARD_WHITE,
                            on_click=proceed_confirm_card,
                        ),
                    ],
                ),
            ],
        ),
    )

    def show_confirm_dialog(title_text: str, message_text: str, on_confirm_callback):
        pending_confirm["callback"] = on_confirm_callback
        pending_confirm["from_auth"] = auth_card.visible
        confirm_title.value = title_text
        confirm_message.value = message_text
        auth_card.visible = False
        main_workspace.visible = False
        confirm_card.visible = True
        page.update()

    # =========================================================================
    # SEPARATED AUTHENTICATION VIEW (LOG IN vs. CREATE ACCOUNT)
    # =========================================================================
    auth_title = ft.Text("Log In", size=24, weight=ft.FontWeight.BOLD, color=ACCENT_MAUVE)
    auth_subtitle = ft.Text(
        "Enter your cooperative username and password below:",
        size=14,
        color=TEXT_DARK,
    )

    auth_username = ft.TextField(
        label="Username",
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
            auth_title.value = "Create New Account"
            auth_subtitle.value = "Fill in all boxes below to register a new dispatcher account."
            btn_mode_login.bgcolor = BG_CREAM
            btn_mode_login.color = TEXT_DARK
            btn_mode_signup.bgcolor = ACCENT_MAUVE
            btn_mode_signup.color = CARD_WHITE
            btn_submit_login.visible = False
            btn_submit_signup.visible = True
        else:
            auth_title.value = "Log In"
            auth_subtitle.value = "Enter your cooperative username and password below."
            btn_mode_login.bgcolor = ACCENT_MAUVE
            btn_mode_login.color = CARD_WHITE
            btn_mode_signup.bgcolor = BG_CREAM
            btn_mode_signup.color = TEXT_DARK
            btn_submit_login.visible = True
            btn_submit_signup.visible = False
        page.update()

    def set_logged_in_ui(is_logged_in: bool):
        auth_card.visible = not is_logged_in
        main_workspace.visible = is_logged_in
        btn_refresh.visible = is_logged_in
        btn_logout.visible = is_logged_in

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
                set_logged_in_ui(True)
                set_status(
                    f"Logged in as: {data['full_name']} (@{data['username']})",
                    "#1b5e20",
                    "#c8e6c9",
                )
                sync_all(refresh_crew_inputs=True)
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

        def execute_signup():
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
                    set_logged_in_ui(True)
                    set_status(
                        f"Account Created! Welcome, {data['full_name']} (@{data['username']})",
                        "#1b5e20",
                        "#c8e6c9",
                    )
                    sync_all(refresh_crew_inputs=True)
                else:
                    err_msg = (
                        res.json().get("detail", "Sign-Up failed")
                        if "application/json" in res.headers.get("content-type", "")
                        else res.text
                    )
                    set_status(f"Sign-Up Error: {err_msg}", "#b71c1c", "#ffcdd2")
            except Exception as ex:
                set_status(f"Cannot connect to server ({base_url()}). Check Server IP above. ({ex})", "#b71c1c", "#ffcdd2")

        show_confirm_dialog(
            "Confirm Account Creation",
            f"Are you sure you want to register this account '{uname}'?",
            execute_signup,
        )

    def handle_logout(e=None):
        def execute_logout():
            current_user.update({"user_id": None, "full_name": "Guest", "username": ""})
            auth_password.value = ""
            set_logged_in_ui(False)
            set_status("You have logged out safely.", TEXT_DARK, SOFT_PEACH)

        show_confirm_dialog(
            "Confirm Log Out",
            "Are you sure you want to log out?",
            execute_logout,
        )

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
        "Log In",
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
    en_route_banner = ft.Container(
        padding=10,
        bgcolor=BG_CREAM,
        border_radius=10,
        border=ft.Border.all(1.5, PASTEL_PINK),
        content=ft.Text(
            "En Route on Highway: Checking live fleet positions...",
            size=13,
            weight=ft.FontWeight.BOLD,
            color=TEXT_DARK,
        ),
    )

    bus_selector = ft.Dropdown(
        label="Step 1: Select Active Mini-Bus Unit",
        value=None,
        options=[],
        width=280,
    )

    live_occupancy_banner = ft.Container(
        padding=12,
        bgcolor=SOFT_PEACH,
        border_radius=10,
        border=ft.Border.all(1.5, ACCENT_MAUVE),
        content=ft.Text("", size=14, weight=ft.FontWeight.BOLD, color=TEXT_DARK),
    )

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

    terminal_dropdown = ft.Dropdown(
        label="Step 3: Select Departure Terminal for Send-Off (Terminals Only)",
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
            ft.DataColumn(ft.Text("Action", weight=ft.FontWeight.BOLD)),
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
    def find_nearest_stop_name(lat: float, lng: float) -> str:
        if not stops_list:
            return "Highway"
        nearest = min(
            stops_list,
            key=lambda s: (float(s["lat"]) - lat) ** 2 + (float(s["lng"]) - lng) ** 2,
        )
        return nearest["stop_name"]

    def render_visual_route_corridor():
        route_corridor_row.controls.clear()
        stationed_bus_ids = set()

        active_buses = [b for b in buses_cache.values() if b.get("status") != "Inactive"]

        for s in stops_list:
            buses_here = []
            for b in active_buses:
                if (
                    abs(float(b["lat"]) - float(s["lat"])) < 0.008
                    and abs(float(b["lng"]) - float(s["lng"])) < 0.008
                ):
                    buses_here.append(f"{b['bus_id']} ({b['current_passengers']} pax)")
                    stationed_bus_ids.add(b["bus_id"])

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

        # Show active buses currently driving between stops so they never appear to disappear
        en_route_buses = [b for b in active_buses if b["bus_id"] not in stationed_bus_ids]
        if not active_buses:
            en_route_banner.content.value = "En Route on Highway: No active mini-buses currently on the route."
            en_route_banner.content.color = "#b71c1c"
        elif en_route_buses:
            parts = [
                f"{b['bus_id']} ({b['current_passengers']} pax • near {find_nearest_stop_name(float(b['lat']), float(b['lng']))})"
                for b in en_route_buses
            ]
            en_route_banner.content.value = "En Route on Highway: " + "   |   ".join(parts)
            en_route_banner.content.color = "#1b5e20"
        else:
            en_route_banner.content.value = "En Route on Highway: All active mini-buses are currently at stations."
            en_route_banner.content.color = TEXT_DARK

    def populate_selected_bus(e=None, refresh_crew_inputs: bool = True):
        b = buses_cache.get(bus_selector.value) if bus_selector.value else None
        if b and b.get("status") != "Inactive":
            if refresh_crew_inputs:
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
        else:
            if refresh_crew_inputs:
                shift_driver_input.value = ""
                shift_conductor_input.value = ""
            live_occupancy_banner.content.value = (
                "No active mini-buses available. Set a unit to Active in Tab 2 (Permanent Fleet Vehicles)."
            )
            logs_table.rows.clear()
        page.update()

    if hasattr(bus_selector, "on_select"):
        bus_selector.on_select = lambda e: populate_selected_bus(e, refresh_crew_inputs=True)
    else:
        bus_selector.on_change = lambda e: populate_selected_bus(e, refresh_crew_inputs=True)

    def fetch_stops():
        res = requests.get(f"{base_url()}/api/stops", timeout=3)
        if res.status_code == 200:
            stops_list.clear()
            stops_cache.clear()
            terminal_dropdown.options.clear()
            remove_stop_dropdown.options.clear()

            all_stops = sorted(
                res.json(),
                key=lambda s: float(s["lat"]) + float(s["lng"]),
                reverse=True,
            )
            for s in all_stops:
                stops_list.append(s)
                label = f"{s['stop_name']} ({s['municipality']})"
                stops_cache[label] = s
                remove_stop_dropdown.options.append(ft.DropdownOption(label))

            # Restrict Departure Terminal Send-Off strictly to the route's start & end terminals
            terminal_stops = []
            if len(all_stops) >= 1:
                terminal_stops.append(all_stops[0])
            if len(all_stops) >= 2:
                terminal_stops.append(all_stops[-1])

            terminal_labels = []
            for ts in terminal_stops:
                t_label = f"{ts['stop_name']} ({ts['municipality']})"
                terminal_labels.append(t_label)
                terminal_dropdown.options.append(ft.DropdownOption(t_label))

            if terminal_labels:
                if not terminal_dropdown.value or terminal_dropdown.value not in terminal_labels:
                    terminal_dropdown.value = terminal_labels[0]
            else:
                terminal_dropdown.value = None

            if stops_list:
                first_remove_lbl = remove_stop_dropdown.options[0].key
                if not remove_stop_dropdown.value or remove_stop_dropdown.value not in stops_cache:
                    remove_stop_dropdown.value = first_remove_lbl
            else:
                remove_stop_dropdown.value = None

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

        def execute_remove_stop():
            try:
                res = requests.delete(f"{base_url()}/api/stops/{target_stop['stop_id']}", timeout=3)
                if res.status_code == 200:
                    set_status(f"Removed '{target_stop['stop_name']}' and re-sorted route!", "#1b5e20", "#c8e6c9")
                    remove_stop_dropdown.value = None
                    sync_all(refresh_crew_inputs=False)
                else:
                    set_status(f"Failed to remove stop: {res.text}", "#b71c1c", "#ffcdd2")
            except Exception as ex:
                set_status(f"Network error removing stop: {ex}", "#b71c1c", "#ffcdd2")

        show_confirm_dialog(
            "Confirm Stop Removal",
            f"Are you sure you want to remove '{target_stop['stop_name']}' from the route?",
            execute_remove_stop,
        )

    def toggle_bus_status(bus_id: str, current_status: str):
        if not bus_id:
            set_status("Please select a bus unit first.", "#b71c1c", "#ffcdd2")
            return

        is_currently_inactive = current_status == "Inactive"
        new_status = "Active" if is_currently_inactive else "Inactive"
        prompt_msg = (
            f"Are you sure you want to mark {bus_id} as ACTIVE and return it to the live map and route?"
            if is_currently_inactive
            else f"Are you sure you want to mark {bus_id} as INACTIVE (no driver / under repair)? "
                 f"This will remove {bus_id} from the live map, corridor, and mobile apps."
        )

        def execute_status_change():
            try:
                res = requests.post(
                    f"{base_url()}/api/buses/status",
                    json={"bus_id": bus_id, "status": new_status},
                    timeout=3,
                )
                if res.status_code == 200:
                    set_status(
                        f"Bus {bus_id} status changed to {new_status}.",
                        "#1b5e20" if new_status == "Active" else "#b71c1c",
                        "#c8e6c9" if new_status == "Active" else "#ffcdd2",
                    )
                    sync_all(refresh_crew_inputs=True)
                else:
                    set_status(f"Failed to update status: {res.text}", "#b71c1c", "#ffcdd2")
            except Exception as ex:
                set_status(f"Error updating bus status: {ex}", "#b71c1c", "#ffcdd2")

        show_confirm_dialog(
            f"Change {bus_id} Status to {new_status}",
            prompt_msg,
            execute_status_change,
        )

    def fetch_buses(refresh_crew_inputs: bool = True):
        res = requests.get(
            f"{base_url()}/api/buses",
            params={"include_inactive": "true"},
            timeout=3,
        )
        if res.status_code == 200:
            prev_selected = bus_selector.value
            buses_cache.clear()
            bus_selector.options.clear()
            fleet_table.rows.clear()
            for b in res.json():
                buses_cache[b["bus_id"]] = b
                is_inactive = b["status"] == "Inactive"

                if not is_inactive:
                    bus_selector.options.append(ft.DropdownOption(b["bus_id"]))

                status_btn = ft.Button(
                    "Set Active" if is_inactive else "Set Inactive",
                    height=36,
                    bgcolor="#c8e6c9" if is_inactive else "#ffcdd2",
                    color="#1b5e20" if is_inactive else "#b71c1c",
                    on_click=lambda e, bid=b["bus_id"], st=b["status"]: toggle_bus_status(bid, st),
                )

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
                            ft.DataCell(
                                ft.Text(
                                    b["status"],
                                    weight=ft.FontWeight.BOLD,
                                    size=13,
                                    color="#b71c1c" if is_inactive else TEXT_DARK,
                                )
                            ),
                            ft.DataCell(status_btn),
                        ]
                    )
                )

            active_keys = [opt.key for opt in bus_selector.options]
            if not active_keys:
                bus_selector.value = None
            elif not bus_selector.value or bus_selector.value not in active_keys:
                bus_selector.value = active_keys[0]

            selection_changed = bus_selector.value != prev_selected
            render_visual_route_corridor()
            populate_selected_bus(refresh_crew_inputs=refresh_crew_inputs or selection_changed)

    def fetch_logs():
        if not bus_selector.value:
            logs_table.rows.clear()
            return
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
        def execute_resolve():
            try:
                res = requests.put(f"{base_url()}/api/feedback/{fb_id}/resolve", timeout=3)
                if res.status_code == 200:
                    set_status(f"Feedback #{fb_id} marked as Resolved.", "#1b5e20", "#c8e6c9")
                    fetch_feedback()
                    page.update()
                else:
                    set_status(f"Failed to resolve Feedback #{fb_id}: {res.text}", "#b71c1c", "#ffcdd2")
            except Exception as ex:
                set_status(f"Network error resolving feedback: {ex}", "#b71c1c", "#ffcdd2")

        show_confirm_dialog(
            "Confirm Feedback Resolution",
            f"Are you sure you want to mark Feedback #{fb_id} as Resolved?",
            execute_resolve,
        )

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

    def save_shift_crew_request(b: dict):
        new_driver = (shift_driver_input.value or "").strip() or b.get("driver_name") or "Unassigned"
        new_conductor = (shift_conductor_input.value or "").strip() or b.get("conductor_name") or "Unassigned"
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
        return requests.post(f"{base_url()}/api/buses/register", json=payload, timeout=3), new_driver, new_conductor

    def update_shift_crew(e=None):
        """Updates only the active shift Driver and Conductor for the selected bus."""
        b = buses_cache.get(bus_selector.value) if bus_selector.value else None
        if not b:
            set_status("Please select an active mini-bus first.", "#b71c1c", "#ffcdd2")
            return

        new_driver = (shift_driver_input.value or "").strip()
        new_conductor = (shift_conductor_input.value or "").strip()
        if not new_driver or not new_conductor:
            set_status("Please enter both Driver and Conductor names before saving.", "#b71c1c", "#ffcdd2")
            return

        def execute_crew_update():
            try:
                res, saved_driver, saved_conductor = save_shift_crew_request(b)
                if res.status_code == 200:
                    set_status(
                        f"Crew Updated for {b['bus_id']}: Driver {saved_driver} & Conductor {saved_conductor}",
                        "#1b5e20",
                        "#c8e6c9",
                    )
                    sync_all(refresh_crew_inputs=True)
                else:
                    set_status(f"Failed to update crew: {res.text}", "#b71c1c", "#ffcdd2")
            except Exception as ex:
                set_status(f"Network error updating crew: {ex}", "#b71c1c", "#ffcdd2")

        show_confirm_dialog(
            "Confirm Crew Assignment",
            f"Save on-duty crew for {b['bus_id']} (Driver: {new_driver}, Conductor: {new_conductor})?",
            execute_crew_update,
        )

    def dispatch_send_off_bus(e=None):
        b = buses_cache.get(bus_selector.value) if bus_selector.value else None
        if not b:
            set_status("Please select an active mini-bus first.", "#b71c1c", "#ffcdd2")
            return

        lbl = terminal_dropdown.value
        target_stop = stops_cache.get(lbl)
        if not target_stop and stops_list:
            target_stop = stops_list[0]
        if not target_stop:
            set_status("No departure terminal available.", "#b71c1c", "#ffcdd2")
            return

        onboard_now = int(b.get("current_passengers", 0))
        warning_line = (
            f"\n\nWARNING: {b['bus_id']} currently has {onboard_now} passenger(s) onboard. "
            "Sending it off will clear all onboard tickets and reset passenger count to 0."
            if onboard_now > 0
            else "\n\nThis will position the bus at the departure terminal with 0 passengers."
        )

        def execute_send_off():
            try:
                _, saved_driver, saved_conductor = save_shift_crew_request(b)

                for s in stops_list:
                    try:
                        requests.post(
                            f"{base_url()}/api/tickets/dropoff",
                            json={"bus_id": b["bus_id"], "destination_stop_id": s["stop_id"]},
                            timeout=2,
                        )
                    except Exception:
                        pass

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
                        f"Dispatched {b['bus_id']} from {target_stop['stop_name']} "
                        f"(Driver: {saved_driver}, Conductor: {saved_conductor}) — Ready for Conductor Ticketing!",
                        "#1b5e20",
                        "#c8e6c9",
                    )
                    sync_all(refresh_crew_inputs=True)
                else:
                    set_status(f"Failed to dispatch bus: {res.text}", "#b71c1c", "#ffcdd2")
            except Exception as ex:
                set_status(f"Network error sending off bus: {ex}", "#b71c1c", "#ffcdd2")

        show_confirm_dialog(
            "Confirm Terminal Send-Off",
            f"Are you sure you want to send off {b['bus_id']} from {target_stop['stop_name']} and start a new trip?{warning_line}",
            execute_send_off,
        )

    def register_bus_click(e):
        bus_id_val = (reg_bus_id.value or "").strip()
        plate_val = (reg_plate.value or "").strip()
        if not bus_id_val or not plate_val:
            set_status("Bus Unit Number and Plate Number are required.", "#b71c1c", "#ffcdd2")
            return

        try:
            seated_val = int((reg_seated.value or "").strip())
            standing_val = int((reg_standing.value or "").strip())
            if seated_val < 1 or standing_val < 0:
                raise ValueError()
        except ValueError:
            set_status(
                "Invalid capacity: Max Seated must be at least 1 and Max Standing must be 0 or more.",
                "#b71c1c",
                "#ffcdd2",
            )
            return

        def execute_register_bus():
            try:
                payload = {
                    "bus_id": bus_id_val,
                    "plate_number": plate_val,
                    "operator_name": (reg_operator.value or "").strip() or "Bongabon Primemovers TSC",
                    "driver_name": (reg_driver.value or "").strip() or "Unassigned",
                    "conductor_name": (reg_conductor.value or "").strip() or "Unassigned",
                    "route_name": OFFICIAL_ROUTE,
                    "max_seated": seated_val,
                    "max_standing": standing_val,
                }
                res = requests.post(f"{base_url()}/api/buses/register", json=payload, timeout=3)
                if res.status_code == 200:
                    set_status(
                        f"Registered Mini-Bus {payload['bus_id']} ({payload['plate_number']}) to fleet!",
                        "#1b5e20",
                        "#c8e6c9",
                    )
                    sync_all(refresh_crew_inputs=False)
                else:
                    set_status(f"Failed to register mini-bus: {res.text}", "#b71c1c", "#ffcdd2")
            except Exception as ex:
                set_status(f"Network error registering mini-bus: {ex}", "#b71c1c", "#ffcdd2")

        show_confirm_dialog(
            "Confirm Save Mini-Bus Profile",
            f"Are you sure you want to save Mini-Bus {bus_id_val} ({plate_val}) with {seated_val} seated + {standing_val} standing capacity?",
            execute_register_bus,
        )

    def sync_all(e=None, refresh_crew_inputs: bool = True, silent: bool = False):
        if current_user["user_id"] is None:
            return
        if not sync_lock.acquire(blocking=False):
            return
        try:
            fetch_stops()
            fetch_buses(refresh_crew_inputs=refresh_crew_inputs)
            fetch_remittance_and_tickets()
            fetch_feedback()
            page.update()
        except Exception as ex:
            if not silent:
                set_status(f"Sync Error: Cannot reach {base_url()} ({ex})", "#b71c1c", "#ffcdd2")
        finally:
            sync_lock.release()

    def auto_refresh_worker():
        while not stop_auto_refresh.wait(AUTO_REFRESH_SECONDS):
            if (
                auto_refresh_enabled["value"]
                and current_user["user_id"] is not None
                and not confirm_card.visible
            ):
                try:
                    sync_all(refresh_crew_inputs=False, silent=True)
                except Exception:
                    pass

    def handle_disconnect(e=None):
        stop_auto_refresh.set()

    page.on_disconnect = handle_disconnect
    threading.Thread(target=auto_refresh_worker, daemon=True).start()

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
                            wrap=True,
                            controls=[
                                ft.Text(
                                    "Live Route Corridor (Auto-Refreshes Every 5s)",
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
                        en_route_banner,
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
                            ],
                            wrap=True,
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
                                    "Save Crew",
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
                            "Route Stop Management",
                            size=14,
                            weight=ft.FontWeight.BOLD,
                            color=ACCENT_MAUVE,
                        ),
                        ft.Text(
                            "Need to add a new stop along the highway? Click 'Open Road-Snapped Live Map in Browser' above to pin and save a new stop.",
                            size=13,
                            color=TEXT_DARK,
                        ),
                        ft.Row(
                            [
                                remove_stop_dropdown,
                                ft.Button(
                                    "Remove Stop from Route",
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

        sync_all(refresh_crew_inputs=False)

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

    btn_refresh = ft.Button(
        "Refresh Data",
        icon=ft.Icons.REFRESH,
        visible=False,
        height=44,
        on_click=lambda e: sync_all(e, refresh_crew_inputs=True),
        bgcolor=PASTEL_PINK,
        color=TEXT_DARK,
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
                                    btn_refresh,
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
        confirm_card,
        auth_card,
        main_workspace,
    )


if __name__ == "__main__":
    if hasattr(ft, "run"):
        ft.run(main)
    else:
        ft.app(target=main)