from collections import defaultdict
import pandas as pd
import gurobipy as gp
from gurobipy import GRB

SLOTS_ORDER = [
    "7:00 - 8:30", "8:30 - 10:00", "10:00 - 11:30", "11:30 - 13:00",
    "13:00 - 14:30", "14:30 - 16:00", "16:00 - 17:30", "17:30 - 19:00", "19:00 - 20:00"
]

CAPACIDAD_MAXIMA = 4
CAPACIDAD_MINIMA = 2

# Pesos para priorizar horarios (mayor valor = mayor prioridad)
SLOT_WEIGHTS = {
    "7:00 - 8:30": 8,    # Penalización leve (extremo inicial)
    "8:30 - 10:00": 9,   # Penalización leve (extremo inicial)
    "10:00 - 11:30": 15, # Prioridad alta (temprano)
    "11:30 - 13:00": 14, # Prioridad alta
    "13:00 - 14:30": 13, # Prioridad media
    "14:30 - 16:00": 12, # Prioridad media
    "16:00 - 17:30": 11, # Prioridad baja
    "17:30 - 19:00": 8,  # Penalización leve (extremo final)
    "19:00 - 20:00": 7   # Penalización leve (extremo final)
}

# Premio para penalizar fuertemente esquinas vacías (asegura al menos 1 voluntario)
RECOMPENSA_COBERTURA = 1000

def build_and_solve(availability, volunteers, blocks, volunteer_max, all_locations, time_limit=300.0, mip_gap=0.01):
    avail_set = set(availability.itertuples(index=False, name=None))

    model = gp.Model("colectatron8000")
    model.setParam("OutputFlag", 1)
    if time_limit is not None: model.setParam("TimeLimit", time_limit)
    model.setParam("MIPGap", mip_gap)

    x = {}
    for v, d, s, l in avail_set:
        x[v, d, s, l] = model.addVar(vtype=GRB.BINARY, name=f"x_{v}_{d}_{s}_{l}")

    if not x:
        return pd.DataFrame(columns=["volunteer", "date", "slot", "location"])

    # --- NUEVA LÓGICA DE FUNCIÓN OBJETIVO ---
    dsl_set = set((d, s, l) for v, d, s, l in x.keys())
    
    is_covered = {}
    for d, s, l in dsl_set:
        is_covered[d, s, l] = model.addVar(vtype=GRB.BINARY, name=f"cov_{d}_{s}_{l}")

    for d, s, l in dsl_set:
        v_vars = [x[v, d, s, l] for v in volunteers if (v, d, s, l) in x]
        if v_vars:
            # is_covered solo puede valer 1 si hay al menos un voluntario asignado a esa esquina en ese bloque
            model.addConstr(is_covered[d, s, l] <= gp.quicksum(v_vars), name=f"link_cov_{d}_{s}_{l}")
        else:
            model.addConstr(is_covered[d, s, l] == 0)

    # Maximizar la cobertura de esquinas + el peso del turno
    obj_expr = gp.quicksum(SLOT_WEIGHTS.get(s, 10) * var for (v, d, s, l), var in x.items())
    obj_expr += gp.quicksum(RECOMPENSA_COBERTURA * var for var in is_covered.values())
    model.setObjective(obj_expr, GRB.MAXIMIZE)
    # ----------------------------------------

    # 1. Capacidad por bloque
    block_vars = defaultdict(list)
    for (v, d, s, l), var in x.items():
        block_vars[d, s, l].append(var)
        
    for (d, s, l), vars_in_block in block_vars.items():
        suma_voluntarios = gp.quicksum(vars_in_block)
        
        # Máximo
        model.addConstr(suma_voluntarios <= CAPACIDAD_MAXIMA, name=f"cap_max_{d}_{s}_{l}")
        
        # Mínimo condicionado (solo exige el mínimo si is_covered es 1)
        model.addConstr(suma_voluntarios >= CAPACIDAD_MINIMA * is_covered[d, s, l], name=f"cap_min_{d}_{s}_{l}")

    # 2. Única esquina por día (y link con x)
    y = {}
    for v, d, s, l in x.keys():
        if (v, d, l) not in y:
            y[v, d, l] = model.addVar(vtype=GRB.BINARY, name=f"y_{v}_{d}_{l}")
            
    for (v, d, s, l), var in x.items():
        model.addConstr(var <= y[v, d, l], name=f"link_{v}_{d}_{s}_{l}")

    vd_pairs = set((v, d) for v, d, l in y.keys())
    for v, d in vd_pairs:
        model.addConstr(gp.quicksum(y[v, d, l] for l in all_locations if (v, d, l) in y) <= 1, name=f"one_loc_{v}_{d}")

    # 3. Límite de turnos máximo indicado por el voluntario por día
    for (v, d), m_shifts in volunteer_max.items():
        v_vars = [var for (v_i, d_i, s, l), var in x.items() if v_i == v and d_i == d]
        if v_vars:
            model.addConstr(gp.quicksum(v_vars) <= m_shifts, name=f"max_s_{v}_{d}")

    # 4. Sucesión estricta de turnos en el mismo día
    for (v, d) in vd_pairs:
        z = {}
        for s in SLOTS_ORDER:
            v_s_vars = [var for (v_i, d_i, s_i, l), var in x.items() if v_i == v and d_i == d and s_i == s]
            z[s] = gp.quicksum(v_s_vars) if v_s_vars else 0

        starts = []
        for i, s in enumerate(SLOTS_ORDER):
            val_s = z[s]
            val_prev = z[SLOTS_ORDER[i-1]] if i > 0 else 0
            
            if isinstance(val_s, int) and val_s == 0 and isinstance(val_prev, int) and val_prev == 0:
                continue
                
            start_var = model.addVar(vtype=GRB.CONTINUOUS, lb=0, ub=1, name=f"start_{v}_{d}_{i}")
            model.addConstr(start_var >= val_s - val_prev, name=f"start_def_{v}_{d}_{i}")
            starts.append(start_var)

        if starts:
            model.addConstr(gp.quicksum(starts) <= 1, name=f"consec_{v}_{d}")

    model.optimize()
    if model.Status not in (GRB.OPTIMAL, GRB.TIME_LIMIT, GRB.SUBOPTIMAL):
        return pd.DataFrame(columns=["volunteer", "date", "slot", "location"])

    rows = [{"volunteer": v, "date": d, "slot": s, "location": l} for (v, d, s, l), var in x.items() if var.X > 0.5]
    return pd.DataFrame(rows, columns=["volunteer", "date", "slot", "location"]).sort_values(["date", "slot", "location", "volunteer"]).reset_index(drop=True)