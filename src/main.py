from __future__ import annotations

from pathlib import Path

from data_processing import procesar_disponibilidad
from solver import (
	build_schedule_dataframe,
	export_schedule,
	get_mock_corner_data,
	solve_volunteer_assignment,
)


def main() -> None:
	
	input_path = Path("data/data1.csv")

	col_id = "Voluntario"
	col_horarios = "Horarios"

	V, H, D, mapa_horarios = procesar_disponibilidad(
		str(input_path), col_id, col_horarios
	)

	E, C, min_turnos, max_turnos = get_mock_corner_data()

	model, x = solve_volunteer_assignment(
		V=V,
		H=H,
		D=D,
		E=E,
		C=C,
		min_turnos=min_turnos,
		max_turnos=max_turnos,
	)

	reverse_slot_map = {idx: label for label, idx in mapa_horarios.items()}
	slot_labels = [reverse_slot_map[h] for h in H]

	schedule_df = build_schedule_dataframe(
		model=model,
		x=x,
		V=V,
		E=E,
		H=H,
		slot_labels=slot_labels,
	)

	output_path = Path("data/cronograma_final.csv")
	export_schedule(schedule_df, str(output_path))

	print(f"Se exporto el cronograma con {len(schedule_df)} asignaciones en: {output_path}")


if __name__ == "__main__":
	main()
