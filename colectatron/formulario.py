"""Lectura de las respuestas del Google Form.

Reconoce las columnas por el texto de la pregunta (no por su posición), así que
no hace falta reordenar nada a mano. Cada problema encontrado se reporta como
un `Aviso` con la fila del archivo, en vez de caerse o adivinar en silencio.

Hay dos formatos:

* ``unificado``: la plantilla nueva (cuadrícula de bloques × días). Ver
  ``docs/formulario.md`` o la pestaña "Formulario" de la app.
* ``antiguo``: el Form de financiamiento 2025, leído por posición de columna.
"""

from __future__ import annotations

import io
import pathlib
import re
from dataclasses import dataclass, field

import pandas as pd

from .config import ConfigColecta
from .texto import es_si, normalizar, normalizar_bloque, parece_bloque, vacio

FORMATO_UNIFICADO = "unificado"
FORMATO_ANTIGUO = "antiguo"


@dataclass
class Voluntario:
    id: str
    fila: int
    nombre: str
    correo: str = ""
    telefono: str = ""
    rol: str = ""
    es_jefe: bool = False
    disponibilidad: dict[str, list[str]] = field(default_factory=dict)  # día -> bloques
    max_turnos: dict[str, int] = field(default_factory=dict)  # día -> máximo
    lugares: dict[str, list[str]] = field(default_factory=dict)  # día -> lugares aceptados
    auto: set[str] = field(default_factory=set)  # días con auto
    bodega: set[str] = field(default_factory=set)  # días en que puede guardar insumos
    direccion: str = ""
    comuna: str = ""
    comentarios: str = ""

    @property
    def tiene_disponibilidad(self) -> bool:
        return any(self.disponibilidad.values())


@dataclass
class Aviso:
    mensaje: str
    fila: int | None = None
    persona: str = ""
    nivel: str = "aviso"  # "aviso" o "error"


@dataclass
class Lectura:
    voluntarios: list[Voluntario]  # dicen que asisten (o marcaron bloques)
    no_asisten: list[Voluntario]
    avisos: list[Aviso]
    total_respuestas: int

    def avisos_df(self) -> pd.DataFrame:
        return pd.DataFrame(
            [{"Nivel": a.nivel, "Fila": a.fila, "Persona": a.persona, "Problema": a.mensaje} for a in self.avisos],
            columns=["Nivel", "Fila", "Persona", "Problema"],
        )


# ---------------------------------------------------------------------------
# Lectura del archivo
# ---------------------------------------------------------------------------


def leer_tabla(archivo, nombre: str | None = None) -> pd.DataFrame:
    """Lee un .xlsx o .csv tal como lo descarga Google Forms/Sheets.

    `archivo` puede ser una ruta o un objeto con los bytes (lo que entrega
    ``st.file_uploader``). Todo se lee como texto para no perder ceros ni el
    "+" de los teléfonos.
    """
    if isinstance(archivo, (str, pathlib.Path)):
        nombre = nombre or str(archivo)
        datos = pathlib.Path(archivo).read_bytes()
    else:
        nombre = nombre or getattr(archivo, "name", "")
        datos = archivo.read() if hasattr(archivo, "read") else bytes(archivo)

    if nombre.lower().endswith((".xlsx", ".xlsm", ".xls")):
        df = pd.read_excel(io.BytesIO(datos), dtype=str)
    else:
        df = None
        for codificacion in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                texto = datos.decode(codificacion)
            except UnicodeDecodeError:
                continue
            df = pd.read_csv(io.StringIO(texto), sep=None, engine="python", dtype=str)
            break
        if df is None:
            raise ValueError("No se pudo leer el archivo: codificación desconocida.")

    df.columns = [str(c).strip() for c in df.columns]
    return df.dropna(how="all").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Detección de columnas (formato unificado)
# ---------------------------------------------------------------------------

_GRILLA = re.compile(r"^(.*?)\s*\[(.+)\]\s*$")


@dataclass(frozen=True)
class Campo:
    etiqueta: str
    claves: tuple[str, ...]  # prefijos de palabra que deben aparecer
    excluir: tuple[str, ...] = ()
    obligatorio: bool = False


