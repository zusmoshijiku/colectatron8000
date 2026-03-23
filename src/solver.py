from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

import pandas as pd
import gurobipy as gp
from gurobipy import GRB


def get_mock_corner_data() -> Tuple[List[str], Dict[str, int], int, int]:
	"""Mock data requested for corners, capacities and volunteer shift bounds."""
	E = ["Esquina Norte", "Esquina Centro", "Esquina Sur"]
	C = {
		"Esquina Norte": 2,
		"Esquina Centro": 3,
		"Esquina Sur": 2,
	}
	min_turnos = 1
	max_turnos = 9
	return E, C, min_turnos, max_turnos


def solve_volunteer_assignment(
	V: Sequence[str],
	H: Sequence[int],
	D: Dict[str, List[int]],
	E: Sequence[str],
	C: Dict[str, int],
	min_turnos: int,
	max_turnos: int,
) -> Tuple[gp.Model, gp.tupledict]:
	"""Build and solve the binary assignment model."""
	model = gp.Model("volunteer_assignment")

	# x[v,e,h] = 1 if volunteer v is assigned to corner e in slot h
	x = model.addVars(V, E, H, vtype=GRB.BINARY, name="x")

	# 1) Availability: x[v,e,h] <= D[v][h]
	model.addConstrs(
		(x[v, e, h] <= D[v][h] for v in V for e in E for h in H),
		name="availability",
	)

	# 2) At most one corner per volunteer per slot
	model.addConstrs(
		(gp.quicksum(x[v, e, h] for e in E) <= 1 for v in V for h in H),
		name="one_corner_per_slot",
	)

	# 3) Capacity per corner and slot
	model.addConstrs(
		(gp.quicksum(x[v, e, h] for v in V) <= C[e] for e in E for h in H),
		name="corner_capacity",
	)

	# 4) Min/max shifts per volunteer
	model.addConstrs(
		(
			gp.quicksum(x[v, e, h] for e in E for h in H) >= min_turnos
			for v in V
		),
		name="min_shifts",
	)
	model.addConstrs(
		(
			gp.quicksum(x[v, e, h] for e in E for h in H) <= max_turnos
			for v in V
		),
		name="max_shifts",
	)

	# Objective: maximize assigned shifts
	model.setObjective(
		gp.quicksum(x[v, e, h] for v in V for e in E for h in H),
		GRB.MAXIMIZE,
	)

	model.optimize()
	return model, x


def build_schedule_dataframe(
	model: gp.Model,
	x: gp.tupledict,
	V: Sequence[str],
	E: Sequence[str],
	H: Sequence[int],
	slot_labels: Sequence[str],
) -> pd.DataFrame:
	"""Return rows where x[v,e,h] > 0.5 as a pandas DataFrame."""
	if model.Status not in {GRB.OPTIMAL, GRB.SUBOPTIMAL, GRB.TIME_LIMIT}:
		return pd.DataFrame(columns=["Voluntario", "Esquina", "Horario"])

	rows = []
	for v in V:
		for e in E:
			for h in H:
				if x[v, e, h].X > 0.5:
					rows.append(
						{
							"Voluntario": v,
							"Esquina": e,
							"Horario": slot_labels[h],
						}
					)

	return pd.DataFrame(rows, columns=["Voluntario", "Esquina", "Horario"])


def export_schedule(schedule_df: pd.DataFrame, output_csv_path: str) -> None:
	schedule_df.to_csv(output_csv_path, index=False, encoding="utf-8")
