import argparse
import pathlib
import sys
import pandas as pd
from typing import List, Optional

def reporte_asignacion(assignments_df: pd.DataFrame, 
                       lista_total_voluntarios: List[str], 
                       lista_filtro: Optional[List[str]] = None) -> None:
    """
    Calcula e imprime el porcentaje de voluntarios que recibieron al menos un turno.
    
    :param assignments_df: DataFrame con las asignaciones (salida del solver).
    :param lista_total_voluntarios: Lista con los nombres de todos los que indicaron disponibilidad.
    :param lista_filtro: (Opcional) Lista de nombres para limitar el cálculo solo a ese grupo.
    """
    # 1. Obtener quiénes recibieron al menos un turno
    asignados_unicos = set(assignments_df["volunteer"].astype(str).unique())
    todos_unicos = set(str(v) for v in lista_total_voluntarios)

    # 2. Aplicar el filtro opcional si se entrega una lista
    if lista_filtro is not None:
        set_filtro = set(str(v) for v in lista_filtro)
        # Reducir el universo solo a los que están en la lista filtro
        todos_unicos = todos_unicos.intersection(set_filtro)
        asignados_unicos = asignados_unicos.intersection(set_filtro)
        print("\n--- REPORTE DE ASIGNACIÓN (FILTRADO) ---")
    else:
        print("\n--- REPORTE DE ASIGNACIÓN (GLOBAL) ---")

    # 3. Calcular métricas
    total = len(todos_unicos)
    if total == 0:
        print("Error: No hay voluntarios en la lista proporcionada o el filtro está vacío.")
        return

    # Cuántos de los asignados pertenecen al universo que estamos analizando
    asignados_efectivos = len(asignados_unicos.intersection(todos_unicos))
    
    porcentaje = (asignados_efectivos / total) * 100
    sin_asignar = total - asignados_efectivos

    # 4. Imprimir resultados
    print(f"Total de personas analizadas: {total}")
    print(f"Personas con al menos 1 turno: {asignados_efectivos}")
    print(f"Personas sin turnos: {sin_asignar}")
    print(f"Porcentaje de éxito: {porcentaje:.2f}%")
    
    if sin_asignar > 0:
        personas_fuera = todos_unicos - asignados_unicos
        print("\nLista de personas que quedaron sin turno:")
        for persona in sorted(personas_fuera):
            print(f" - {persona.replace('_', ' ')}")



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

    ## trabajo futuro: añadir lista de correos de gente que se bajó, para hacer reasignación.
    ## y que luego se tome en cuenta en data_processing, para botar esas filas.
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

    reporte_asignacion(assignments, problem["volunteers"])
    # Opcional: Usar la función para ver solo a los Jefes/Comisionados
    # lista_jefes = [v for v, es_jefe in problem["roles_jefatura"].items() if es_jefe]
    # reporte_asignacion(assignments, problem["volunteers"], lista_filtro=lista_jefes)
    return 0

if __name__ == "__main__":
    sys.exit(main())