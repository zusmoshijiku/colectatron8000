import pandas as pd
import gurobipy as gp
from gurobipy import GRB
from collections import defaultdict
from typing import Dict, List, Tuple

SLOTS_ORDER = [
    "7:00 - 8:30", "8:30 - 10:00", "10:00 - 11:30", "11:30 - 13:00",
    "13:00 - 14:30", "14:30 - 16:00", "16:00 - 17:30", "17:30 - 19:00", "19:00 - 20:00"
]
## CAPACIDAD MÁXIMA POR BLOQUE POR ESQUINA, AJUSTAR SI NO ENCUENTRA SOLUCIÓN
CAPACIDAD_MAXIMA = 5
RECOMPENSA_COBERTURA = 1000
RECOMPENSA_JEFE = 500

SLOT_WEIGHTS = {
    "7:00 - 8:30": 8, "8:30 - 10:00": 10, "10:00 - 11:30": 10, "11:30 - 13:00": 10,
    "13:00 - 14:30": 10, "14:30 - 16:00": 10, "16:00 - 17:30": 10,
    "17:30 - 19:00": 10, "19:00 - 20:00": 5
}

def build_and_solve(availability: pd.DataFrame, volunteers: List[str], 
                    blocks: List[Tuple], volunteer_max: Dict[Tuple, int], 
                    all_locations: List[str], roles_jefatura: Dict[str, bool],
                    time_limit: float = 300.0, mip_gap: float = 0.01) -> pd.DataFrame:
    
    model = gp.Model("Colectatron_Standard")
    model.setParam("OutputFlag", 1)
    model.setParam("TimeLimit", time_limit)
    model.setParam("MIPGap", mip_gap)

    # ==========================================
    # VARIABLES DE DECISIÓN
    # ==========================================
    x = {} # x[voluntario, dia, horario, esquina] -> 1 si es asignado
    for v, d, s, l in set(availability.itertuples(index=False, name=None)):
        x[v, d, s, l] = model.addVar(vtype=GRB.BINARY, name=f"x_{v}_{d}_{s}_{l}")

    if not x:
        return pd.DataFrame(columns=["volunteer", "date", "slot", "location"])

    is_covered = {} # 1 si la esquina l está operativa en el día d y horario s
    dsl_set = set((d, s, l) for v, d, s, l in x.keys())
    for d, s, l in dsl_set:
        is_covered[d, s, l] = model.addVar(vtype=GRB.BINARY, name=f"cov_{d}_{s}_{l}")

    y = {} # 1 si el voluntario v asiste a la esquina l en el día d (para agrupar turnos en la misma esquina)
    for v, d, s, l in x.keys():
        if (v, d, l) not in y:
            y[v, d, l] = model.addVar(vtype=GRB.BINARY, name=f"y_{v}_{d}_{l}")

    # ==========================================
    # FUNCIÓN OBJETIVO
    # ==========================================
    # Maximizar cobertura de esquinas (fuerte) + preferencia de horarios (leve)
    obj_expr = gp.quicksum(
        (SLOT_WEIGHTS.get(s, 10) + (RECOMPENSA_JEFE if roles_jefatura.get(v, False) else 0)) * var 
        for (v, d, s, l), var in x.items()
    )
    obj_expr += gp.quicksum(RECOMPENSA_COBERTURA * var for var in is_covered.values())
    model.setObjective(obj_expr, GRB.MAXIMIZE)

    # ==========================================
    # RESTRICCIONES
    # ==========================================
    
    # 1. Vincular Cobertura y Capacidad Máxima
    block_vars = defaultdict(list)
    for (v, d, s, l), var in x.items():
        block_vars[d, s, l].append(var)
        
    for (d, s, l), vars_in_block in block_vars.items():
        suma_voluntarios = gp.quicksum(vars_in_block)
        model.addConstr(is_covered[d, s, l] <= suma_voluntarios, name=f"link_cov_{d}_{s}_{l}")
        model.addConstr(suma_voluntarios <= CAPACIDAD_MAXIMA, name=f"cap_max_{d}_{s}_{l}")

    # 2. Protección del Comisionado (Nadie solo excepto Jefes)
    for (v, d, s, l), var in x.items():
        is_jefe = roles_jefatura.get(v, False)
        if not is_jefe:
            # Si se asigna este comisionado, la suma del RESTO de personas debe ser >= 1
            otros_vars = [x[u, d, s, l] for u in volunteers if u != v and (u, d, s, l) in x]
            if otros_vars:
                model.addConstr(var <= gp.quicksum(otros_vars), name=f"no_solo_{v}_{d}_{s}_{l}")
            else:
                # Si no hay nadie más disponible en este bloque, el comisionado no puede ir
                model.addConstr(var == 0, name=f"no_solo_{v}_{d}_{s}_{l}_imposible")

    # 3. Permanencia en una sola esquina por día
    for (v, d, s, l), var in x.items():
        model.addConstr(var <= y[v, d, l], name=f"link_y_{v}_{d}_{s}_{l}")

    for v, d in set((v, d) for v, d, l in y.keys()):
        model.addConstr(gp.quicksum(y[v, d, l] for l in all_locations if (v, d, l) in y) <= 1, name=f"una_esquina_{v}_{d}")

    # 4. Límite máximo de turnos por voluntario por día
    for (v, d), m_shifts in volunteer_max.items():
        v_vars = [var for (vol, dia, s, l), var in x.items() if vol == v and dia == d]
        if v_vars:
            model.addConstr(gp.quicksum(v_vars) <= m_shifts, name=f"max_turnos_{v}_{d}")

    # 5. Sucesión estricta de turnos continuos
    for v, d in set((v, d) for v, d, s, l in x.keys()):
        z = {s: gp.quicksum([var for (vol, dia, horario, l), var in x.items() if vol == v and dia == d and horario == s]) for s in SLOTS_ORDER}
        starts = []
        for i, s in enumerate(SLOTS_ORDER):
            val_s = z[s]
            val_prev = z[SLOTS_ORDER[i-1]] if i > 0 else 0
            
            # Crear variable continua solo si hay cambio de estado posible
            if not (isinstance(val_s, int) and val_s == 0 and isinstance(val_prev, int) and val_prev == 0):
                start_var = model.addVar(vtype=GRB.CONTINUOUS, lb=0, ub=1, name=f"start_{v}_{d}_{i}")
                model.addConstr(start_var >= val_s - val_prev, name=f"start_def_{v}_{d}_{i}")
                starts.append(start_var)

        if starts:
            model.addConstr(gp.quicksum(starts) <= 1, name=f"turnos_continuos_{v}_{d}")

    # ==========================================
    # OPTIMIZACIÓN Y EXTRACCIÓN
    # ==========================================
    model.optimize()
    if model.Status not in (GRB.OPTIMAL, GRB.TIME_LIMIT, GRB.SUBOPTIMAL):
        print(f"El solver no encontró solución óptima. Estado: {model.Status}")
        return pd.DataFrame(columns=["volunteer", "date", "slot", "location"])

    rows = [{"volunteer": v, "date": d, "slot": s, "location": l} 
            for (v, d, s, l), var in x.items() if var.X > 0.5]
    
    return pd.DataFrame(rows).sort_values(["date", "slot", "location", "volunteer"]).reset_index(drop=True)