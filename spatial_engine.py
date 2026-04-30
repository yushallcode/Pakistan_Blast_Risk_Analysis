
import math

PAK_LAT_MIN = 23.5    
PAK_LAT_MAX = 37.5    
PAK_LON_MIN = 60.5    
PAK_LON_MAX = 77.5    

MAX_INCIDENTS_PER_CELL = 5    
MAX_DEPTH              = 6   

#======================#
#FUNCTION 1: make_node #
#======================#
def make_node(lat_min, lat_max, lon_min, lon_max, depth=0):
    """
    Returns a dict which is a fresh, empty node

    """
    new_node = {
        "lat_min":   lat_min,   
        "lat_max":   lat_max,   
        "lon_min":   lon_min,   
        "lon_max":   lon_max,   
        "depth":     depth,     
        "cell_id":   None,      
        "incidents": [],        
        "children":  [],        
    }

    return new_node


#==========================#
#FUNCTION 2: node_contains #
#==========================#
def node_contains(node, lat, lon):
    """
    Checks if a GPS point (lat, lon) is inside this node.
    Returns a bool; True if the point is inside this cell, False otherwise

    """
    latitude_ok  = (node["lat_min"] <= lat < node["lat_max"])
    longitude_ok = (node["lon_min"] <= lon < node["lon_max"])
    return latitude_ok and longitude_ok


#====================#
#FUNCTION 3: is_leaf #
#====================#
def is_leaf(node):
    """
    Returns bool; True if this node has no children (is a leaf)

    """
    return len(node["children"]) == 0


#========================#
# FUNCTION 4: split_node #
#========================#
def split_node(node):
    """
    Before splitting:          After splitting:
    +------------------+       +--------+--------+
    |                  |       |   NW   |   NE   |
    |   one big cell   |  -->  +--------+--------+
    |   with 6 points  |       |   SW   |   SE   |
    +------------------+       +--------+--------+

    Returns: a node dict which is now split into 4 children, and all incidents moved down
    """

    lat_mid = (node["lat_min"] + node["lat_max"]) / 2
    lon_mid = (node["lon_min"] + node["lon_max"]) / 2

    child_depth = node["depth"] + 1

    north_west = make_node(lat_mid, node["lat_max"], node["lon_min"], lon_mid, child_depth)
    north_east = make_node(lat_mid, node["lat_max"], lon_mid, node["lon_max"], child_depth)
    south_west = make_node(node["lat_min"], lat_mid, node["lon_min"], lon_mid, child_depth)
    south_east = make_node(node["lat_min"], lat_mid, lon_mid, node["lon_max"], child_depth)

    node["children"] = [north_west, north_east, south_west, south_east]

    for incident in node["incidents"]:
        for child in node["children"]:
            if node_contains(child, incident["lat"], incident["lon"]):
                child["incidents"].append(incident) 
                break                               
    node["incidents"] = []


# ============================#
# FUNCTION 5: insert_incident #
# ============================#
def insert_incident(node, lat, lon, row_idx, year=None, label="", killed=0.0, injured=0.0):
    
    if not node_contains(node, lat, lon):
        return

    if is_leaf(node):
        new_incident = {
            "row_idx": row_idx,  
            "lat":     lat,      
            "lon":     lon,      
            "year":    year,     
            "label":   label,    
            "killed":  killed,   
            "injured": injured,  
        }
        node["incidents"].append(new_incident)

        too_many_incidents = len(node["incidents"]) > MAX_INCIDENTS_PER_CELL
        not_too_deep = node["depth"] < MAX_DEPTH

        if too_many_incidents and not_too_deep:
            split_node(node)

    else:
        for child in node["children"]:
            if node_contains(child, lat, lon):
                insert_incident(child, lat, lon, row_idx, year, label, killed, injured)
                break  


# ===========================#
# FUNCTION 6: build_quadtree #
# ===========================#
def build_quadtree(df):
    """
    Returns dict which is the root node of the finished Quadtree
    """

    print("Quadtree building in progress ...")

    root = make_node(PAK_LAT_MIN, PAK_LAT_MAX, PAK_LON_MIN, PAK_LON_MAX, depth=0)

    for row_idx, row in df.iterrows():
        latitude  = float(row["Latitude"])
        longitude = float(row["Longitude"])

        if "Year" in row:
            year_value = int(row["Year"])
        else:
            year_value = None

        if "Province" in row:
            label_value = str(row["Province"])
        else:
            label_value = ""

        if "Killed Max" in row:
            killed_value = float(row["Killed Max"])
        else:
            killed_value = 0.0

        if "Injured Max" in row:
            injured_value = float(row["Injured Max"])
        else:
            injured_value = 0.0

        insert_incident(root, latitude, longitude, row_idx,
            year = year_value,
            label = label_value,
            killed = killed_value,
            injured = injured_value,
        )
        
    assign_cell_ids(root)

    #counting how many leaf cells were created
    all_leaves  = get_all_leaf_nodes(root)
    total_cells = len(all_leaves)
    print("Quadtree built with " + str(total_cells) + " leaf cells created.")

    return root


# ============================#
# FUNCTION 7: assign_cell_ids #
# ============================#
def assign_cell_ids(node, counter=None):
    """
    Returns:
    None, but assigns a unique integer ID to every leaf node in the tree.
    """
    if counter is None:
        counter = [0] 
    if is_leaf(node):
        node["cell_id"] = counter[0]
        counter[0] = counter[0] + 1
    else:
        for child in node["children"]:
            assign_cell_ids(child, counter)


