from __future__ import annotations

import re
import unicodedata

import pandas as pd


def _leer_tabla(ruta_archivo: str) -> pd.DataFrame:
    ruta = str(ruta_archivo).lower()
    if ruta.endswith(".xlsx") or ruta.endswith(".xls"):
        return pd.read_excel(ruta_archivo)
    # sep=None lets pandas infer delimiters such as ';' from Google Forms exports.
    return pd.read_csv(ruta_archivo, sep=None, engine="python")


def _normalizar_nombre_columna(nombre: str) -> str:
    return str(nombre).strip().lower().replace("_", " ")


def _clave_texto(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    texto = texto.lower()
    texto = re.sub(r"[^a-z0-9 ]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _es_si(valor: object) -> bool:
    clave = _clave_texto(valor)
    return "si" in clave or "s" == clave


def _split_horarios(texto: object) -> list[str]:
    if pd.isna(texto):
        return []
    partes = [p.strip() for p in re.split(r"\s*,\s*", str(texto)) if p.strip()]
    # Keep likely time slots and ignore generic sentences.
    return [p for p in partes if ":" in p and "-" in p]


def _detectar_columna_id(df: pd.DataFrame, col_id_objetivo: str) -> str | None:
    if col_id_objetivo in df.columns:
        return col_id_objetivo

    candidatos = {
        "voluntario",
        "volunteer",
        "nombre",
        "name",
        "id",
        "legajo",
    }
    for c in df.columns:
        if _clave_texto(c) in candidatos:
            return c
    return None


def _detectar_columna_confirmacion(df: pd.DataFrame) -> str | None:
    for c in df.columns:
        clave = _clave_texto(c)
        if "puedes ir a la colecta" in clave:
            return c
    return None


def _columnas_horarios(df: pd.DataFrame, col_horarios_objetivo: str) -> list[str]:
    if col_horarios_objetivo in df.columns:
        return [col_horarios_objetivo]

    columnas = []
    for c in df.columns:
        clave = _clave_texto(c)
        if "horario te acomoda" in clave or "horarios" in clave or "horario" in clave:
            columnas.append(c)
    return columnas


def _renombrar_columnas_entrada(
    df: pd.DataFrame,
    col_id_objetivo: str,
    col_horarios_objetivo: str,
) -> pd.DataFrame:
    """Map input schema to canonical columns and build Horarios when split in many columns."""
    col_id_detectada = _detectar_columna_id(df, col_id_objetivo)
    if col_id_detectada is None:
        raise ValueError(
            "No se encontro una columna de identificador de voluntario. "
            f"Columnas disponibles: {list(df.columns)}"
        )

    if col_id_detectada != col_id_objetivo:
        df = df.rename(columns={col_id_detectada: col_id_objetivo})

    columnas_horarios = _columnas_horarios(df, col_horarios_objetivo)
    if not columnas_horarios:
        raise ValueError(
            "No se encontro ninguna columna de horarios. "
            f"Columnas disponibles: {list(df.columns)}"
        )

    if col_horarios_objetivo not in df.columns:
        df[col_horarios_objetivo] = ""

    # Keep only volunteers who confirmed attendance when the field exists.
    col_confirmacion = _detectar_columna_confirmacion(df)
    if col_confirmacion is not None:
        df = df[df[col_confirmacion].apply(_es_si)].copy()

    df[col_horarios_objetivo] = df[columnas_horarios].fillna("").astype(str).agg(
        ", ".join, axis=1
    )

    return df


def procesar_disponibilidad(ruta_archivo, col_id, col_horarios):
    df = _leer_tabla(ruta_archivo)
    df = _renombrar_columnas_entrada(df, col_id, col_horarios)

    V = []

    # Extraer todos los bloques horarios únicos
    horarios_unicos = set()
    for respuestas in df[col_horarios].dropna():
        for h in _split_horarios(respuestas):
            horarios_unicos.add(h)

    H_nombres = sorted(horarios_unicos)
    H = list(range(len(H_nombres)))
    mapa_horarios = {nombre: i for i, nombre in enumerate(H_nombres)}

    # Construir matriz D[v][h]
    D = {}
    for _, fila in df.iterrows():
        v = fila[col_id]
        if pd.isna(v):
            continue

        id_vol = str(v).strip()
        if not id_vol:
            continue

        if id_vol not in D:
            D[id_vol] = [0] * len(H)

        for h in _split_horarios(fila[col_horarios]):
            if h in mapa_horarios:
                D[id_vol][mapa_horarios[h]] = 1

    # Keep only volunteers with at least one available slot to avoid trivial infeasibilities.
    V = [v for v, disp in D.items() if sum(disp) > 0]
    D = {v: D[v] for v in V}

    return V, H, D, mapa_horarios
