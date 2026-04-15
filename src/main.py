import argparse
import pathlib
import sys

def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--respuestas", default="data/data4.csv", help="Ruta al archivo CSV o Excel del formulario.")
    parser.add_argument("--esquinas", default="data/esquinas.csv", help="Ruta al archivo CSV con las esquinas (columna 'location').")
    parser.add_argument("--output", default="data/assignments.csv", help="Ruta de salida.")
    parser.add_argument("--time-limit", type=float, default=300.0)
    parser.add_argument("--mip-gap", type=float, default=0.01)
    return parser.parse_args(argv)

def main(argv=None):
    args = parse_args(argv)
    from data_processing import build_problem_data
    from solver import build_and_solve

    problem = build_problem_data(args.respuestas, args.esquinas)
    

    assignments = build_and_solve(
        availability=problem["availability"],
        volunteers=problem["volunteers"],
        blocks=problem["blocks"],
        volunteer_max=problem["volunteer_max"],
        all_locations=problem["all_locations"],
        roles_jefatura=problem["roles_jefatura"],
        time_limit=args.time_limit,
        mip_gap=args.mip_gap,
    )

    if assignments.empty:
        print("No se encontraron asignaciones factibles.")
        return 1

    contact_info = problem["contacto"]
    assignments["correo"] = assignments["volunteer"].apply(lambda v: contact_info.get(v, {}).get("correo", ""))
    assignments["telefono"] = assignments["volunteer"].apply(lambda v: contact_info.get(v, {}).get("telefono", ""))

    output_path = pathlib.Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    assignments.to_csv(output_path, index=False)
    
    print(f"\n🎉 ¡Éxito! {len(assignments)} turnos asignados.")
    print(f"Asignaciones guardadas en: {output_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())