# El orden importa: "Dirección de correo electrónico" debe caer en correo antes
# que en dirección, y "Dirección donde guardarías…" en dirección antes que en bodega.
CAMPOS: dict[str, Campo] = {
    "correo": Campo("Correo", ("correo", "email", "e-mail", "mail"), obligatorio=True),
    "nombre": Campo("Nombre", ("nombre",), excluir=("correo",), obligatorio=True),
    "telefono": Campo("Teléfono", ("telefono", "celular", "whatsapp", "fono")),
    "asiste": Campo("¿Asiste?", ("asisti", "vas a ir", "puedes ir", "asistencia")),
    "rol": Campo("Rol", ("rol", "eres")),
    "direccion": Campo("Dirección de la casa-bodega", ("direccion", "domicilio")),
    "bodega": Campo("Días que puede guardar insumos", ("guardar", "bodega")),
    "auto": Campo("Días con auto", ("auto",)),
    "comuna": Campo("Comuna", ("comuna",)),
    "lugares": Campo("Lugares", ("lugar", "esquina", "supermercado"), excluir=("bloque", "maximo")),
    "comentarios": Campo("Comentarios", ("comentario", "observacion")),
}

GRILLAS = {
    "bloques": "Cuadrícula de bloques × días",
    "maximo": "Cuadrícula de máximo de bloques por día",
}


def _contiene_palabra(texto_norm: str, prefijos: tuple[str, ...]) -> bool:
    return any(re.search(r"\b" + re.escape(normalizar(p)), texto_norm) for p in prefijos)


def grillas_del_archivo(columnas: list[str]) -> dict[str, dict[str, str]]:
    """Agrupa columnas "Pregunta [Fila]" por pregunta: {pregunta: {fila: columna}}."""
    grillas: dict[str, dict[str, str]] = {}
    for col in columnas:
        m = _GRILLA.match(col)
        if m:
            grillas.setdefault(m.group(1).strip(), {})[m.group(2).strip()] = col
    return grillas


def detectar_columnas(df: pd.DataFrame) -> dict[str, str | None]:
    """Propone qué columna corresponde a cada campo. Las grillas se identifican por su pregunta."""
    columnas = list(df.columns)
    grillas = grillas_del_archivo(columnas)
    en_grilla = {c for filas in grillas.values() for c in filas.values()}
    simples = [c for c in columnas if c not in en_grilla]

    mapa: dict[str, str | None] = {}
    usadas: set[str] = set()
    for clave, campo in CAMPOS.items():
        mapa[clave] = None
        for col in simples:
            n = normalizar(col)
            if col in usadas or not _contiene_palabra(n, campo.claves):
                continue
            if campo.excluir and _contiene_palabra(n, campo.excluir):
                continue
            mapa[clave] = col
            usadas.add(col)
            break

    mapa["bloques"] = None
    mapa["maximo"] = None
    for pregunta, filas in grillas.items():
        if all(parece_bloque(f) for f in filas) and mapa["bloques"] is None:
            mapa["bloques"] = pregunta
        elif not any(parece_bloque(f) for f in filas) and mapa["maximo"] is None:
            mapa["maximo"] = pregunta
    return mapa


def dias_de_grilla(df: pd.DataFrame, pregunta: str) -> list[str]:
    """Días que aparecen marcados en la cuadrícula de bloques, en orden de aparición."""
    columnas = grillas_del_archivo(list(df.columns)).get(pregunta, {}).values()
    vistos: dict[str, str] = {}
    for col in columnas:
        for valor in df[col].dropna():
            for parte in str(valor).split(","):
                parte = parte.strip()
                if parte and normalizar(parte) not in vistos:
                    vistos[normalizar(parte)] = parte
    return list(vistos.values())


def bloques_de_grilla(df: pd.DataFrame, pregunta: str) -> list[str]:
    return list(grillas_del_archivo(list(df.columns)).get(pregunta, {}).keys())


# ---------------------------------------------------------------------------
# Interpretación de respuestas
# ---------------------------------------------------------------------------


def _texto(fila: pd.Series, col: str | None) -> str:
    if not col or col not in fila.index or vacio(fila[col]):
        return ""
    return str(fila[col]).strip()


def _telefono(valor: str) -> str:
    valor = valor.strip()
    return valor[:-2] if valor.endswith(".0") else valor


def dias_mencionados(valor, dias: list[str]) -> list[str]:
    """Días de la configuración que aparecen en una respuesta ("Sábado, Domingo")."""
    n = normalizar(valor)
    return [d for d in dias if re.search(r"\b" + re.escape(normalizar(d)) + r"\b", n)]


def es_jefe(rol: str, roles_jefe: list[str]) -> bool:
    n = normalizar(rol)
    return bool(n) and any(re.search(r"\b" + re.escape(normalizar(r)) + r"\b", n) for r in roles_jefe if normalizar(r))


