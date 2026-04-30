import os
import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot  as plt
import matplotlib.patches as mpatches
import spatial_engine as se


# ----------------#
# Formula weights #
# ----------------#
W_DENSITY_PER_INCIDENT   = 5   
W_DENSITY_CAP            = 40  

W_DEPTH_PER_LEVEL        = 3    
W_DEPTH_CAP              = 20   

W_RECENCY_RECENT         = 4    
W_RECENCY_OLD            = 2    
W_RECENCY_CAP            = 25   
RECENCY_WINDOW_YEARS     = 2    

W_SEVERITY_PER_KILLED    = 0.1  
W_SEVERITY_CAP           = 15   

SCORE_MAX                = 100  


# ---------------------------------#
# Risk band thresholds and colours #
# ---------------------------------#
RISK_BANDS = [
    (80, "CRITICAL", "#8B0000"),   
    (60, "HIGH", "#E74C3C"),   
    (40, "MEDIUM",  "#E67E22"),   
    (20, "LOW", "#F1C40F"), 
    ( 0, "MINIMAL", "#27AE60"),   
]


# ================================#
# FUNCTION 1: calculate_node_risk #
# ================================#
def calculate_node_risk(node, current_year):
    """
    Returns an integer from 0 to 100.
    """
    incidents = node["incidents"]
    count     = len(incidents)

    if count == 0:
        return 0
    # ── 1. DENSITY SCORE ─────────────────────────────────────────
    density_score = min(count * W_DENSITY_PER_INCIDENT, W_DENSITY_CAP)

    # ── 2. DEPTH SCORE ───────────────────────────────────────────
    depth_score = min(node["depth"] * W_DEPTH_PER_LEVEL, W_DEPTH_CAP)

    # ── 3. RECENCY SCORE ─────────────────────────────────────────
    recent_count = 0
    old_count    = 0
    for inc in incidents:
        year = inc.get("year") or 0
        if current_year - year <= RECENCY_WINDOW_YEARS:
            recent_count += 1
        else:
            old_count += 1
    recency_score = min(recent_count * W_RECENCY_RECENT + old_count * W_RECENCY_OLD, W_RECENCY_CAP)

    # ── 4. SEVERITY SCORE ────────────────────────────────────────
    total_killed  = sum(inc.get("killed", 0) or 0 for inc in incidents)
    severity_score = min(total_killed * W_SEVERITY_PER_KILLED, W_SEVERITY_CAP)

    # ── TOTAL ────────────────────────────────────────────────────
    raw_score = density_score + depth_score + recency_score + severity_score
    final     = min(int(raw_score), SCORE_MAX)

    return final


# ==========================#
# FUNCTION 2: get_risk_band #
# ==========================#
def get_risk_band(score):
    for threshold, label, colour in RISK_BANDS:
        if score >= threshold:
            return label, colour
    return "MINIMAL", "#27AE60"


# =============================#
# FUNCTION 3: get_risk_profile #
# =============================#
def get_risk_profile(node, current_year):
    """
    Returns a dict with every stat needed for the terminal printout and the annotated map.
    """
    incidents = node["incidents"]
    count     = len(incidents)
    score     = calculate_node_risk(node, current_year)
    label, colour = get_risk_band(score)

    total_killed  = sum(inc.get("killed",  0) or 0 for inc in incidents)
    total_injured = sum(inc.get("injured", 0) or 0 for inc in incidents)
    avg_killed    = total_killed  / count if count else 0.0
    avg_injured   = total_injured / count if count else 0.0

    recent = [i for i in incidents if (i.get("year") or 0) >= current_year - RECENCY_WINDOW_YEARS]

    years = [i["year"] for i in incidents if i.get("year")]
    year_min = min(years) if years else None
    year_max = max(years) if years else None

    # Province breakdown
    provinces = {}
    for inc in incidents:
        p = inc.get("label", "Unknown")
        provinces[p] = provinces.get(p, 0) + 1

    area_km2 = se.get_cell_area_km2(node)

    density_per_100km2 = (count / area_km2 * 100) if area_km2 > 0 else 0.0

    depth_s   = min(node["depth"] * W_DEPTH_PER_LEVEL,   W_DEPTH_CAP)
    density_s = min(count         * W_DENSITY_PER_INCIDENT, W_DENSITY_CAP)
    recent_c  = len(recent)
    old_c     = count - recent_c
    recency_s = min(recent_c * W_RECENCY_RECENT + old_c * W_RECENCY_OLD, W_RECENCY_CAP)
    severity_s = min(total_killed * W_SEVERITY_PER_KILLED, W_SEVERITY_CAP)

    return {
        "cell_id":            node["cell_id"],
        "depth":              node["depth"],
        "risk_score":         score,
        "risk_label":         label,
        "risk_colour":        colour,
        "total_incidents":    count,
        "recent_incidents":   len(recent),
        "total_killed":       int(total_killed),
        "total_injured":      int(total_injured),
        "avg_killed":         round(avg_killed,  1),
        "avg_injured":        round(avg_injured, 1),
        "year_first":         year_min,
        "year_last":          year_max,
        "provinces":          provinces,
        "area_km2":           round(area_km2, 1),
        "density_per_100km2": round(density_per_100km2, 2),
        "lat_min":            node["lat_min"],
        "lat_max":            node["lat_max"],
        "lon_min":            node["lon_min"],
        "lon_max":            node["lon_max"],
        # formula breakdown
        "score_density":      int(density_s),
        "score_depth":        int(depth_s),
        "score_recency":      int(recency_s),
        "score_severity":     int(severity_s),
    }


# =====================================#
# FUNCTION 4: calculate_all_cell_risks #
# =====================================#
def calculate_all_cell_risks(root, current_year):
    """
    Returns dict   { cell_id -> score (0..100) }
    """
    scores = {}
    for leaf in se.get_all_leaf_nodes(root):
        scores[leaf["cell_id"]] = calculate_node_risk(leaf, current_year)
    return scores


# =========================# 
# FUNCTION 5  —  get_trend #
# =========================#
def get_trend(node, current_year):
    """
    Window size = 3 years.
    Counts incidents in:
      window_1  =  oldest  (current_year-9 to current_year-6)
      window_2  =  middle  (current_year-6 to current_year-3)
      window_3  =  recent  (current_year-3 to current_year  )

    Returns a dict with:
      "trend"    : str   "ESCALATING" / "DE-ESCALATING" / "STABLE" / "NO DATA"
      "counts"   : list  [w1_count, w2_count, w3_count]
      "colour"   : str   hex colour for the forecast map
    """
    incidents = node["incidents"]
    if not incidents:
        return {"trend": "NO DATA", "counts": [0, 0, 0], "colour": "#27AE60"}

    w1 = sum(1 for i in incidents if i.get("year") and current_year-9 <= i["year"] < current_year-6)
    w2 = sum(1 for i in incidents if i.get("year") and current_year-6 <= i["year"] < current_year-3)
    w3 = sum(1 for i in incidents if i.get("year") and current_year-3 <= i["year"] <= current_year)

    if w3 > w2 and w2 >= w1:
        trend  = "ESCALATING"
        colour = "#8B0000"   
    elif w3 > w2:
        trend  = "ESCALATING"
        colour = "#C0392B"   
    elif w3 < w2:
        trend  = "DE-ESCALATING"
        colour = "#E67E22"   
    else:
        trend  = "STABLE"
        colour = "#F1C40F"   

    return {"trend": trend, "counts": [w1, w2, w3], "colour": colour}




