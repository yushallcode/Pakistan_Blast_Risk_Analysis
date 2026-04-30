
# pandas lets us read CSVs and work with tables (DataFrames)
import pandas as pd

# os lets us check whether a file exists on disk
import os


# ------------------------------------------------------------------
# Province name corrections
# The dataset sometimes spells "FATA" as "Fata" and "NaN" appears
# where the province is unknown.  We fix those here.
# ------------------------------------------------------------------
PROVINCE_FIX = {
    "Fata": "FATA",   # wrong spelling -> correct spelling
    "Nan":  "Unknown" # pandas NaN turned into string -> make it "Unknown"
}

# ------------------------------------------------------------------
# Province centre coordinates  (latitude, longitude)
# These are used by Demo Mode so the user can just type "KPK"
# instead of typing exact GPS coordinates.
# ------------------------------------------------------------------
PROVINCE_CENTRES = {
    "KPK":         (33.76, 71.51),
    "FATA":        (33.54, 70.65),
    "Punjab":      (32.36, 73.37),
    "Sindh":       (25.46, 67.27),
    "Balochistan": (30.00, 67.05),
    "Capital":     (33.72, 73.07),
    "AJK":         (34.07, 73.62),
}

# ------------------------------------------------------------------
# Columns to remove from the CSV before we do anything else.
# Reasons they are dropped:
#   - Too many missing values  (most of the column is blank)
#   - Free-text fields we cannot use in calculations
#   - Duplicate of another column
# ------------------------------------------------------------------
COLS_TO_DROP = [
    "S#",                       # just the row number — useless
    "Date",                     # messy text — we use the Year column
    "Islamic Date",             # 154 rows missing
    "Holiday Type",             # 424 rows missing (86 % blank)
    "Time",                     # 211 rows missing (43 % blank)
    "City",                     # same info as Province + lat/lon
    "Location",                 # 487 unique free-text phrases
    "Influencing Event/Event",  # 305 rows missing (61 % blank)
    "Targeted Sect if any",     # 399 rows missing (80 % blank)
    "Killed Min",               # we use Killed Max (more complete)
    "Injured Min",              # we use Injured Max (more complete)
    "Explosive Weight (max)",   # 324 rows missing (65 % blank)
    "Hospital Names",           # free text — can't compute with it
    "Temperature(F)",           # same info as Temperature(C)
    "No. of Suicide Blasts",    # too many missing; not used
    "Blast Day Type",           # not used in the heuristic
    "Open/Closed Space",        # not used in the heuristic
    "Location Sensitivity",     # not used in the heuristic
]


# ==================================================================
# FUNCTION 1  —  load_and_clean_data
# ==================================================================
def load_and_clean_data(csv_path):
    """
    Load the CSV file and return a clean DataFrame.

    A DataFrame is like a spreadsheet table inside Python.
    Each row is one blast incident.  Each column is one piece
    of information about that incident.

    Steps we perform (explained in plain English):
      1. Drop the columns we don't need
      2. Fix broken data types
         (Longitude and Injured Max were stored as text, not numbers)
      3. Remove the 4 rows that have no GPS coordinates
         (we can't place them on the Quadtree without lat/lon)
      4. Standardise text capitalisation
         (fixes things like "foreign" vs "Foreign" vs "FOREIGN")
      5. Fill in remaining blanks with safe default values

    Parameters
    ----------
    csv_path : str   full path to the CSV file on disk

    Returns
    -------
    pd.DataFrame   a clean table ready for the rest of the project
    """

    # SAFETY CHECK — tell the user clearly if the file is missing
    if not os.path.exists(csv_path):
        raise FileNotFoundError(
            "[data_utils] File not found: " + csv_path + "\n"
            "Make sure suicide-blasts-dataset.csv is in the same folder."
        )

    print("[data_utils] Loading: " + csv_path)

    # Read every row and column from the CSV into a DataFrame
    df = pd.read_csv(csv_path)

    print("[data_utils] Raw shape: "
          + str(df.shape[0]) + " rows x "
          + str(df.shape[1]) + " columns")

    # ------------------------------------------------------------------
    # STEP 1 — Drop columns we don't need
    # We build a list of column names that actually exist in df
    # (some might not be present in every version of the CSV)
    # ------------------------------------------------------------------
    columns_to_actually_drop = []          # start with an empty list
    for col_name in COLS_TO_DROP:          # go through every name we want to drop
        if col_name in df.columns:         # only add it if it exists in our table
            columns_to_actually_drop.append(col_name)

    df.drop(columns=columns_to_actually_drop, inplace=True)
    # inplace=True means "change df directly instead of making a copy"

    # ------------------------------------------------------------------
    # STEP 2 — Fix data types
    # pandas read these two as text (strings) instead of numbers.
    # pd.to_numeric converts them; errors="coerce" turns bad values to NaN
    # (NaN = Not a Number = blank/missing in pandas)
    # ------------------------------------------------------------------
    df["Longitude"]   = pd.to_numeric(df["Longitude"],   errors="coerce")
    df["Injured Max"] = pd.to_numeric(df["Injured Max"],  errors="coerce")

    # ------------------------------------------------------------------
    # STEP 3 — Remove rows with missing GPS coordinates
    # We cannot place an incident on the Quadtree without lat and lon.
    # ------------------------------------------------------------------
    rows_before_drop = len(df)              # count rows before we drop any

    df.dropna(subset=["Latitude", "Longitude"], inplace=True)
    # dropna means "drop rows where these columns have NaN values"

    rows_dropped = rows_before_drop - len(df)
    if rows_dropped > 0:
        print("[data_utils] Dropped "
              + str(rows_dropped)
              + " rows with missing coordinates")

    # ------------------------------------------------------------------
    # STEP 4 — Standardise text capitalisation
    # .str.strip()  removes spaces from the start and end
    # .str.title()  makes "First Letter Of Each Word Capital"
    # This fixes things like "kpk" -> "Kpk" or "CIVILIAN" -> "Civilian"
    # ------------------------------------------------------------------
    text_columns = ["Province", "Location Category", "Target Type"]

    for col_name in text_columns:
        if col_name in df.columns:
            # Convert to string first (in case pandas stored it as something else)
            df[col_name] = df[col_name].astype(str)
            df[col_name] = df[col_name].str.strip()   # remove leading/trailing spaces
            df[col_name] = df[col_name].str.title()   # capitalise properly

    # Apply the province spelling corrections from our dictionary above
    df["Province"] = df["Province"].replace(PROVINCE_FIX)

    # ------------------------------------------------------------------
    # STEP 5 — Fill remaining missing values with safe defaults
    # For numbers: use the median (middle value) so outliers don't skew
    # For text: use a clear placeholder string like "Unknown"
    # ------------------------------------------------------------------

    # Numeric columns — fill blanks with the column's median
    numeric_columns_to_fill = ["Killed Max", "Injured Max", "Temperature(C)"]
    for col_name in numeric_columns_to_fill:
        if col_name in df.columns:
            column_median = df[col_name].median()         # calculate the median
            df[col_name]  = df[col_name].fillna(column_median)  # fill NaN with it

    # Text columns — fill blanks with a readable default
    text_columns_to_fill = [
        ("Location Category", "Unknown"),
        ("Target Type",       "Unknown"),
        ("Province",          "Unknown"),
    ]
    for col_name, default_value in text_columns_to_fill:
        if col_name in df.columns:
            df[col_name] = df[col_name].fillna(default_value)

    # Reset the row numbers so they go 0, 1, 2, 3, …  cleanly
    df.reset_index(drop=True, inplace=True)

    print("[data_utils] Clean dataset: "
          + str(df.shape[0]) + " rows x "
          + str(df.shape[1]) + " columns")

    return df


