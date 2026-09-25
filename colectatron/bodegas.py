"""Asignación de casas-bodega a los supermercados abiertos cada día.

Es un paso posterior al solver: para cada (día, supermercado) con turnos se
elige la casa más cercana en auto entre quienes pueden guardar insumos ese día.
Sin tiempos de traslado, se prefiere una casa de la misma comuna. A igualdad,
se reparte la carga entre casas.
"""

from __future__ import annotations

import pandas as pd

from .config import ConfigColecta
from .formulario import Voluntario
from .texto import normalizar

COLUMNAS_BODEGAS = ["Día", "Lugar", "Casa-bodega", "Teléfono", "Dirección", "Comuna", "Minutos en auto", "Misma comuna"]


def asignar_bodegas(
    config: ConfigColecta,
    voluntarios: list[Voluntario],
    asignaciones: pd.DataFrame,
    minutos: dict[tuple[str, str], float] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """`minutos[(lugar, id_persona)]` son los minutos en auto desde el lugar a la casa (opcional)."""
    minutos = minutos or {}
    filas, avisos = [], []
    if asignaciones.empty:
        return pd.DataFrame(columns=COLUMNAS_BODEGAS), avisos

    abiertos = asignaciones[["dia", "lugar"]].drop_duplicates()
    for d in config.dias:
        candidatos = [v for v in voluntarios if d in v.bodega]
        carga = {v.id: 0 for v in candidatos}
        for lugar in [x for x in config.nombres_lugares if ((abiertos.dia == d) & (abiertos.lugar == x)).any()]:
            if not candidatos:
                avisos.append(f"{d}: nadie puede guardar insumos; falta casa-bodega para {lugar}.")
                filas.append({"Día": d, "Lugar": lugar, "Casa-bodega": "⚠️ Sin casa-bodega"})
                continue
            comuna_lugar = normalizar(config.lugar(lugar).comuna)
            con_tiempo = all((lugar, v.id) in minutos for v in candidatos)
            if con_tiempo:
                claves = [(minutos[lugar, v.id], carga[v.id], v.fila) for v in candidatos]
            else:
                claves = [(normalizar(v.comuna) != comuna_lugar, carga[v.id], v.fila) for v in candidatos]
            elegido = candidatos[claves.index(min(claves))]
            carga[elegido.id] += 1
            misma = bool(comuna_lugar) and normalizar(elegido.comuna) == comuna_lugar
            filas.append(
                {
                    "Día": d,
                    "Lugar": lugar,
                    "Casa-bodega": elegido.nombre,
                    "Teléfono": elegido.telefono,
                    "Dirección": elegido.direccion,
                    "Comuna": elegido.comuna,
                    "Minutos en auto": round(minutos[lugar, elegido.id]) if (lugar, elegido.id) in minutos else None,
                    "Misma comuna": "Sí" if misma else "No",
                }
            )
            if not misma and comuna_lugar:
                avisos.append(f"{d}: la casa-bodega de {lugar} ({elegido.nombre}) está en otra comuna.")
    return pd.DataFrame(filas, columns=COLUMNAS_BODEGAS), avisos