def interpretar_lugares(valor, lugares: list[str]) -> tuple[list[str], list[str]]:
    """Devuelve (lugares elegidos, partes no reconocidas). Vacío o "Donde me necesiten" = todos."""
    n = normalizar(valor)
    if not n or "donde me necesiten" in n or "cualquier" in n or "todos" in n:
        return list(lugares), []
    elegidos = [lugar for lugar in lugares if normalizar(lugar) in n]
    resto = n
    for lugar in elegidos:
        resto = resto.replace(normalizar(lugar), " ")
    sobras = [p.strip() for p in re.split(r"[,;]", resto) if p.strip()]
    return elegidos, sobras


def interpretar_maximo(valor, sin_limite: int) -> int | None:
    """Número de bloques máximo. None si no se entiende."""
    n = normalizar(valor)
    if not n or "sin limite" in n or "todo" in n or "cualquier" in n or "lo que" in n:
        return sin_limite
    m = re.search(r"\d+", n)
    return int(m.group()) if m else None


def _bloques_de_texto(valor, bloques: list[str]) -> tuple[list[str], list[str]]:
    """Para el formato antiguo: "10:00 - 11:30, 11:30 - 13:00" o "Todo el día"."""
    n = normalizar(valor)
    if not n:
        return [], []
    if "todo el dia" in n or "cualquier horario" in n:
        return list(bloques), []
    por_clave = {normalizar_bloque(b): b for b in bloques}
    elegidos, sobras = [], []
    for parte in str(valor).split(","):
        clave = normalizar_bloque(parte)
        if not clave:
            continue
        if clave in por_clave:
            elegidos.append(por_clave[clave])
        else:
            sobras.append(parte.strip())
    return [b for b in bloques if b in elegidos], sobras


def _registrar(
    v: Voluntario,
    asiste: bool | None,
    por_id: dict[str, Voluntario],
    no_asisten: list[Voluntario],
    avisos: list[Aviso],
) -> None:
    """Agrega a la persona a la lista que corresponde, resolviendo respuestas repetidas."""
    anteriores = [x for x in no_asisten if x.id == v.id]
    if v.id in por_id:
        anteriores.append(por_id.pop(v.id))
    for anterior in anteriores:
        if anterior in no_asisten:
            no_asisten.remove(anterior)
        avisos.append(
            Aviso(f"Respondió más de una vez; se usa la respuesta de la fila {v.fila}.", anterior.fila, anterior.nombre)
        )

    if asiste is False:
        if v.tiene_disponibilidad:
            avisos.append(
                Aviso("Dijo que no asiste pero marcó horarios; se considera que no asiste.", v.fila, v.nombre)
            )
        v.disponibilidad = {}
        no_asisten.append(v)
        return
    if not v.tiene_disponibilidad:
        avisos.append(Aviso("No marcó ningún horario válido; quedará sin turno.", v.fila, v.nombre))
    por_id[v.id] = v


def _identificar(correo: str, nombre: str) -> str:
    return normalizar(correo) if correo else "nombre:" + normalizar(nombre)


def _avisar_nombres_repetidos(voluntarios: list[Voluntario], avisos: list[Aviso]) -> None:
    por_nombre: dict[str, list[Voluntario]] = {}
    for v in voluntarios:
        por_nombre.setdefault(normalizar(v.nombre), []).append(v)
    for grupo in por_nombre.values():
        if len(grupo) > 1:
            for v in grupo:
                avisos.append(
                    Aviso(
                        "Hay otra persona con el mismo nombre (distinto correo); en el planner se distinguen por correo.",
                        v.fila,
                        v.nombre,
                    )
                )