# ===========================#
# FUNCTION 8: find_leaf_node #
# ===========================#
def find_leaf_node(root, lat, lon):
    """
    Returns
    dict which is the leaf node containing the point (lat, lon), or None if the point is outside Pakistan
    """

    inside_latitude_range  = (PAK_LAT_MIN <= lat <= PAK_LAT_MAX)
    inside_longitude_range = (PAK_LON_MIN <= lon <= PAK_LON_MAX)
    if not inside_latitude_range or not inside_longitude_range:
        return None   

    return _find_recursive(root, lat, lon)


def _find_recursive(node, lat, lon):
    """
    helper for find_leaf_node.
    """
    if not node_contains(node, lat, lon):
        return None
    if is_leaf(node):
        return node
    for child in node["children"]:
        result = _find_recursive(child, lat, lon)
        if result is not None:
            return result 
    return None 


# ===============================#
# FUNCTION 9: get_all_leaf_nodes # 
# ===============================#
def get_all_leaf_nodes(node, result=None):
    """
    Returns list of all leaf nodes in the tree rooted at this node.
    """
    if result is None:
        result = []
    if is_leaf(node):
        result.append(node)
    else:
        for child in node["children"]:
            get_all_leaf_nodes(child, result)
    return result


# =============================#
# FUNCTION 10: count_incidents #
# =============================#
def count_incidents(node):
    """
    Returns an int total number of incidents
    """
    if is_leaf(node):
        return len(node["incidents"])
    else:
        total = 0
        for child in node["children"]:
            total = total + count_incidents(child)
        return total


# =====================================#
# FUNCTION 11: get_incidents_in_region #
# =====================================#
def get_incidents_in_region(root, lat_min, lat_max, lon_min, lon_max):
    """
    Returns all incidents whose GPS point falls inside the rectangle defined by the given coordinates.
    
    root    : dict   the root node of the tree
    lat_min : float  southern edge of the query rectangle
    lat_max : float  northern edge
    lon_min : float  western edge
    lon_max : float  eastern edge
    """

    results = []  
    _range_query(root, lat_min, lat_max, lon_min, lon_max, results)
    return results

def _range_query(node, lat_min, lat_max, lon_min, lon_max, results):

    no_overlap = ( lat_min >= node["lat_max"] or lat_max <= node["lat_min"] or lon_min >= node["lon_max"] or lon_max <= node["lon_min"])
    if no_overlap:
        return 
    if is_leaf(node):
        for incident in node["incidents"]:
            lat_ok = (lat_min <= incident["lat"] <= lat_max)
            lon_ok = (lon_min <= incident["lon"] <= lon_max)
            if lat_ok and lon_ok:
                results.append(incident) 
    else:
        for child in node["children"]:
            _range_query(child, lat_min, lat_max, lon_min, lon_max, results)


# =============================#
# FUNCTION 12: update_incident #
# =============================#
def update_incident(root, row_idx, new_year=None, new_label=None):
    """
    Returns: bool True if the incident was found and updated, False otherwise
    """
    all_leaves = get_all_leaf_nodes(root)
    for leaf in all_leaves:
        for incident in leaf["incidents"]:
            if incident["row_idx"] == row_idx:
                if new_year is not None:
                    incident["year"] = new_year
                if new_label is not None:
                    incident["label"] = new_label
                return True   
    return False  


# =============================#
# FUNCTION 13: delete_incident #
# =============================#
def delete_incident(root, row_idx):
    """
    Returns: bool True if the incident was found and deleted, False otherwise
    """
    all_leaves = get_all_leaf_nodes(root)
    for leaf in all_leaves:
        for i in range(len(leaf["incidents"])):
            if leaf["incidents"][i]["row_idx"] == row_idx:
                leaf["incidents"].pop(i)
                return True
    return False 


# ==============================#
# FUNCTION 14: assign_row_cells #
# ==============================#
def assign_row_cells(df, root):
    """
    Returns pd.DataFrame a copy of df with an extra "cell_id" column
    """

    print("DataFrame row-to-cell assignment in progress ...")

    cell_ids = []
    for index, row in df.iterrows():
        lat  = row["Latitude"]
        lon  = row["Longitude"]

        leaf = find_leaf_node(root, lat, lon)
        if leaf is not None:
            cell_ids.append(leaf["cell_id"])
        else:
            cell_ids.append(-1) 

    df_with_cells = df.copy()
    df_with_cells["cell_id"] = cell_ids
    unique_cell_count = df_with_cells["cell_id"].nunique()
    print("DataFrame row-to-cell assignment done. " + str(unique_cell_count) + " unique cells used.")
    return df_with_cells


# ===============================#
# FUNCTION 15: get_cell_area_km2 #
# ===============================#
def get_cell_area_km2(node):
    """
    We use the "flat Earth" approximation, which is accurate enough
    for risk scoring at this scale:
      1 degree of latitude  ≈ 111 km everywhere
      1 degree of longitude ≈ 111 × cos(latitude) km (longitude degrees get shorter as you move toward the poles)
    Source: https://orsac.odisha.gov.in/pdf/Geodesy-fundamentals.pdf
    
    Returns: float approximate area in km²
    """
    centre_lat = (node["lat_min"] + node["lat_max"]) / 2

    lat_span_degrees = node["lat_max"] - node["lat_min"]
    height_km        = lat_span_degrees * 111.0

    lon_span_degrees = node["lon_max"] - node["lon_min"]
    cos_of_lat       = math.cos(math.radians(centre_lat))
    width_km         = lon_span_degrees * 111.0 * cos_of_lat

    area_km2 = height_km * width_km

    return area_km2