import pandas as pd
import pathlib
import sys
from openpyxl.styles import Alignment

def crear_planner_excel(input_csv="data/assignments.csv", output_excel="data/planner_colecta.xlsx"):
    try:
        df = pd.read_csv(input_csv)
    except FileNotFoundError:
        print(f"Error: No se encontró el archivo {input_csv}. Corre el solver primero.")
        return

    # Formatear la etiqueta de cada voluntario combinando nombre y contacto
    def formatear_contacto(row):
        nombre = str(row['volunteer']).replace('_', ' ') # Recuperar espacios en el nombre
        tel = str(row['telefono']).replace('.0', '') if pd.notna(row['telefono']) else ""
        correo = str(row['correo']) if pd.notna(row['correo']) else ""
        
        lineas = [f"👤 {nombre}"]
        if tel and tel != "nan": lineas.append(f"📞 {tel}")
        if correo and correo != "nan": lineas.append(f"✉️ {correo}")
        
        return "\n".join(lineas)

    df['info_contacto'] = df.apply(formatear_contacto, axis=1)

    # Limpiar horarios para alinear correctamente
    df['slot'] = df['slot'].astype(str).str.replace(r'\s+', ' ', regex=True).str.strip()
    df['slot'] = df['slot'].str.replace(r'\s*-\s*', ' - ', regex=True)

    slots_order = [
        "7:00 - 8:30", "8:30 - 10:00", "10:00 - 11:30", "11:30 - 13:00",
        "13:00 - 14:30", "14:30 - 16:00", "16:00 - 17:30", "17:30 - 19:00", "19:00 - 20:00"
    ]

    # Agrupar múltiples voluntarios en la misma celda, separados por un doble salto de línea
    agg_df = df.groupby(['date', 'slot', 'location'])['info_contacto'].apply(lambda x: '\n\n'.join(x)).reset_index()

    pathlib.Path(output_excel).parent.mkdir(parents=True, exist_ok=True)
    
    with pd.ExcelWriter(output_excel, engine='openpyxl') as writer:
        for date in df['date'].unique():
            df_day = agg_df[agg_df['date'] == date]
            pivot = df_day.pivot(index='slot', columns='location', values='info_contacto')
            pivot = pivot.reindex(slots_order).fillna('')
            
            sheet_name = str(date).replace(":", "").replace("/", "")[:31]
            pivot.to_excel(writer, sheet_name=sheet_name)
            
            # --- Ajustes visuales (Wrap Text) ---
            worksheet = writer.sheets[sheet_name]
            
            # Ajustar ancho de las columnas (Esquinas)
            for col in worksheet.columns:
                worksheet.column_dimensions[col[0].column_letter].width = 35
                
            # Habilitar "Ajustar texto" y alinear arriba para todas las celdas
            for row in worksheet.iter_rows():
                for cell in row:
                    cell.alignment = Alignment(wrap_text=True, vertical='top')
            
    print(f"✅ Planner generado exitosamente en: {output_excel}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        crear_planner_excel(input_csv=sys.argv[1])
    else:
        crear_planner_excel()