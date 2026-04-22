import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import re
import sys

def generar_heatmap(input_csv="data/assignments.csv", output_png="cronograma_visualizacion.png"):
    try:
        df = pd.read_csv(input_csv)
    except FileNotFoundError:
        print(f"Error: No se encontró {input_csv}.")
        return

    # Limpieza de espacios en los horarios para asegurar coincidencia
    df['slot'] = df['slot'].apply(lambda x: re.sub(r'\s+', ' ', str(x)).strip())
    df['slot'] = df['slot'].str.replace(r'\s*-\s*', ' - ', regex=True)

    # Orden cronológico estricto
    slots_order = [
        "7:00 - 8:30", "8:30 - 10:00", "10:00 - 11:30", "11:30 - 13:00",
        "13:00 - 14:30", "14:30 - 16:00", "16:00 - 17:30", "17:30 - 19:00", "19:00 - 20:00"
    ]

    # Obtener los días únicos de forma dinámica
    dias = df['date'].unique()
    
    # Contar la cantidad de voluntarios por bloque
    counts = df.groupby(['date', 'location', 'slot']).size().reset_index(name='volunteers')

    fig, axes = plt.subplots(len(dias), 1, figsize=(14, 5 * len(dias)))
    
    # Manejo en caso de que solo se asigne un día (axes no sería un arreglo)
    if len(dias) == 1:
        axes = [axes]

    for i, date in enumerate(dias):
        # Crear matriz pivot
        pivot = counts[counts['date'] == date].pivot(index='location', columns='slot', values='volunteers').fillna(0)
        
        # Asegurar que todas las columnas existan, incluso si el horario quedó vacío
        for col in slots_order:
            if col not in pivot.columns:
                pivot[col] = 0
                
        # Reordenar las columnas
        pivot = pivot.reindex(columns=slots_order, fill_value=0)
        
        # Generar mapa de calor
        sns.heatmap(pivot, annot=True, cmap="YlGnBu", vmin=0, vmax=4, ax=axes[i], 
                    linewidths=.5, cbar_kws={'label': 'N° Voluntarios'})
        axes[i].set_title(f'Ocupación de Esquinas - {date}', fontsize=16, fontweight='bold')
        axes[i].set_xlabel('Bloque Horario', fontsize=12)
        axes[i].set_ylabel('Esquina', fontsize=12)
        axes[i].tick_params(axis='x', rotation=45)

    plt.tight_layout()
    plt.savefig(output_png, dpi=300)
    print(f"Visualización generada con éxito en: {output_png}")

if __name__ == "__main__":
    archivo_entrada = sys.argv[1] if len(sys.argv) > 1 else "data/assignments.csv"
    generar_heatmap(input_csv=archivo_entrada)