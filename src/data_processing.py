import pathlib
import pandas as pd

SLOTS_ORDER = [
    "7:00 - 8:30", "8:30 - 10:00", "10:00 - 11:30", "11:30 - 13:00",
    "13:00 - 14:30", "14:30 - 16:00", "16:00 - 17:30", "17:30 - 19:00", "19:00 - 20:00"
]

def _read_file(path):
    path = pathlib.Path(path)
    try:
        return pd.read_csv(path, sep=None, engine="python")
    except Exception:
        # Fallback for uncommon malformed rows while keeping all available data.
        return pd.read_csv(path, sep=";", engine="python", on_bad_lines="skip")

def parse_num_shifts(val):
    if pd.isna(val): return 0
    val_str = str(val).strip()
    # Se agrega "Cualquier horario" para contemplar la nueva respuesta del formulario
    if "Todo el día" in val_str or "Cualquier horario" in val_str: 
        return len(SLOTS_ORDER)
    try: return int(float(val_str))
    except: return 1

def parse_slots(val):
    if pd.isna(val): return []
    val_str = str(val)
    if "Todo el día" in val_str or "Cualquier horario" in val_str: 
        return SLOTS_ORDER
    
    slots = [s.strip() for s in val_str.split(",") if s.strip()]
    
    valid_slots = []
    for s in slots:
        # Normalizamos quitando todos los espacios para asegurar el match
        clean_s = s.replace(" ", "").lower()
        for canonical in SLOTS_ORDER:
            if canonical.replace(" ", "").lower() == clean_s:
                valid_slots.append(canonical)
                break
    return valid_slots

def parse_locations(val, all_locations):
    if pd.isna(val): return all_locations
    val_str = str(val)
    if "Donde me necesiten" in val_str: return all_locations
    matched = [loc for loc in all_locations if loc.lower() in val_str.lower()]
    return matched if matched else all_locations

def build_problem_data(respuestas_path, esquinas_path):
    esquinas_df = _read_file(esquinas_path)
    all_locations = esquinas_df["location"].dropna().unique().tolist()
    
    df = _read_file(respuestas_path)
    avail_rows = []
    vol_max = {}
    roles = {}
    contacto = {}
    
    for _, row in df.iterrows():
        if pd.isna(row.iloc[0]):
            continue
        # correo electrónico
        correo = str(row.iloc[0]).strip()

        # nombre del voluntario
        v = str(row.iloc[1]).strip()
        if not v or v.lower() == "nan": # chequear nulos
            continue

        # número de teléfono
        telefono = str(row.iloc[2]).strip()

        contacto[v] = {"correo": correo, "telefono": telefono}

        # asistencia (si o no)
        asistencia = str(row.iloc[3]).strip().lower()
        if "sí" not in asistencia:
            continue
        # elección de día(s) de asistencia
        dia = str(row.iloc[4]).strip().lower()
        days_to_process = []
        # la tupla que se agrega es: (dia, cantidad de turnos, horarios, esquinas)
        if "viernes" in dia:
            days_to_process.append(("Viernes", row.iloc[5], row.iloc[6], row.iloc[7]))
        elif "sábado" in dia:
            days_to_process.append(("Sábado", row.iloc[8], row.iloc[9], row.iloc[10]))
        elif "ambos" in dia:
            days_to_process.append(("Viernes", row.iloc[11], row.iloc[12], row.iloc[15]))
            days_to_process.append(("Sábado", row.iloc[13], row.iloc[14], row.iloc[15]))
        es_jefe = "comisionadx" not in str(row.iloc[16]).strip().lower() or pd.isna(row.iloc[16]) or \
                    "comunero" not in str(row.iloc[16]).strip().lower()
        roles[v] = es_jefe
            
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
    volunteers = sorted(list(set(roles.keys())))
    
    return {
        "availability": availability,
        "volunteers": volunteers,
        "blocks": blocks,
        "volunteer_max": vol_max,
        "all_locations": all_locations,
        "roles_jefatura": roles,
        "contacto": contacto
    }