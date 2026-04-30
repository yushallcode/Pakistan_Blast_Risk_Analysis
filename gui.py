# ── Standard library ─────────────────────────────────────────
import os
import sys

# ── GUI libraries (built into Python) ────────────────────────
import tkinter as tk
from tkinter import ttk          # nicer-looking widgets
from tkinter import messagebox   # popup dialogs

# ── Matplotlib embedded inside tkinter ───────────────────────
import matplotlib
matplotlib.use("TkAgg")          # tells matplotlib to draw inside tkinter
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ── Our own project files ─────────────────────────────────────
import data_utils      as du
import spatial_engine  as se
import risk_calculator as rc


# =============================================================
# GLOBAL STATE
# All shared data lives here as plain module-level variables.
# No classes needed — we just pass these variables to functions.
# =============================================================

CSV_PATH     = "suicide-blasts-dataset.csv"

# These get filled during startup and are then used everywhere
g_df         = None    # the clean DataFrame
g_qt         = None    # the Quadtree root node
g_year       = 2017    # reference year (user can change this)
g_selected   = None    # the leaf node the user last clicked

# Next available row_idx for newly inserted incidents.
# Set once in main() from the dataset's highest existing ID.
# do_create() reads AND increments this so every new incident
# gets a unique ID without re-scanning the whole tree.
g_next_id    = 0

# Colours used throughout the GUI
C_BG         = "#0f1923"    # dark background
C_SURFACE    = "#162130"    # card / panel background
C_BORDER     = "#1e3348"    # subtle border colour
C_ACCENT     = "#00c8ff"    # bright blue highlight
C_TEXT       = "#c8dde8"    # main text
C_MUTED      = "#4a6070"    # secondary text
C_RED        = "#e74c3c"    # danger / delete
C_GREEN      = "#27ae60"    # success / safe
C_ORANGE     = "#e67e22"    # warning


# =============================================================
# HELPER — make_label
# =============================================================
def make_label(parent, text, fg=None, font=None, **kwargs):
    """
    Create a tkinter Label with our dark theme.
    """
    # Pull 'bg' out of kwargs (or use C_SURFACE if not supplied).
    # .pop() removes the key from the dict so it won't appear again
    # inside **kwargs when we spread it into tk.Label below.
    bg = kwargs.pop("bg", C_SURFACE)

    return tk.Label(
        parent,
        text = text,
        bg   = bg,               # exactly ONE bg value now
        fg   = fg   or C_TEXT,
        font = font or ("Consolas", 9),
        **kwargs                 # remaining keys (e.g. textvariable, justify)
    )


def make_button(parent, text, command, colour=None, width=14):
    """Create a flat-looking button with our colour scheme."""
    btn = tk.Button(
        parent,
        text             = text,
        command          = command,
        bg               = colour or C_ACCENT,
        fg               = "#000000" if (colour == C_ACCENT or colour is None) else "#ffffff",
        font             = ("Consolas", 9, "bold"),
        relief           = "flat",
        activebackground = "#009fcc",
        activeforeground = "#000000",
        padx             = 10,
        pady             = 4,
        width            = width,
        cursor           = "hand2",
    )
    return btn


def make_entry(parent, width=18, textvariable=None):
    """Create a text entry field with our dark theme."""
    e = tk.Entry(
        parent,
        width                 = width,
        bg                    = "#0d1a26",
        fg                    = C_TEXT,
        insertbackground       = C_ACCENT,
        relief                = "flat",
        font                  = ("Consolas", 9),
        bd                    = 1,
        highlightthickness    = 1,
        highlightcolor         = C_ACCENT,
        highlightbackground   = C_BORDER,
    )
    if textvariable:
        e.config(textvariable=textvariable)
    return e


def score_to_colour(score):
    """Return the hex colour string for a given 0-100 risk score."""
    _, colour = rc.get_risk_band(score)
    return colour


def forecast_score(base_score, trend, years_ahead):
    """
    Project a risk score forward by years_ahead years.
    Uses the same linear trend logic as risk_calculator.
    """
    if trend == "ESCALATING":
        delta = +4
    elif trend == "DE-ESCALATING":
        delta = -5
    elif trend == "STABLE":
        delta = +1
    else:
        delta = -3    # NO DATA — decays slowly

    projected = base_score + delta * years_ahead
    # clamp to 0-100
    projected = max(0, min(100, projected))
    return projected


# =============================================================
# MAP DRAWING
# This function draws the Quadtree on a matplotlib Figure.
# It is called every time the map needs to be refreshed.
# =============================================================

def draw_quadtree_map(ax, mode="risk", highlight_node=None,
                      forecast_year=None):
    """
    Draw all Quadtree leaf cells onto the given matplotlib Axes.

    mode="risk"     — colour by current risk score
    mode="forecast" — colour by projected score for forecast_year
    mode="trend"    — colour by rising / falling / stable trend

    highlight_node  — if set, that cell gets a white border

    This function is the LIVE map — it redraws from scratch every
    time a CRUD operation changes the Quadtree.
    """
    ax.clear()
    ax.set_facecolor("#040c14")
    ax.set_xlim(se.PAK_LON_MIN, se.PAK_LON_MAX)
    ax.set_ylim(se.PAK_LAT_MIN, se.PAK_LAT_MAX)
    ax.tick_params(colors=C_MUTED, labelsize=7)
    for spine in ax.spines.values():
        spine.set_edgecolor(C_BORDER)
    ax.set_xlabel("Longitude", color=C_MUTED, fontsize=8)
    ax.set_ylabel("Latitude",  color=C_MUTED, fontsize=8)

    ref_year   = forecast_year if forecast_year else g_year
    all_leaves = se.get_all_leaf_nodes(g_qt)

    for leaf in all_leaves:
        # Width and height of this cell in degrees
        w = leaf["lon_max"] - leaf["lon_min"]
        h = leaf["lat_max"] - leaf["lat_min"]

        n_incidents = len(leaf["incidents"])

        # ── Decide the fill colour based on the mode ──────────
        if mode == "forecast" and forecast_year:
            base   = rc.calculate_node_risk(leaf, g_year)
            trend  = rc.get_trend(leaf, g_year)["trend"]
            score  = forecast_score(base, trend, forecast_year - g_year)
            colour = score_to_colour(score)
            alpha  = 0.15 + (score / 100) * 0.70 if n_incidents > 0 else 0.08

        elif mode == "trend":
            trend_info = rc.get_trend(leaf, g_year)
            colour = trend_info["colour"]
            alpha  = 0.70 if n_incidents > 0 else 0.12

        else:    # default: "risk"
            score  = rc.calculate_node_risk(leaf, ref_year)
            colour = score_to_colour(score)
            alpha  = 0.15 + (score / 100) * 0.70 if n_incidents > 0 else 0.08

        # ── Highlight the selected cell ────────────────────────
        is_selected = (
            highlight_node is not None and
            leaf["cell_id"] == highlight_node["cell_id"]
        )
        edge_colour = "white" if is_selected else C_BORDER
        edge_width  = 2.0     if is_selected else 0.3

        # ── Draw the rectangle ────────────────────────────────
        rect = mpatches.FancyBboxPatch(
            (leaf["lon_min"], leaf["lat_min"]),
            w, h,
            boxstyle   = "square,pad=0",
            facecolor  = colour,
            edgecolor  = edge_colour,
            linewidth  = edge_width,
            alpha      = alpha,
            zorder     = 2,
        )
        ax.add_patch(rect)

    # ── Draw incident dots (small yellow dots) ─────────────────
    all_incidents = []
    for leaf in all_leaves:
        all_incidents.extend(leaf["incidents"])

    if all_incidents:
        lons = [inc["lon"] for inc in all_incidents]
        lats = [inc["lat"] for inc in all_incidents]
        ax.scatter(lons, lats,
                   c="#ffe57a", s=5, alpha=0.55,
                   zorder=4, marker=".", linewidths=0)

    # ── Title ──────────────────────────────────────────────────
    total = len(all_incidents)
    if mode == "forecast" and forecast_year:
        title = f"Forecast: {forecast_year}  |  {total} incidents in tree"
    elif mode == "trend":
        title = f"Trend Direction  |  {total} incidents"
    else:
        title = f"Risk Map — {ref_year}  |  {total} incidents"

    ax.set_title(title, color=C_TEXT, fontsize=9, fontweight="bold", pad=8)


