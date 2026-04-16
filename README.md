# colectatron8000

`colectatron8000` optimiza la asignacion de voluntarios a turnos y esquinas de colecta usando `gurobipy`.

LAS COLUMNAS DEL .csv DEBEN SER:

- [0] CORREO
- [1] NOMBRE
- [2] NÚMERO DE TELÉFONO
- [3] ASISTENCIA (SI O NO)
- [4] DÍA (VIERNES, SÁBADO O AMBOS)
- [5] CANTIDAD DE TURNOS VIERNES
- [6] PREFERENCIA HORARIOS VIERNES
- [7] PREFERENCIA ESQUINA VIERNES
- [8] CANTIDAD DE TURNOS SÁBADO
- [9] PREFERENCIA HORARIOS SÁBADO
- [10] PREFERENCIA ESQUINA SÁBADO
- [11] CANTIDAD DE TURNOS VIERNES (AMBOS)
- [12] PREFERENCIA HORARIOS VIERNES (AMBOS)
- [13] CANTIDAD DE TURNOS SÁBADO (AMBOS)
- [14] PREFERENCIA HORARIOS SÁBADO (AMBOS)
- [15] PREFERENCIA ESQUINA (AMBOS)
- [16] JEFE O COMISIONADO
- [17+] CUALQUIER OTRA COSA (TDI CRUSH, AUTO, MOOD DEL DÍA, GÜAREVER. EL MODELO NO LO TOMA EN CUENTA)

SI EL ARCHIVO NO TIENE ESTA ESTRUCTURA DE COLUMNAS LA WEA SE VA A CAER, TENGA CUIDADO.

El flujo actual del proyecto es:
1. Limpiar a priori el excel de respuestas. Eliminar información personal (menos el nombre) y la parte final del auto y TDI-Crush (me dio lata que el algoritmo lo tome en cuenta) (ORDENAR LAS COLUMNAS SI ES NECESARIO, OJALÁ QUE EL FORM LO DEJE TAL CUAL SE NECESITA)
2. Leer respuestas de formulario (CSV/Excel) y transformar disponibilidad.
3. Resolver el modelo de optimizacion.
4. Exportar asignaciones a CSV.
5. (Opcional) Generar planner en Excel y visualizacion tipo mapa de calor.

El resto del readme es slop generado por copilot. No quiere decir que sea información falsa, solo que no hay que ponerle tanta atención. Es por completitud más que nada.

## Estructura del proyecto

```text
colectatron8000/
├── data/
│   ├── data1.csv
│   ├── data2.csv
│   ├── esquinas.csv
│   ├── assignments.csv
│   ├── cronograma_final.csv
│   └── planner_colecta.xlsx
├── src/
│   ├── main.py
│   ├── data_processing.py
│   ├── solver.py
│   ├── generar_planner.py
│   └── visual.ipynb
├── requirements.txt
└── README.md
```

## Requisitos

- Python 3.9+
- Licencia valida de Gurobi (academica o comercial) (Por lo menos alguno de ustedes ya dio opti)

Instalacion de dependencias:

```bash
pip install -r requirements.txt
```

## Archivos de entrada

### 1. Respuestas del formulario (`--respuestas`)

Puede ser `.csv` o `.xlsx`.

El parser actual esta adaptado al layout de exportacion de Google Forms usado en este proyecto (columnas por posicion), incluyendo campos de:
- identificador del voluntario,
- confirmacion de asistencia,
- dia(s) disponible(s),
- cantidad maxima de turnos,
- horarios disponibles,
- esquinas preferidas.

Notas:
- Para CSV se detecta automaticamente el separador (incluye casos con `;`).
- Se filtran respuestas `No...`.
- Se ignoran filas vacias y bloques horarios no validos.

### 2. Esquinas (`--esquinas`)

Archivo CSV/Excel con columna obligatoria:

- `location`: nombre de la esquina/punto de colecta.

Ejemplo (`data/esquinas.csv`):

```csv
location
Francisco Bilbao con Tobalaba
Los Leones con Eliodoro Yañez
Tobalaba con El Bosque
```

## Ejecucion del solver

Comando base:

```bash
python src/main.py
```

Argumentos disponibles:

- `--respuestas` ruta al CSV/Excel del formulario (default: `data/data2.csv`)
- `--esquinas` ruta al CSV/Excel de esquinas (default: `data/esquinas.csv`)
- `--output` ruta del CSV de salida (default: `data/assignments.csv`)
- `--time-limit` limite de tiempo del solver en segundos (default: `300`)
- `--mip-gap` tolerancia MIP (default: `0.01`)

Ejemplo:

```bash
python src/main.py --respuestas data/data1.csv --output data/assignments.csv
```

## Modelo de optimizacion (resumen)

`src/solver.py` implementa un MILP con variables binarias para asignar voluntarios a combinaciones `(fecha, horario, esquina)` segun disponibilidad.

Restricciones principales:
- Capacidad maxima por bloque (`CAPACIDAD_MAXIMA`).
- Capacidad minima condicionada por cobertura (`CAPACIDAD_MINIMA`).
- Un voluntario en una sola esquina por dia.
- Maximo de turnos por voluntario y por dia segun formulario.
- Turnos consecutivos por voluntario en el dia.

Funcion objetivo:
- Maximiza cobertura de bloques (premio alto por bloque cubierto).
- Prioriza ciertos horarios con pesos (`SLOT_WEIGHTS`).

## Salidas

### 1. CSV de asignaciones

Se genera en la ruta definida por `--output`.

Columnas:
- `volunteer`
- `date`
- `slot`
- `location`

### 2. Planner en Excel (opcional)

Script:

```bash
python src/generar_planner.py
```

Opcionalmente puedes indicar otro CSV de entrada:

```bash
python src/generar_planner.py data/assignments.csv
```

Salida por defecto:
- `data/planner_colecta.xlsx`

### 3. Visualizacion (opcional)

Notebook:
- `src/visual.ipynb`

Lee `data/assignments.csv` y genera un mapa de calor de ocupacion por esquina y bloque horario.
Ademas guarda una imagen:
- `src/cronograma_visualizacion.png`

## Problemas comunes


1. LAS COLUMNAS TE QUEDARON DESORDENADAS Y AHORA LA WEA SE CAE. TE DIJE QUE HABÍA QUE ORDENARLAS YNO PESCASTES. 
2. `ParserError` al leer CSV:
  - Usar exportacion CSV completa de Google Forms y mantener delimitador consistente.
  - Verificar que el archivo no este corrupto o truncado.
3. `GurobiError` o licencia:
  - Confirmar que la licencia de Gurobi esta activa en el equipo.
4. Salida vacia:
  - Revisar disponibilidad real de voluntarios y esquinas.
  - Probar relajando parametros (`--mip-gap`) o revisando limites de turnos.

## Licencia

MIT
