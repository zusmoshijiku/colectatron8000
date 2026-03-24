import pandas as pd
import pathlib
import sys

def crear_planner_excel(input_csv="data/assignments.csv", output_excel="data/planner_colecta.xlsx"):
    # Cargar los resultados del solver
    try:
        df = pd.read_csv(input_csv)
    except FileNotFoundError:
        print(f"Error: No se encontró el archivo {input_csv}. Corre el solver primero.")
        return

    # Limpiar espacios en blanco invisibles que pueden romper el ordenamiento
    df['slot'] = df['slot'].astype(str).str.replace(r'\s+', ' ', regex=True).str.strip()
    df['slot'] = df['slot'].str.replace(r'\s*-\s*', ' - ', regex=True)

    # Orden cronológico estricto de los horarios
    slots_order = [
        "7:00 - 8:30", "8:30 - 10:00", "10:00 - 11:30", "11:30 - 13:00",
        "13:00 - 14:30", "14:30 - 16:00", "16:00 - 17:30", "17:30 - 19:00", "19:00 - 20:00"
    ]

    # Agrupar múltiples voluntarios asignados a una misma esquina y bloque en un solo texto separado por comas
    df['volunteer'] = df['volunteer'].astype(str)
    # Si los IDs son números terminados en .0 (ej: 33.0), limpiamos ese .0
    df['volunteer'] = df['volunteer'].str.replace(r'\.0$', '', regex=True)
    
    agg_df = df.groupby(['date', 'slot', 'location'])['volunteer'].apply(lambda x: ', '.join(x)).reset_index()

    # Escribir a un archivo Excel con múltiples hojas (una por día)
    pathlib.Path(output_excel).parent.mkdir(parents=True, exist_ok=True)
    
    with pd.ExcelWriter(output_excel, engine='openpyxl') as writer:
        for date in df['date'].unique():
            # Filtrar por día
            df_day = agg_df[agg_df['date'] == date]
            
            # Pivotear: Filas = Horas, Columnas = Esquinas, Valores = Voluntarios
            pivot = df_day.pivot(index='slot', columns='location', values='volunteer')
            
            # Reindexar para forzar el orden cronológico de las horas, llenando vacíos con strings vacíos
            pivot = pivot.reindex(slots_order).fillna('')
            
            # Limpiar nombre de la hoja (Excel no permite nombres muy largos o con ciertos caracteres)
            sheet_name = str(date).replace(":", "").replace("/", "")[:31]
            
            # Exportar a Excel
            pivot.to_excel(writer, sheet_name=sheet_name)
            
    print(f"✅ Planner generado exitosamente en: {output_excel}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        crear_planner_excel(input_csv=sys.argv[1])
    else:
        crear_planner_excel()