def leer_unificado(df: pd.DataFrame, config: ConfigColecta, mapa: dict[str, str | None]) -> Lectura:
    avisos: list[Aviso] = []
    for clave in ("nombre", "bloques"):
        if not mapa.get(clave):
            etiqueta = CAMPOS[clave].etiqueta if clave in CAMPOS else GRILLAS[clave]
            avisos.append(Aviso(f"No se encontró la columna «{etiqueta}». Elígela a mano.", nivel="error"))
    if any(a.nivel == "error" for a in avisos):
        return Lectura([], [], avisos, len(df))

    grillas = grillas_del_archivo(list(df.columns))
    por_clave_bloque = {normalizar_bloque(b): b for b in config.bloques}
    columnas_bloque: dict[str, str] = {}
    for fila_grilla, col in grillas.get(mapa["bloques"], {}).items():
        bloque = por_clave_bloque.get(normalizar_bloque(fila_grilla))
        if bloque:
            columnas_bloque[bloque] = col
        else:
            avisos.append(Aviso(f"El bloque «{fila_grilla}» del formulario no está en la configuración; se ignora."))
    faltantes = [b for b in config.bloques if b not in columnas_bloque]
    if faltantes:
        avisos.append(Aviso(f"Estos bloques de la configuración no están en el formulario: {', '.join(faltantes)}."))

    columnas_max: dict[str, str] = {}
    if mapa.get("maximo"):
        for fila_grilla, col in grillas.get(mapa["maximo"], {}).items():
            for dia in dias_mencionados(fila_grilla, config.dias):
                columnas_max[dia] = col

    dias_desconocidos: set[str] = set()
    lugares_desconocidos: dict[str, int] = {}
    por_id: dict[str, Voluntario] = {}
    no_asisten: list[Voluntario] = []

    for i, fila in df.iterrows():
        num = int(i) + 2  # fila en Excel/Sheets (la 1 es el encabezado)
        nombre = _texto(fila, mapa.get("nombre"))
        correo = _texto(fila, mapa.get("correo"))
        if not nombre and not correo:
            continue
        nombre = nombre or correo

        rol = _texto(fila, mapa.get("rol"))
        v = Voluntario(
            id=_identificar(correo, nombre),
            fila=num,
            nombre=nombre,
            correo=correo,
            telefono=_telefono(_texto(fila, mapa.get("telefono"))),
            rol=rol,
            es_jefe=es_jefe(rol, config.roles_jefe),
            direccion=_texto(fila, mapa.get("direccion")),
            comuna=_texto(fila, mapa.get("comuna")),
            comentarios=_texto(fila, mapa.get("comentarios")),
        )

        for bloque, col in columnas_bloque.items():
            valor = _texto(fila, col)
            dias = dias_mencionados(valor, config.dias)
            for parte in valor.split(","):
                if parte.strip() and not dias_mencionados(parte, config.dias):
                    dias_desconocidos.add(parte.strip())
            for dia in dias:
                v.disponibilidad.setdefault(dia, []).append(bloque)
        v.disponibilidad = {
            d: [b for b in config.bloques if b in v.disponibilidad[d]] for d in config.dias if d in v.disponibilidad
        }

        for dia, bloques in v.disponibilidad.items():
            maximo = len(bloques)
            if dia in columnas_max:
                valor = _texto(fila, columnas_max[dia])
                leido = interpretar_maximo(valor, len(config.bloques))
                if leido is None:
                    avisos.append(
                        Aviso(
                            f"No se entiende el máximo de bloques del {dia} («{valor}»); se usa sin límite.",
                            num,
                            nombre,
                        )
                    )
                else:
                    maximo = leido
            v.max_turnos[dia] = maximo

        elegidos, sobras = interpretar_lugares(_texto(fila, mapa.get("lugares")), config.nombres_lugares)
        for s in sobras:
            lugares_desconocidos[s] = lugares_desconocidos.get(s, 0) + 1
        if not elegidos:
            avisos.append(
                Aviso("Ninguno de los lugares elegidos está en la configuración; se consideran todos.", num, nombre)
            )
            elegidos = config.nombres_lugares
        v.lugares = {d: list(elegidos) for d in v.disponibilidad}

        if mapa.get("auto"):
            v.auto = set(dias_mencionados(_texto(fila, mapa["auto"]), config.dias))
        if mapa.get("bodega"):
            v.bodega = set(dias_mencionados(_texto(fila, mapa["bodega"]), config.dias))
            if v.bodega and not v.direccion:
                avisos.append(Aviso("Puede guardar insumos pero no indicó dirección.", num, nombre))

        asiste = None
        if mapa.get("asiste"):
            valor = _texto(fila, mapa["asiste"])
            asiste = es_si(valor)
            if asiste is None and valor:
                avisos.append(
                    Aviso(f"No se entiende la respuesta de asistencia («{valor}»); se usan sus horarios.", num, nombre)
                )
        _registrar(v, asiste, por_id, no_asisten, avisos)

    if dias_desconocidos:
        avisos.append(
            Aviso(
                "Hay días en el formulario que no están en la configuración (se ignoran): "
                + ", ".join(sorted(dias_desconocidos))
                + "."
            )
        )
    for texto, n in sorted(lugares_desconocidos.items()):
        avisos.append(
            Aviso(f"Lugar no reconocido «{texto}» ({n} respuesta(s)); revisa los nombres en la configuración.")
        )

    voluntarios = list(por_id.values())
    _avisar_nombres_repetidos(voluntarios, avisos)
    return Lectura(voluntarios, no_asisten, avisos, len(df))


# ---------------------------------------------------------------------------
# Formato antiguo de financiamiento (por posición de columna)
# ---------------------------------------------------------------------------

