import pathlib
import pandas as pd

SLOTS_ORDER = [
    "7:00 - 8:30", "8:30 - 10:00", "10:00 - 11:30", "11:30 - 13:00",
    "13:00 - 14:30", "14:30 - 16:00", "16:00 - 17:30", "17:30 - 19:00", "19:00 - 20:00"
]

def _read_file(path):
    path = pathlib.Path(path)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    # Google Forms exports in this project use ';' as delimiter and can include
    # commas inside cells (time-slot lists), so delimiter inference is safer.
    try:
        return pd.read_csv(path, sep=None, engine="python")
    except Exception:
        # Fallback for uncommon malformed rows while keeping all available data.
        return pd.read_csv(path, sep=";", engine="python", on_bad_lines="skip")

def parse_num_shifts(val):
    if pd.isna(val): return 0
    val = str(val).strip()
    if "Todo el día" in val: return len(SLOTS_ORDER)
    try: return int(float(val))
    except: return 1

def parse_slots(val):
    if pd.isna(val): return []
    slots = [s.strip() for s in str(val).split(",") if s.strip()]
    return [s for s in slots if "-" in s and ":" in s]

def parse_locations(val, all_locations):
    if pd.isna(val): return all_locations
    val = str(val)
    if "Donde me necesiten" in val: return all_locations
    matched = [loc for loc in all_locations if loc.lower() in val.lower()]
    return matched if matched else all_locations

def build_problem_data(respuestas_path, esquinas_path):
    esquinas_df = _read_file(esquinas_path)
    all_locations = esquinas_df["location"].dropna().unique().tolist()
    
    df = _read_file(respuestas_path)
    
    avail_rows = []
    vol_max = {}
    
    for _, row in df.iterrows():
        if pd.isna(row.iloc[0]):
            continue
        v = str(row.iloc[0]).strip()
        if not v or v.lower() == "nan":
            continue

        respuesta = str(row.iloc[1]).strip()
        if respuesta.startswith("No"):
            continue
        
        day_choice = str(row.iloc[2]).strip()
        days_to_process = []
        
        if "Viernes" in day_choice:
            days_to_process.append(("Viernes 9", row.iloc[3], row.iloc[4], row.iloc[5]))
        elif "Sábado" in day_choice or "Sabado" in day_choice:
            days_to_process.append(("Sábado 10", row.iloc[6], row.iloc[7], row.iloc[8]))
        elif "Ambos" in day_choice:
            days_to_process.append(("Viernes 9", row.iloc[9], row.iloc[10], row.iloc[13]))
            days_to_process.append(("Sábado 10", row.iloc[11], row.iloc[12], row.iloc[13]))
            
        for d, shifts_val, slots_val, loc_val in days_to_process:
            max_s = parse_num_shifts(shifts_val)
            slots = parse_slots(slots_val)
            locs = parse_locations(loc_val, all_locations)
            
            vol_max[(v, d)] = max_s
            for s in slots:
                for l in locs:
                    avail_rows.append({"volunteer": v, "date": d, "slot": s, "location": l})
                    
    availability = pd.DataFrame(avail_rows)
    blocks = sorted(availability[["date", "slot", "location"]].drop_duplicates().itertuples(index=False, name=None)) if not availability.empty else []
    volunteers = (
        sorted(availability["volunteer"].dropna().astype(str).unique().tolist())
        if not availability.empty
        else []
    )
    
    return {
        "availability": availability,
        "volunteers": volunteers,
        "blocks": blocks,
        "volunteer_max": vol_max,
        "all_locations": all_locations
    }