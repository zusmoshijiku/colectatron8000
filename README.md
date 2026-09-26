# Colectatron8000

Asigna voluntarios a turnos de colecta —de dinero en esquinas (financiamiento) o de insumos en supermercados—
buscando cubrir la mayor cantidad de bloques posible y respetando la disponibilidad de cada persona.

Se usa desde el navegador: se suben las respuestas del Google Form y se descarga el planner en Excel.
No hay que instalar nada, editar código ni usar la terminal.

## Cómo se usa (para la comisión)

1. **Colecta**: elige la plantilla (financiamiento o insumos) y ajusta días, bloques, lugares y reglas.
   Guarda la configuración (`.json`) para reutilizarla la próxima vez.
2. **Formulario**: ajusta los textos (invitación con ¿Cuándo? y ¿Dónde?, opciones de rol, la pregunta chiste del final
   y el link a la foto de la comisión que agradece la inscripción). En financiamiento, indica si ya salieron los
   resultados de inscripción a los trabajos (inicios de junio): antes los roles son Familia y Voluntario/a; después,
   también Staff. Luego copia el script que genera la app y pégalo en
   [script.google.com](https://script.google.com). Al ejecutarlo se crea el Google Form con las preguntas exactas que
   la app sabe leer (paso a paso en la misma pestaña). Las fotos de las opciones de la pregunta chiste se agregan
   después, en el editor del Form.
3. **Respuestas**: descarga las respuestas desde la hoja del Form (*Archivo → Descargar → Excel o CSV*) y súbelas tal cual.
   La app reconoce las columnas por el texto de la pregunta y lista todo lo que haya que revisar
   (respuestas repetidas, lugares mal escritos, gente que dijo que no va, etc.).
4. **Resultados**: presiona *Asignar turnos*. Verás la ocupación de cada bloque, los turnos por persona,
   quién quedó sin turno y los avisos (por ejemplo, un cierre sin auto). Descarga el planner en Excel.

¿Quieres probar sin datos reales? En la pestaña *Respuestas* está el botón **Probar con respuestas de ejemplo**.
También hay archivos ficticios en [`ejemplos/`](ejemplos/).

### El planner en Excel

- Una hoja por día: bloques × lugares, con nombre y teléfono (⭐ jefe, 🚗 tiene auto ese día).
- **Por persona**: dónde y a qué hora le toca a cada uno (para avisar por WhatsApp).
- **Sin turno**, **Casas-bodega** (insumos) y **Avisos**.

## Reglas del modelo

El programa resuelve un modelo de optimización entera con [HiGHS](https://highs.dev) (gratuito, sin licencia).

Siempre se cumple:

- Máximo de personas por lugar y bloque (capacidad de cada lugar).
- Cada persona está en un solo lugar por día.
- Nadie hace más bloques de los que ofreció, y sus bloques de un día son seguidos.

Reglas que se activan en la configuración:

| Regla | Financiamiento | Insumos | Qué hace |
|---|---|---|---|
| Nadie solo | ✅ | — | Solo Familia y Staff pueden quedar a cargo de una esquina; Voluntario/a nunca queda solo. En insumos no aplica: siempre hay un jefe de la comisión en el supermercado (y el Form no pregunta el rol). |
| Horario continuo por lugar | — | ✅ | Cada lugar abre en un solo tramo por día (puede partir más tarde si no hay gente en la mañana). |
| Auto en el cierre | — | ✅ | En el último bloque de cada supermercado debe haber alguien con auto para el traslado final. Si no hay, se avisa para conseguir uno. |
| Autos repartidos en el día | — | ✅ | Prefiere que haya personas con auto en varios bloques (traslados intermedios). |
| Casas-bodega | — | ✅ | Asigna a cada supermercado abierto una casa donde guardar lo recolectado, de preferencia en la misma comuna o la más cercana en auto. |

Qué busca, en orden de importancia: cubrir bloques, que cada persona tenga al menos un turno, dar prioridad a los jefes
(si corresponde) y preferir los bloques centrales del día. Los pesos se pueden cambiar en *Opciones avanzadas*.

**Mapa y tiempos de traslado**: en insumos, el botón *Ubicar en el mapa* busca las direcciones de los supermercados y
casas-bodega en OpenStreetMap, las muestra en un mapa y calcula los minutos en auto (servidor público de OSRM).
Se envían solo direcciones, sin nombres. Si el servicio de rutas no responde, los tiempos se estiman en línea recta.

**Rendimiento** (datos ficticios, computador de 4 núcleos): 100 personas y 3 supermercados ≈ 1 s;
150 personas y 5 supermercados ≈ 7 s; 250 personas y 5 supermercados ≈ 25 s. Antes de llamar al solver se arma
una solución inicial rápida, así que incluso si se alcanza el tiempo máximo siempre hay una asignación válida.

## Publicar la app (una sola vez)

La app se publica gratis en [Streamlit Community Cloud](https://streamlit.io/cloud):

1. Entra con la cuenta de GitHub que tiene acceso a este repositorio.
2. **Create app → Deploy a public app from GitHub**: repositorio `colectatron8000`, rama `main`,
   archivo principal `streamlit_app.py`. En *Advanced settings* elige Python 3.12.
3. En **Settings → Secrets** escribe la contraseña de la app:

   ```toml
   password = "una-clave-para-la-comision"
   ```

4. Opcional: en **Settings → Sharing** deja la app privada e invita a la comisión por correo.

Cada vez que se actualiza la rama `main`, la app se actualiza sola. Si nadie la usa en 12 horas se "duerme";
se despierta con un clic.

## Privacidad

- La app no guarda nada: procesa las respuestas en memoria y entrega el Excel.
- Este repositorio no debe contener datos de personas. Los archivos de `ejemplos/` son inventados.
  `data/`, `*.xlsx` y `*.csv` fuera de `ejemplos/` están en `.gitignore`.
- El Form generado incluye un aviso sobre el uso de los datos.

## Para desarrollar

Requiere Python 3.10 o superior.

```bash
pip install -r requirements-dev.txt
streamlit run streamlit_app.py   # abre la app en http://localhost:8501
pytest                           # pruebas
ruff check . && ruff format .    # estilo
```

Estructura:

```text
streamlit_app.py           Interfaz (las 4 pestañas)
colectatron/
├── config.py              Configuración de la colecta y plantillas (financiamiento / insumos)
├── formulario.py          Lectura del Form: detección de columnas, validación y avisos
├── plantilla_form.py      Preguntas del Form unificado y script de Google Apps Script que lo crea
├── solver.py              Modelo de optimización (HiGHS)
├── inicial.py             Solución inicial rápida para el solver
├── bodegas.py             Asignación de casas-bodega
├── geo.py                 Direcciones → mapa y tiempos en auto (OpenStreetMap / OSRM)
├── reportes.py            Tablas de resultados y planner en Excel
├── ejemplo.py             Generador de respuestas ficticias
└── texto.py               Normalización de textos (acentos, emojis)
tests/                     Pruebas (pytest), incluida una prueba de la app completa
ejemplos/                  Configuraciones y respuestas ficticias
```

El Form antiguo de financiamiento (17 columnas en orden fijo) se sigue pudiendo leer eligiendo
*Form antiguo* en la pestaña *Respuestas*.

## Licencia

MIT