COLUMNAS_ANTIGUAS = [
    "Correo",
    "Nombre",
    "Teléfono",
    "Asistencia",
    "Día",
    "Turnos día 1",
    "Horarios día 1",
    "Esquina día 1",
    "Turnos día 2",
    "Horarios día 2",
    "Esquina día 2",
    "Turnos día 1 (ambos)",
    "Horarios día 1 (ambos)",
    "Turnos día 2 (ambos)",
    "Horarios día 2 (ambos)",
    "Esquina (ambos)",
    "Rol",
]


def leer_antiguo(df: pd.DataFrame, config: ConfigColecta) -> Lectura:
    """Form de financiamiento 2025: 17 columnas en un orden fijo (ver README antiguo)."""
    avisos: list[Aviso] = []
    if df.shape[1] < len(COLUMNAS_ANTIGUAS):
        avisos.append(
            Aviso(
                f"El formato antiguo necesita al menos {len(COLUMNAS_ANTIGUAS)} columnas y el archivo tiene {df.shape[1]}.",
                nivel="error",
            )
        )
    if len(config.dias) != 2:
        avisos.append(Aviso("El formato antiguo solo admite colectas de exactamente 2 días.", nivel="error"))
    if avisos:
        return Lectura([], [], avisos, len(df))

    dia1, dia2 = config.dias
    por_id: dict[str, Voluntario] = {}
    no_asisten: list[Voluntario] = []

    for i, fila in df.iterrows():
        num = int(i) + 2
        c = [fila.iloc[k] for k in range(len(COLUMNAS_ANTIGUAS))]
        correo = "" if vacio(c[0]) else str(c[0]).strip()
        nombre = "" if vacio(c[1]) else str(c[1]).strip()
        if not nombre and not correo:
            continue
        nombre = nombre or correo
        rol = "" if vacio(c[16]) else str(c[16]).strip()
        v = Voluntario(
            id=_identificar(correo, nombre),
            fila=num,
            nombre=nombre,
            correo=correo,
            telefono=_telefono("" if vacio(c[2]) else str(c[2])),
            rol=rol,
            es_jefe=es_jefe(rol, config.roles_jefe),
        )

        dia = normalizar(c[4])
        if "ambos" in dia:
            opciones = [(dia1, c[11], c[12], c[15]), (dia2, c[13], c[14], c[15])]
        elif normalizar(dia1) in dia:
            opciones = [(dia1, c[5], c[6], c[7])]
        elif normalizar(dia2) in dia:
            opciones = [(dia2, c[8], c[9], c[10])]
        else:
            opciones = []

        for d, turnos, horarios, esquina in opciones:
            bloques, sobras = _bloques_de_texto(horarios, config.bloques)
            if sobras:
                avisos.append(Aviso(f"Horarios no reconocidos el {d}: {', '.join(sobras)}.", num, nombre))
            if not bloques:
                continue
            maximo = interpretar_maximo(turnos, len(config.bloques))
            if maximo is None:
                avisos.append(
                    Aviso(f"No se entiende la cantidad de turnos del {d} («{turnos}»); se usa sin límite.", num, nombre)
                )
                maximo = len(bloques)
            elegidos, sobras = interpretar_lugares(esquina, config.nombres_lugares)
            if sobras or not elegidos:
                avisos.append(Aviso(f"Esquina no reconocida el {d} («{esquina}»); se consideran todas.", num, nombre))
                elegidos = elegidos or config.nombres_lugares
            v.disponibilidad[d] = bloques
            v.max_turnos[d] = maximo
            v.lugares[d] = elegidos

        asiste = es_si(c[3])
        if asiste is None and not vacio(c[3]):
            avisos.append(
                Aviso(f"No se entiende la respuesta de asistencia («{c[3]}»); se usan sus horarios.", num, nombre)
            )
        _registrar(v, asiste, por_id, no_asisten, avisos)

    voluntarios = list(por_id.values())
    _avisar_nombres_repetidos(voluntarios, avisos)
    return Lectura(voluntarios, no_asisten, avisos, len(df))


def leer_respuestas(
    df: pd.DataFrame,
    config: ConfigColecta,
    formato: str = FORMATO_UNIFICADO,
    mapa: dict[str, str | None] | None = None,
) -> Lectura:
    if formato == FORMATO_ANTIGUO:
        return leer_antiguo(df, config)
    return leer_unificado(df, config, mapa if mapa is not None else detectar_columnas(df))


def valores_de_rol(df: pd.DataFrame, columna: str | None) -> list[str]:
    """Respuestas distintas de la pregunta de rol, para elegir cuáles son jefes."""
    if not columna or columna not in df.columns:
        return []
    return sorted({str(x).strip() for x in df[columna].dropna() if str(x).strip()})