# =============================================================
# SECTION 1 — TAB: MAP
# Live Quadtree map. Click on the map to read a cell.
# =============================================================

def build_map_tab(notebook):
    """
    Build the MAP tab and return (frame, refresh_map).
    Contains:
      - A large matplotlib canvas showing the live Quadtree
      - A sidebar showing the risk profile of the clicked cell
      - A year slider to change the reference year
    """
    frame = tk.Frame(notebook, bg=C_BG)
    frame.columnconfigure(0, weight=1)
    frame.columnconfigure(1, weight=0)
    frame.rowconfigure(0, weight=1)

    # ── Left side: the map canvas ─────────────────────────────
    map_frame = tk.Frame(frame, bg=C_BG)
    map_frame.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)

    fig_map, ax_map = plt.subplots(figsize=(7, 6))
    fig_map.patch.set_facecolor(C_BG)

    canvas_map = FigureCanvasTkAgg(fig_map, master=map_frame)
    canvas_map.get_tk_widget().pack(fill="both", expand=True)

    # Controls row below the map
    ctrl_frame = tk.Frame(map_frame, bg=C_BG)
    ctrl_frame.pack(fill="x", pady=(4, 0))

    make_label(ctrl_frame, "  Year:", bg=C_BG).pack(side="left")

    # Reference year slider
    year_var = tk.IntVar(value=g_year)

    # We define on_year_change before year_lbl but use year_lbl lazily
    # (Python closures capture variables by reference, so year_lbl is
    # accessible at the moment the callback fires, not when it is defined)
    def on_year_change(val):
        global g_year
        g_year = int(float(val))
        year_lbl.config(text=str(g_year))
        refresh_map()

    year_slider = tk.Scale(
        ctrl_frame,
        from_              = 1995,
        to                 = 2017,
        orient             = "horizontal",
        variable           = year_var,
        command            = on_year_change,
        bg                 = C_BG,
        fg                 = C_TEXT,
        troughcolor        = C_SURFACE,
        highlightthickness = 0,
        showvalue          = 0,
        length             = 200,
    )
    year_slider.pack(side="left", padx=6)

    year_lbl = make_label(ctrl_frame, str(g_year),
                          fg=C_ACCENT, font=("Consolas", 10, "bold"),
                          bg=C_BG)
    year_lbl.pack(side="left")

    # Mode toggle buttons
    mode_var = tk.StringVar(value="risk")

    def set_mode(m):
        mode_var.set(m)
        refresh_map()

    for label_text, mode_val in [("Risk", "risk"), ("Trend", "trend")]:
        b = tk.Button(
            ctrl_frame, text=label_text,
            command=lambda m=mode_val: set_mode(m),
            bg=C_SURFACE, fg=C_TEXT, font=("Consolas", 8),
            relief="flat", padx=8, pady=2, cursor="hand2",
            bd=1, highlightbackground=C_BORDER
        )
        b.pack(side="left", padx=3)

    # ── Right side: cell info panel ───────────────────────────
    info_frame = tk.Frame(frame, bg=C_SURFACE, width=220)
    info_frame.grid(row=0, column=1, sticky="ns", padx=(0, 10), pady=10)
    info_frame.pack_propagate(False)

    make_label(info_frame, "CELL INFO",
               fg=C_ACCENT, font=("Consolas", 9, "bold")).pack(pady=(12, 4))

    ttk.Separator(info_frame, orient="horizontal").pack(fill="x", padx=10)

    # StringVars — updated whenever the user clicks a cell on the map
    info_vars = {
        "cell_id":   tk.StringVar(value="—"),
        "score":     tk.StringVar(value="—"),
        "level":     tk.StringVar(value="—"),
        "incidents": tk.StringVar(value="—"),
        "killed":    tk.StringVar(value="—"),
        "injured":   tk.StringVar(value="—"),
        "depth":     tk.StringVar(value="—"),
        "area":      tk.StringVar(value="—"),
        "trend":     tk.StringVar(value="—"),
        "provinces": tk.StringVar(value="—"),
        "years":     tk.StringVar(value="—"),
        "density":   tk.StringVar(value="—"),
        "recency":   tk.StringVar(value="—"),
        "severity":  tk.StringVar(value="—"),
    }

    # Helper: add one key-value row to the info panel
    def add_info_row(parent, label_text, var, colour=None):
        row = tk.Frame(parent, bg=C_SURFACE)
        row.pack(fill="x", padx=10, pady=2)
        make_label(row, label_text + ":",
                   fg=C_MUTED, font=("Consolas", 8),
                   bg=C_SURFACE).pack(side="left")
        # 'textvariable' goes through **kwargs safely after the bg fix
        make_label(row, "",
                   fg=colour or C_TEXT, font=("Consolas", 8, "bold"),
                   textvariable=var, bg=C_SURFACE).pack(side="right")

    add_info_row(info_frame, "Cell ID",   info_vars["cell_id"])
    add_info_row(info_frame, "Score",     info_vars["score"],     C_ACCENT)
    add_info_row(info_frame, "Level",     info_vars["level"],     C_RED)
    add_info_row(info_frame, "Trend",     info_vars["trend"],     C_ORANGE)
    ttk.Separator(info_frame, orient="horizontal").pack(fill="x", padx=10, pady=4)
    add_info_row(info_frame, "Incidents", info_vars["incidents"])
    add_info_row(info_frame, "Killed",    info_vars["killed"],    C_RED)
    add_info_row(info_frame, "Injured",   info_vars["injured"],   C_ORANGE)
    add_info_row(info_frame, "Years",     info_vars["years"])
    add_info_row(info_frame, "Province",  info_vars["provinces"])
    ttk.Separator(info_frame, orient="horizontal").pack(fill="x", padx=10, pady=4)
    make_label(info_frame, "SCORE BREAKDOWN",
               fg=C_MUTED, font=("Consolas", 7, "bold")).pack()
    add_info_row(info_frame, "Density",   info_vars["density"])
    add_info_row(info_frame, "Depth",     info_vars["depth"])
    add_info_row(info_frame, "Recency",   info_vars["recency"])
    add_info_row(info_frame, "Severity",  info_vars["severity"])
    add_info_row(info_frame, "Area km2",  info_vars["area"])

    make_label(info_frame, "\nClick map to read a cell",
               fg=C_MUTED, font=("Consolas", 7, "italic"),
               bg=C_SURFACE).pack(pady=(8, 0))

    # ── Refresh the map canvas ─────────────────────────────────
    def refresh_map():
        draw_quadtree_map(ax_map,
                          mode=mode_var.get(),
                          highlight_node=g_selected)
        fig_map.tight_layout(pad=1.0)
        canvas_map.draw()

    # ── Click handler: pixel -> lat/lon -> find cell ───────────
    def on_map_click(event):
        global g_selected

        # Only handle clicks that land inside the plot axes area
        if event.inaxes != ax_map:
            return

        clicked_lon = event.xdata
        clicked_lat = event.ydata

        # Ask the Quadtree which leaf cell owns this GPS point
        leaf = se.find_leaf_node(g_qt, clicked_lat, clicked_lon)
        if leaf is None:
            return

        g_selected = leaf

        # Build the full risk profile for this leaf
        profile = rc.get_risk_profile(leaf, g_year)
        trend   = rc.get_trend(leaf, g_year)

        # Fill every StringVar so the labels in the panel update
        info_vars["cell_id"].set(str(profile["cell_id"]))
        info_vars["score"].set(str(profile["risk_score"]) + " / 100")
        info_vars["level"].set(profile["risk_label"])
        info_vars["trend"].set(trend["trend"])
        info_vars["incidents"].set(str(profile["total_incidents"]))
        info_vars["killed"].set(str(profile["total_killed"]))
        info_vars["injured"].set(str(profile["total_injured"]))

        yr_f = profile["year_first"] or "?"
        yr_l = profile["year_last"]  or "?"
        info_vars["years"].set(f"{yr_f} – {yr_l}")

        # Most common province in this cell
        if profile["provinces"]:
            top_prov = max(profile["provinces"],
                           key=profile["provinces"].get)
        else:
            top_prov = "—"
        info_vars["provinces"].set(top_prov)

        info_vars["density"].set(str(profile["score_density"])  + " pts")
        info_vars["depth"].set(str(profile["score_depth"])      + " pts")
        info_vars["recency"].set(str(profile["score_recency"])  + " pts")
        info_vars["severity"].set(str(profile["score_severity"]) + " pts")
        info_vars["area"].set(str(profile["area_km2"]))

        # Redraw so the selected cell gets a white highlight border
        refresh_map()

    # Connect the matplotlib click event to our handler
    fig_map.canvas.mpl_connect("button_press_event", on_map_click)

    # Store the refresh function on the frame so other tabs can call it
    frame.refresh_map = refresh_map

    # Initial draw
    refresh_map()

    return frame, refresh_map