# ==================================================================
# FUNCTION 2  —  get_province_centre
# ==================================================================
def get_province_centre(province_name):
    """
    Return the (latitude, longitude) centre-point of a named province.

    Used by Demo Mode so the user can type "KPK" instead of
    having to find and type exact GPS coordinates.

    If the province name is not recognised, we return (None, None)
    and print a helpful message so the user knows what went wrong.

    Parameters
    ----------
    province_name : str   e.g. "KPK", "Sindh", "Punjab"

    Returns
    -------
    tuple   (latitude, longitude)  or  (None, None) if not found
    """

    # Clean up whatever the user typed
    cleaned_name = province_name.strip()   # remove spaces from both ends
    cleaned_name = cleaned_name.title()    # capitalise like a title

    # Apply our spelling fixes (e.g. "Fata" -> "FATA")
    if cleaned_name in PROVINCE_FIX:
        cleaned_name = PROVINCE_FIX[cleaned_name]

    # Look up the centre coordinates in our dictionary
    if cleaned_name in PROVINCE_CENTRES:
        centre_coordinates = PROVINCE_CENTRES[cleaned_name]
        return centre_coordinates         # returns (lat, lon)

    # If we get here the province name was not recognised
    print("[data_utils] Unknown province: '" + province_name + "'")
    print("[data_utils] Known provinces: " + str(list(PROVINCE_CENTRES.keys())))
    return None, None                     # signal "not found"


# ==================================================================
# FUNCTION 3  —  summarise_data
# ==================================================================
def summarise_data(df):
    """
    Print a quick human-readable summary of the clean DataFrame.

    This is called by Option E in main_app.py to show dataset
    statistics in the terminal.

    Parameters
    ----------
    df : pd.DataFrame   the clean dataset from load_and_clean_data()
    """

    print("")
    print("=" * 50)
    print("  DATA SUMMARY")
    print("=" * 50)

    # Count rows and columns
    total_rows    = len(df)
    total_columns = len(df.columns)
    print("  Rows          : " + str(total_rows))
    print("  Columns       : " + str(total_columns))

    # Year range
    earliest_year = int(df["Year"].min())
    latest_year   = int(df["Year"].max())
    print("  Year range    : " + str(earliest_year) + " to " + str(latest_year))

    # Unique provinces
    all_provinces = sorted(df["Province"].unique())
    print("  Provinces     : " + str(all_provinces))

    # GPS range
    min_lat = df["Latitude"].min()
    max_lat = df["Latitude"].max()
    min_lon = df["Longitude"].min()
    max_lon = df["Longitude"].max()
    print("  Lat range     : " + str(round(min_lat, 2)) + " to " + str(round(max_lat, 2)))
    print("  Lon range     : " + str(round(min_lon, 2)) + " to " + str(round(max_lon, 2)))

    # Casualties
    total_killed  = int(df["Killed Max"].sum())
    total_injured = int(df["Injured Max"].sum())
    print("  Total killed  : " + str(total_killed))
    print("  Total injured : " + str(total_injured))

    print("=" * 50)
    print("")