# =============================================================
# SECTION 2 — TAB: CRUD
# Add, Update, Delete incidents. Map refreshes after each op.
# =============================================================

def build_crud_tab(notebook, refresh_map_fn):
    """
    Build the CRUD tab.
    Three columns:
      CREATE — form to add a new incident
      UPDATE — change label/year of an existing incident by ID
      DELETE — remove an incident by ID
    After every successful operation the map refreshes.
    """
    frame = tk.Frame(notebook, bg=C_BG)

    make_label(frame, "  CRUD OPERATIONS  —  Live Quadtree",
               fg=C_ACCENT, font=("Consolas", 11, "bold"),
               bg=C_BG).pack(anchor="w", pady=(12, 4), padx=14)

    # ── Status bar ────────────────────────────────────────────
    status_var = tk.StringVar(value="Ready.")
    status_bar = tk.Label(
        frame, textvariable=status_var,
        bg=C_SURFACE, fg=C_GREEN,
        font=("Consolas", 8), anchor="w", padx=10
    )
    status_bar.pack(fill="x", padx=10, pady=(0, 6))

    def set_status(msg, colour=C_GREEN):
        status_var.set("  " + msg)
        status_bar.config(fg=colour)

    # Container for the three column cards
    cols = tk.Frame(frame, bg=C_BG)
    cols.pack(fill="both", expand=True, padx=10, pady=4)

    # Helper: make a titled column card
    def make_card(parent, title, colour):
        card = tk.Frame(parent, bg=C_SURFACE, bd=0,
                        highlightthickness=1,
                        highlightbackground=colour)
        card.pack(side="left", fill="both", expand=True,
                  padx=6, pady=4)
        tk.Label(card, text=title, bg=colour,
                 fg="#000000" if colour == C_ACCENT else "#ffffff",
                 font=("Consolas", 9, "bold"),
                 padx=8, pady=4).pack(fill="x")
        return card

    # ===========================================================
    # CREATE COLUMN
    # ===========================================================
    create_card = make_card(cols, "  1 — CREATE  (Add Incident)", C_ACCENT)

    fields_create = {}
    create_form_data = [
        ("Latitude",  "23.5 – 37.5", "33.72"),
        ("Longitude", "60.5 – 77.5", "73.07"),
        ("Year",      "e.g. 2015",   "2015"),
        ("Province",  "e.g. KPK",    "KPK"),
        ("Killed",    "number",       "0"),
        ("Injured",   "number",       "0"),
    ]

    for field_name, hint, default_val in create_form_data:
        row = tk.Frame(create_card, bg=C_SURFACE)
        row.pack(fill="x", padx=8, pady=3)
        make_label(row, field_name,
                   bg=C_SURFACE, font=("Consolas", 8)).pack(anchor="w")
        var = tk.StringVar(value=default_val)
        make_entry(row, textvariable=var).pack(fill="x")
        fields_create[field_name] = var

    # Province shortcut dropdown
    row = tk.Frame(create_card, bg=C_SURFACE)
    row.pack(fill="x", padx=8, pady=3)
    make_label(row, "Quick Province",
               bg=C_SURFACE, font=("Consolas", 8)).pack(anchor="w")

    prov_options = {
        "KPK (Peshawar)":      ("33.76", "71.51", "KPK"),
        "FATA":                ("33.54", "70.65", "FATA"),
        "Punjab (Lahore)":     ("32.36", "73.37", "Punjab"),
        "Sindh (Karachi)":     ("25.46", "67.27", "Sindh"),
        "Balochistan":         ("30.00", "67.05", "Balochistan"),
        "Capital (Islamabad)": ("33.72", "73.07", "Capital"),
        "AJK":                 ("34.07", "73.62", "AJK"),
    }

    prov_var = tk.StringVar(value="— pick —")
    prov_menu = ttk.Combobox(row, textvariable=prov_var,
                              values=list(prov_options.keys()),
                              state="readonly", width=22)
    prov_menu.pack(fill="x")

    def on_prov_pick(event):
        chosen = prov_var.get()
        if chosen in prov_options:
            lat_s, lon_s, prov_s = prov_options[chosen]
            fields_create["Latitude"].set(lat_s)
            fields_create["Longitude"].set(lon_s)
            fields_create["Province"].set(prov_s)

    prov_menu.bind("<<ComboboxSelected>>", on_prov_pick)

    # CREATE button callback
    def do_create():
        """
        Validate the form fields and if valid, insert a new incident into
        the Quadtree. Then refresh the map and incident list.
        """
        global g_next_id   # we are going to assign to it, so declare it

        # Read and validate the form fields
        try:
            lat     = float(fields_create["Latitude"].get())
            lon     = float(fields_create["Longitude"].get())
            year    = int(fields_create["Year"].get())
            label   = fields_create["Province"].get().strip()
            killed  = float(fields_create["Killed"].get())
            injured = float(fields_create["Injured"].get())
        except ValueError:
            set_status("Fill all fields with valid numbers.", C_RED)
            return

        # Boundary check — must be inside Pakistan
        if not (23.5 <= lat <= 37.5 and 60.5 <= lon <= 77.5):
            set_status("Lat/Lon outside Pakistan.", C_RED)
            return

        # Use the pre-computed next ID and advance it
        new_id     = g_next_id
        g_next_id += 1

        # Insert into Quadtree
        se.insert_incident(g_qt, lat, lon, new_id,
                           year=year, label=label,
                           killed=killed, injured=injured)

        # Find the cell it landed in so we can tell the user
        leaf_node = se.find_leaf_node(g_qt, lat, lon)
        cell_id   = leaf_node["cell_id"] if leaf_node else "?"

        set_status(f"Created ID {new_id}  →  Cell {cell_id}", C_GREEN)
        refresh_map_fn()
        refresh_incident_list()

    make_button(create_card, "  + Add Incident",
                do_create, colour=C_ACCENT).pack(pady=8)

    # ===========================================================
    # UPDATE COLUMN
    # ===========================================================
    update_card = make_card(cols, "  2 — UPDATE  (Edit Incident)", C_ORANGE)

    fields_update = {}
    update_form_data = [
        ("Row ID",    "incident row_idx"),
        ("New Label", "new province name"),
        ("New Year",  "new year (blank=keep)"),
    ]

    for field_name, hint in update_form_data:
        row = tk.Frame(update_card, bg=C_SURFACE)
        row.pack(fill="x", padx=8, pady=3)
        make_label(row, field_name,
                   bg=C_SURFACE, font=("Consolas", 8)).pack(anchor="w")
        make_label(row, hint,
                   fg=C_MUTED, bg=C_SURFACE,
                   font=("Consolas", 7)).pack(anchor="w")
        var = tk.StringVar()
        make_entry(row, textvariable=var).pack(fill="x")
        fields_update[field_name] = var

    def do_update():
        row_id_str = fields_update["Row ID"].get().strip()
        new_label  = fields_update["New Label"].get().strip()
        new_year_s = fields_update["New Year"].get().strip()

        if not row_id_str:
            set_status("Enter a Row ID.", C_RED)
            return
        try:
            row_id = int(row_id_str)
        except ValueError:
            set_status("Row ID must be a whole number.", C_RED)
            return

        new_year = None
        if new_year_s:
            try:
                new_year = int(new_year_s)
            except ValueError:
                set_status("Year must be a whole number.", C_RED)
                return

        final_label = new_label if new_label else None
        success = se.update_incident(g_qt, row_id,
                                     new_year=new_year,
                                     new_label=final_label)
        if success:
            set_status(f"Updated ID {row_id}  ✓", C_GREEN)
            refresh_map_fn()
            refresh_incident_list()
        else:
            set_status(f"ID {row_id} not found.", C_RED)

    make_button(update_card, "  ✎ Update",
                do_update, colour=C_ORANGE).pack(pady=8)

    # ===========================================================
    # DELETE COLUMN
    # ===========================================================
    delete_card = make_card(cols, "  3 — DELETE  (Remove Incident)", C_RED)

    row = tk.Frame(delete_card, bg=C_SURFACE)
    row.pack(fill="x", padx=8, pady=3)
    make_label(row, "Row ID to Delete",
               bg=C_SURFACE, font=("Consolas", 8)).pack(anchor="w")
    make_label(row, "exact row_idx number",
               fg=C_MUTED, bg=C_SURFACE,
               font=("Consolas", 7)).pack(anchor="w")
    delete_id_var = tk.StringVar()
    make_entry(row, textvariable=delete_id_var).pack(fill="x")

    def do_delete():
        id_str = delete_id_var.get().strip()
        if not id_str:
            set_status("Enter a Row ID to delete.", C_RED)
            return
        try:
            row_id = int(id_str)
        except ValueError:
            set_status("Row ID must be a whole number.", C_RED)
            return

        # Ask for confirmation with a popup dialog
        confirmed = messagebox.askyesno(
            "Confirm Delete",
            f"Delete incident with Row ID {row_id}?\nThis cannot be undone."
        )
        if not confirmed:
            set_status("Delete cancelled.", C_MUTED)
            return

        before  = se.count_incidents(g_qt)
        success = se.delete_incident(g_qt, row_id)
        after   = se.count_incidents(g_qt)

        if success:
            set_status(
                f"Deleted ID {row_id}  |  "
                f"{before} → {after} incidents", C_GREEN
            )
            delete_id_var.set("")
            refresh_map_fn()
            refresh_incident_list()
        else:
            set_status(f"ID {row_id} not found.", C_RED)

    make_button(delete_card, "  ✕ Delete",
                do_delete, colour=C_RED).pack(pady=8)

    # ── Separator ─────────────────────────────────────────────
    ttk.Separator(frame, orient="horizontal").pack(fill="x", padx=10, pady=4)

    # ===========================================================
    # READ — Incident list at the bottom
    # ===========================================================
    make_label(frame, "  READ — Incident List  (click column header to sort)",
               fg=C_ACCENT, font=("Consolas", 9, "bold"),
               bg=C_BG).pack(anchor="w", padx=14, pady=(4, 2))

    # Search bar
    search_frame = tk.Frame(frame, bg=C_BG)
    search_frame.pack(fill="x", padx=10, pady=(0, 4))
    make_label(search_frame, "  Search:", bg=C_BG).pack(side="left")
    search_var = tk.StringVar()
    make_entry(search_frame, width=25, textvariable=search_var).pack(side="left", padx=4)

    # Treeview table
    tree_frame = tk.Frame(frame, bg=C_BG)
    tree_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    cols_def = ("ID", "Year", "Province", "Lat", "Lon",
                "Killed", "Injured", "Cell")

    tree = ttk.Treeview(tree_frame, columns=cols_def,
                         show="headings", height=8)

    # Style the Treeview to match our dark theme
    style = ttk.Style()
    style.configure("Treeview",
                     background      = "#0d1a26",
                     foreground      = C_TEXT,
                     fieldbackground = "#0d1a26",
                     rowheight       = 20,
                     font            = ("Consolas", 8))
    style.configure("Treeview.Heading",
                     background = C_SURFACE,
                     foreground = C_ACCENT,
                     font       = ("Consolas", 8, "bold"))
    style.map("Treeview", background=[("selected", C_BORDER)])

    col_widths = {"ID": 50, "Year": 55, "Province": 90,
                  "Lat": 70, "Lon": 70,
                  "Killed": 55, "Injured": 60, "Cell": 45}

    # Sort state — shared dict so sort_tree and refresh_incident_list
    # can both read and write it
    sort_state = {"col": "ID", "reverse": False}

    def sort_tree(col):
        # Toggle direction if clicking the same column again
        if sort_state["col"] == col:
            sort_state["reverse"] = not sort_state["reverse"]
        else:
            sort_state["reverse"] = False
        sort_state["col"] = col
        refresh_incident_list()

    for col in cols_def:
        tree.heading(col, text=col,
                     command=lambda c=col: sort_tree(c))
        tree.column(col, width=col_widths.get(col, 70), anchor="center")

    scrollbar = ttk.Scrollbar(tree_frame, orient="vertical",
                               command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    tree.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    # Clicking a row auto-fills the delete and update ID fields
    def on_tree_select(event):
        selected = tree.focus()
        if selected:
            values = tree.item(selected, "values")
            if values:
                delete_id_var.set(values[0])
                fields_update["Row ID"].set(values[0])

    tree.bind("<<TreeviewSelect>>", on_tree_select)

    def refresh_incident_list(event=None):
        """Rebuild the incident table from the current Quadtree state."""
        all_leaves    = se.get_all_leaf_nodes(g_qt)
        all_incidents = []
        for leaf in all_leaves:
            for inc in leaf["incidents"]:
                all_incidents.append({
                    "id":       inc["row_idx"],
                    "year":     inc.get("year") or "?",
                    "province": inc.get("label") or "?",
                    "lat":      round(inc["lat"], 3),
                    "lon":      round(inc["lon"], 3),
                    "killed":   int(inc.get("killed") or 0),
                    "injured":  int(inc.get("injured") or 0),
                    "cell":     leaf["cell_id"],
                })

        # Apply search filter
        query = search_var.get().strip().lower()
        if query:
            all_incidents = [
                i for i in all_incidents
                if query in str(i["province"]).lower()
                or query in str(i["year"])
                or query in str(i["id"])
            ]

        # Sort by the chosen column
        col_map = {
            "ID": "id", "Year": "year", "Province": "province",
            "Lat": "lat", "Lon": "lon",
            "Killed": "killed", "Injured": "injured", "Cell": "cell"
        }
        sort_key = col_map.get(sort_state["col"], "id")
        try:
            all_incidents.sort(key=lambda x: x[sort_key],
                               reverse=sort_state["reverse"])
        except TypeError:
            pass    # mixed types (e.g. int vs "?") — skip sort

        # Clear old rows and repopulate
        for row in tree.get_children():
            tree.delete(row)
        for inc in all_incidents:
            tree.insert("", "end", values=(
                inc["id"], inc["year"], inc["province"],
                inc["lat"], inc["lon"],
                inc["killed"], inc["injured"], inc["cell"]
            ))

    # Update the list whenever the user types in the search box
    search_var.trace_add("write", lambda *a: refresh_incident_list())

    # Initial population
    refresh_incident_list()

    frame.refresh_incident_list = refresh_incident_list
    return frame


# =============================================================
# SECTION 3 — TAB: FORECAST
# Projects risk scores 1-5 years into the future.
# =============================================================

def build_forecast_tab(notebook):
    """
    Build the FORECAST tab.
    Shows the Quadtree map coloured by projected risk for a
    future year chosen by a slider (base+1 to base+5 years).
    Also shows a table of top predicted hotspots.
    """
    frame = tk.Frame(notebook, bg=C_BG)
    frame.columnconfigure(0, weight=1)
    frame.columnconfigure(1, weight=0)
    frame.rowconfigure(0, weight=1)

    # ── Left: forecast map ────────────────────────────────────
    left = tk.Frame(frame, bg=C_BG)
    left.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)

    fig_fc, ax_fc = plt.subplots(figsize=(7, 5.5))
    fig_fc.patch.set_facecolor(C_BG)

    canvas_fc = FigureCanvasTkAgg(fig_fc, master=left)
    canvas_fc.get_tk_widget().pack(fill="both", expand=True)

    # Controls below the forecast map
    ctrl = tk.Frame(left, bg=C_BG)
    ctrl.pack(fill="x", pady=(6, 0))

    make_label(ctrl, "  Forecast Year:", bg=C_BG).pack(side="left")

    fc_year_var = tk.IntVar(value=g_year + 1)
    fc_lbl = make_label(ctrl,
                         f"{g_year + 1}  (+1 year)",
                         fg=C_ACCENT, font=("Consolas", 9, "bold"),
                         bg=C_BG)
    fc_lbl.pack(side="right", padx=8)

    def on_fc_slider(val):
        """Called by the Scale whenever its value changes."""
        yr    = int(float(val))
        delta = yr - g_year
        fc_lbl.config(
            text=f"{yr}  (+{delta} year{'s' if delta != 1 else ''})"
        )
        fc_year_var.set(yr)
        redraw_forecast(yr)

    fc_slider = tk.Scale(
        ctrl,
        from_              = g_year + 1,
        to                 = g_year + 5,
        orient             = "horizontal",
        command            = on_fc_slider,   # fires on every value change
        bg                 = C_BG,
        fg                 = C_TEXT,
        troughcolor        = C_SURFACE,
        highlightthickness = 0,
        showvalue          = 0,
        length             = 260,
    )
    fc_slider.pack(side="left", padx=6)

    for plus in [1, 2, 3, 4, 5]:
        yr = g_year + plus
        tk.Button(
            ctrl, text=f"+{plus}y",
            command=lambda y=yr: fc_slider.set(y),  # ← fixed
            bg=C_SURFACE, fg=C_TEXT, font=("Consolas", 7),
            relief="flat", padx=4, cursor="hand2"
        ).pack(side="left", padx=1)

    # ── Right: hotspot prediction table ───────────────────────
    right = tk.Frame(frame, bg=C_SURFACE, width=240)
    right.grid(row=0, column=1, sticky="ns", padx=(0, 10), pady=10)
    right.pack_propagate(False)

    make_label(right, "TOP PREDICTED HOTSPOTS",
               fg=C_ACCENT, font=("Consolas", 8, "bold")).pack(pady=(10, 4))
    make_label(right, "(next 5 years)",
               fg=C_MUTED, font=("Consolas", 7)).pack()
    ttk.Separator(right, orient="horizontal").pack(fill="x", padx=6, pady=4)

    hotspot_frame = tk.Frame(right, bg=C_SURFACE)
    hotspot_frame.pack(fill="both", expand=True, padx=4)

    # Trend colour legend
    legend_frame = tk.Frame(right, bg=C_SURFACE)
    legend_frame.pack(fill="x", padx=8, pady=8)
    make_label(legend_frame, "TREND LEGEND",
               fg=C_MUTED, font=("Consolas", 7, "bold"),
               bg=C_SURFACE).pack(anchor="w")

    for colour, label_text in [
        ("#8b0000", "ESCALATING — rising"),
        ("#e67e22", "DE-ESCALATING"),
        ("#f1c40f", "STABLE"),
        ("#27ae60", "NO DATA / SAFE"),
    ]:
        row_f = tk.Frame(legend_frame, bg=C_SURFACE)
        row_f.pack(fill="x", pady=1)
        tk.Label(row_f, text="■", fg=colour, bg=C_SURFACE,
                 font=("Consolas", 9)).pack(side="left")
        make_label(row_f, " " + label_text,
                   fg=C_TEXT, font=("Consolas", 7),
                   bg=C_SURFACE).pack(side="left")

    ttk.Separator(right, orient="horizontal").pack(fill="x", padx=6, pady=4)
    explainer = (
        "HOW IT WORKS:\n\n"
        "1. Score every cell now\n"
        "2. Detect trend from 3\n"
        "   windows of 3 years\n"
        "3. ESCALATING → +4/yr\n"
        "   DE-ESC      → -5/yr\n"
        "   STABLE       → +1/yr\n"
        "4. Project score forward"
    )
    make_label(right, explainer,
               fg=C_MUTED, font=("Consolas", 7),
               justify="left", bg=C_SURFACE).pack(anchor="w", padx=8)

    def redraw_forecast(target_year):
        """Redraw the forecast map and hotspot list for target_year."""
        draw_quadtree_map(ax_fc, mode="forecast",
                          forecast_year=target_year)
        # Faint year watermark in the background
        ax_fc.text(
            (se.PAK_LON_MIN + se.PAK_LON_MAX) / 2,
            (se.PAK_LAT_MIN + se.PAK_LAT_MAX) / 2,
            str(target_year),
            fontsize=52, color="white", alpha=0.06,
            ha="center", va="center", fontweight="bold",
            transform=ax_fc.transData
        )
        fig_fc.tight_layout(pad=1.0)
        canvas_fc.draw()

        # Rebuild the hotspot ranking table
        for widget in hotspot_frame.winfo_children():
            widget.destroy()

        all_leaves = se.get_all_leaf_nodes(g_qt)
        fc_cells   = []
        for leaf in all_leaves:
            if len(leaf["incidents"]) == 0:
                continue
            base_score = rc.calculate_node_risk(leaf, g_year)
            trend_info = rc.get_trend(leaf, g_year)
            trend      = trend_info["trend"]
            fc_s       = forecast_score(base_score, trend,
                                        target_year - g_year)
            fc_cells.append((fc_s, base_score, trend, leaf))

        fc_cells.sort(key=lambda x: x[0], reverse=True)
        top_cells = fc_cells[:8]

        # Header row for the table
        hdr = tk.Frame(hotspot_frame, bg=C_BORDER)
        hdr.pack(fill="x", pady=(0, 2))
        for txt, w in [("Cell", 40), ("Now", 38), ("Proj", 38), ("Trend", 80)]:
            tk.Label(hdr, text=txt, bg=C_BORDER, fg=C_MUTED,
                     font=("Consolas", 7, "bold"),
                     width=w // 7).pack(side="left", padx=2)

        for fc_s, base_s, trend, leaf in top_cells:
            _, band_colour = rc.get_risk_band(fc_s)

            row_w = tk.Frame(hotspot_frame, bg=C_SURFACE)
            row_w.pack(fill="x", pady=1)

            tk.Label(row_w, text=str(leaf["cell_id"]),
                     bg=C_SURFACE, fg=C_TEXT,
                     font=("Consolas", 8), width=4).pack(side="left")
            tk.Label(row_w, text=str(base_s),
                     bg=C_SURFACE, fg=C_MUTED,
                     font=("Consolas", 8), width=4).pack(side="left")
            tk.Label(row_w, text=str(fc_s),
                     bg=C_SURFACE, fg=band_colour,
                     font=("Consolas", 8, "bold"), width=4).pack(side="left")

            trend_short = {
                "ESCALATING":    "↑ ESC",
                "DE-ESCALATING": "↓ D-E",
                "STABLE":        "→ STA",
                "NO DATA":       "· N/D",
            }.get(trend, trend[:5])
            trend_col = {
                "ESCALATING":    "#8b0000",
                "DE-ESCALATING": C_ORANGE,
                "STABLE":        "#f1c40f",
                "NO DATA":       C_GREEN,
            }.get(trend, C_MUTED)
            tk.Label(row_w, text=trend_short,
                     bg=C_SURFACE, fg=trend_col,
                     font=("Consolas", 8)).pack(side="left", padx=4)

    # Initial draw for +1 year
    redraw_forecast(g_year + 1)

    return frame


# =============================================================
# SECTION 4 — TAB: STATS
# Summary numbers and top-10 risk table.
# =============================================================

def build_stats_tab(notebook):
    """
    Build the STATS tab.
    Shows:
      - KPI numbers (total incidents, killed, cells etc.)
      - Risk band distribution bars
      - Top-10 highest-risk cells table
    """
    frame = tk.Frame(notebook, bg=C_BG)

    make_label(frame, "  SYSTEM STATISTICS",
               fg=C_ACCENT, font=("Consolas", 11, "bold"),
               bg=C_BG).pack(anchor="w", pady=(12, 6), padx=14)

    # ── KPI row ───────────────────────────────────────────────
    kpi_frame = tk.Frame(frame, bg=C_BG)
    kpi_frame.pack(fill="x", padx=10, pady=4)

    kpi_vars = {}

    def add_kpi(parent, title, var_key, colour):
        card = tk.Frame(parent, bg=C_SURFACE,
                        highlightthickness=1,
                        highlightbackground=colour)
        card.pack(side="left", expand=True, fill="x", padx=4)
        tk.Label(card, text=title, bg=C_SURFACE, fg=C_MUTED,
                 font=("Consolas", 7, "bold")).pack(pady=(6, 0))
        var = tk.StringVar(value="—")
        kpi_vars[var_key] = var
        tk.Label(card, textvariable=var, bg=C_SURFACE, fg=colour,
                 font=("Consolas", 14, "bold")).pack(pady=(0, 6))

    add_kpi(kpi_frame, "INCIDENTS",      "incidents", C_ACCENT)
    add_kpi(kpi_frame, "KILLED",         "killed",    C_RED)
    add_kpi(kpi_frame, "INJURED",        "injured",   C_ORANGE)
    add_kpi(kpi_frame, "CRITICAL CELLS", "critical",  "#8b0000")
    add_kpi(kpi_frame, "LEAF CELLS",     "cells",     C_MUTED)

    # ── Risk band distribution bars ───────────────────────────
    ttk.Separator(frame, orient="horizontal").pack(fill="x", padx=10, pady=6)
    make_label(frame, "  Risk Band Distribution",
               fg=C_ACCENT, font=("Consolas", 9, "bold"),
               bg=C_BG).pack(anchor="w", padx=14)

    band_frame = tk.Frame(frame, bg=C_BG)
    band_frame.pack(fill="x", padx=14, pady=4)

    band_vars = {}
    band_configs = [
        ("CRITICAL", "#8b0000"),
        ("HIGH",     C_RED),
        ("MEDIUM",   C_ORANGE),
        ("LOW",      "#f1c40f"),
        ("MINIMAL",  C_GREEN),
    ]
    for band_name, colour in band_configs:
        row_b = tk.Frame(band_frame, bg=C_BG)
        row_b.pack(fill="x", pady=2)
        make_label(row_b, f"{band_name:<10}",
                   fg=colour, font=("Consolas", 8, "bold"),
                   bg=C_BG).pack(side="left")
        bar_canvas = tk.Canvas(row_b, height=14, bg=C_SURFACE,
                               highlightthickness=0)
        bar_canvas.pack(side="left", fill="x", expand=True, padx=6)
        count_lbl = make_label(row_b, "0",
                               fg=colour, font=("Consolas", 8),
                               bg=C_BG)
        count_lbl.pack(side="right")
        band_vars[band_name] = (bar_canvas, count_lbl)

    # ── Top-10 table ──────────────────────────────────────────
    ttk.Separator(frame, orient="horizontal").pack(fill="x", padx=10, pady=6)
    make_label(frame, "  Top 10 Highest-Risk Cells",
               fg=C_ACCENT, font=("Consolas", 9, "bold"),
               bg=C_BG).pack(anchor="w", padx=14)

    top_tree_frame = tk.Frame(frame, bg=C_BG)
    top_tree_frame.pack(fill="both", expand=True, padx=10, pady=(4, 10))

    top_cols = ("Rank", "Cell", "Score", "Level",
                "Incidents", "Killed", "Depth", "Trend", "Province")
    top_tree = ttk.Treeview(top_tree_frame, columns=top_cols,
                              show="headings", height=10)

    top_widths = {
        "Rank": 40, "Cell": 45, "Score": 50, "Level": 75,
        "Incidents": 70, "Killed": 55, "Depth": 50,
        "Trend": 110, "Province": 90
    }
    for col in top_cols:
        top_tree.heading(col, text=col)
        top_tree.column(col, width=top_widths.get(col, 60), anchor="center")

    top_scroll = ttk.Scrollbar(top_tree_frame, orient="vertical",
                                command=top_tree.yview)
    top_tree.configure(yscrollcommand=top_scroll.set)
    top_tree.pack(side="left", fill="both", expand=True)
    top_scroll.pack(side="right", fill="y")

    # "Last updated" label at the bottom right
    updated_var = tk.StringVar(value="")
    make_label(frame, "",
               textvariable=updated_var,
               fg=C_MUTED, font=("Consolas", 7),
               bg=C_BG).pack(anchor="e", padx=12)

    def refresh_stats():
        """Recompute all statistics and repaint this tab."""
        all_leaves = se.get_all_leaf_nodes(g_qt)
        all_inc    = []
        for leaf in all_leaves:
            all_inc.extend(leaf["incidents"])

        total_incidents = len(all_inc)
        total_killed    = sum(i.get("killed",  0) or 0 for i in all_inc)
        total_injured   = sum(i.get("injured", 0) or 0 for i in all_inc)

        # Score every non-empty cell
        scored = []
        for leaf in all_leaves:
            if len(leaf["incidents"]) == 0:
                continue
            s = rc.calculate_node_risk(leaf, g_year)
            scored.append((s, leaf))

        critical_count = sum(1 for s, _ in scored if s >= 80)

        kpi_vars["incidents"].set(str(total_incidents))
        kpi_vars["killed"].set(str(int(total_killed)))
        kpi_vars["injured"].set(str(int(total_injured)))
        kpi_vars["critical"].set(str(critical_count))
        kpi_vars["cells"].set(str(len(all_leaves)))

        # Count how many cells fall into each risk band
        band_counts = {b: 0 for b, _ in band_configs}
        for s, _ in scored:
            label, _ = rc.get_risk_band(s)
            if label in band_counts:
                band_counts[label] += 1

        max_count = max(band_counts.values()) if band_counts else 1

        # Map each band name to a representative score for get_risk_band
        band_scores = {
            "CRITICAL": 80, "HIGH": 60,
            "MEDIUM": 40, "LOW": 20, "MINIMAL": 0
        }

        for band_name, _ in band_configs:
            bar_cv, count_lbl = band_vars[band_name]
            cnt = band_counts[band_name]
            count_lbl.config(text=str(cnt))
            bar_cv.update_idletasks()
            w = bar_cv.winfo_width()
            bar_cv.delete("all")
            if max_count > 0 and w > 0:
                fill_w   = max(2, int((cnt / max_count) * w))
                _, colour = rc.get_risk_band(band_scores[band_name])
                bar_cv.create_rectangle(0, 0, fill_w, 14,
                                        fill=colour, outline="")

        # Rebuild the top-10 table
        scored.sort(key=lambda x: x[0], reverse=True)
        for row in top_tree.get_children():
            top_tree.delete(row)

        for rank, (score, leaf) in enumerate(scored[:10], 1):
            profile = rc.get_risk_profile(leaf, g_year)
            trend   = rc.get_trend(leaf, g_year)["trend"]
            prov    = (max(profile["provinces"],
                           key=profile["provinces"].get)
                       if profile["provinces"] else "?")
            top_tree.insert("", "end", values=(
                rank,
                leaf["cell_id"],
                score,
                profile["risk_label"],
                profile["total_incidents"],
                profile["total_killed"],
                leaf["depth"],
                trend,
                prov,
            ))

        updated_var.set(f"Last refreshed — Year {g_year}")

    make_button(frame, "  ↺ Refresh Stats",
                refresh_stats, colour=C_ACCENT).pack(pady=4)

    # Initial load — deferred 200 ms so widgets have been laid out
    # and winfo_width() returns the true pixel width for the bars
    frame.after(200, refresh_stats)

    frame.refresh_stats = refresh_stats
    return frame


# =============================================================
# MAIN — Build the window and run the app
# =============================================================

def main():
    global g_df, g_qt, g_year, g_next_id

    # ── Check CSV ─────────────────────────────────────────────
    if not os.path.exists(CSV_PATH):
        print(f"ERROR: '{CSV_PATH}' not found in this folder.")
        print("Put suicide-blasts-dataset.csv next to gui_app.py")
        sys.exit(1)

    # ── Load data ─────────────────────────────────────────────
    print("Loading data...")
    g_df = du.load_and_clean_data(CSV_PATH)

    print("Building Quadtree...")
    g_qt   = se.build_quadtree(g_df)
    g_df   = se.assign_row_cells(g_df, g_qt)
    g_year = int(g_df["Year"].max())

    # Find the highest existing row_idx so new incidents
    # start above it and never collide with existing IDs
    all_leaves = se.get_all_leaf_nodes(g_qt)
    all_ids    = []
    for leaf in all_leaves:
        for inc in leaf["incidents"]:
            all_ids.append(inc["row_idx"])
    g_next_id = (max(all_ids) + 1) if all_ids else 0

    print("Starting GUI...")

    # ── Create the main window ────────────────────────────────
    root = tk.Tk()
    root.title("Pakistan Blast Risk — Quadtree CRUD System")
    root.geometry("1100x760")
    root.minsize(900, 650)
    root.configure(bg=C_BG)

    # ── Header bar ────────────────────────────────────────────
    header = tk.Frame(root, bg="#0a1520", height=44)
    header.pack(fill="x")
    header.pack_propagate(False)

    tk.Label(
        header,
        text = "  QUADTREE / RISK  INTELLIGENCE",
        bg   = "#0a1520",
        fg   = C_ACCENT,
        font = ("Consolas", 11, "bold")
    ).pack(side="left", padx=6)

    # Live counter in the header — updates every 2 seconds
    header_count_var = tk.StringVar()

    def update_header_count():
        total = se.count_incidents(g_qt)
        n_cells = len(se.get_all_leaf_nodes(g_qt))
        header_count_var.set(
            f"Incidents: {total}  |  Cells: {n_cells}  |  Ref Year: {g_year}"
        )
        root.after(2000, update_header_count)

    tk.Label(
        header,
        textvariable = header_count_var,
        bg           = "#0a1520",
        fg           = C_MUTED,
        font         = ("Consolas", 8)
    ).pack(side="right", padx=12)

    update_header_count()

    # ── Notebook (tabs) ───────────────────────────────────────
    style = ttk.Style()
    style.theme_use("default")
    style.configure("TNotebook",
                     background  = C_BG,
                     borderwidth = 0)
    style.configure("TNotebook.Tab",
                     background = C_SURFACE,
                     foreground = C_MUTED,
                     padding    = [14, 6],
                     font       = ("Consolas", 9))
    style.map("TNotebook.Tab",
               background=[("selected", C_BG)],
               foreground=[("selected", C_ACCENT)])

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True)

    # ── Build all 4 tabs ──────────────────────────────────────
    map_tab,      refresh_map = build_map_tab(notebook)
    crud_tab                  = build_crud_tab(notebook, refresh_map)
    forecast_tab              = build_forecast_tab(notebook)
    stats_tab                 = build_stats_tab(notebook)

    notebook.add(map_tab,      text="  ◉  Risk Map  ")
    notebook.add(crud_tab,     text="  ≡  CRUD  ")
    notebook.add(forecast_tab, text="  ◎  Forecast  ")
    notebook.add(stats_tab,    text="  ▦  Stats  ")

    # Refresh the Stats tab whenever the user switches to it
    def on_tab_change(event):
        selected = notebook.tab(notebook.select(), "text").strip()
        if "Stats" in selected:
            stats_tab.refresh_stats()

    notebook.bind("<<NotebookTabChanged>>", on_tab_change)

    # ── Start the event loop ──────────────────────────────────
    root.mainloop()


if __name__ == "__main__":
    main()