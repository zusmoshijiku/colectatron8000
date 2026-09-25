"""Respuestas ficticias con el formato del Form unificado, para probar la app y los tests.

No contiene datos de personas reales.
"""

from __future__ import annotations

import random

import pandas as pd

from . import plantilla_form as pf
from .config import TIPO_INSUMOS, ConfigColecta

_NOMBRES = [
    "Antonia",
    "Benjamín",
    "Catalina",
    "Diego",
    "Emilia",
    "Felipe",
    "Florencia",
    "Gaspar",
    "Isidora",
    "Joaquín",
    "Josefa",
    "Martín",
    "Matilde",
    "Nicolás",
    "Rocío",
    "Tomás",
    "Valentina",
    "Vicente",
    "Amanda",
    "Cristóbal",
    "Javiera",
    "Ignacio",
    "Sofía",
    "Agustín",
]
_APELLIDOS = ["Rojas", "Muñoz", "Soto", "Contreras", "Silva", "Pérez", "Morales", "Fuentes", "Vega", "Araya"]
_CALLES = [
    ("Av. Irarrázaval 2900", "Ñuñoa"),
    ("José Pedro Alessandri 1200", "Ñuñoa"),
    ("Av. Pedro de Valdivia 3000", "Providencia"),
    ("Av. Los Leones 1500", "Providencia"),
    ("Av. Macul 3500", "Macul"),
    ("Av. Grecia 1800", "Ñuñoa"),
]


def respuestas_ejemplo(config: ConfigColecta, n: int = 40, semilla: int = 8000) -> pd.DataFrame:
    rng = random.Random(semilla)
    textos = pf.textos_de(config)
    roles = textos.roles
    insumos = config.tipo == TIPO_INSUMOS
    nombres = [f"{a} {b}" for a in _NOMBRES for b in _APELLIDOS]
    rng.shuffle(nombres)
    filas = []
    for i in range(n):
        nombre = nombres[i % len(nombres)]
        fila = dict.fromkeys(pf.encabezados(config), "")
        fila[pf.COL_MARCA] = f"2026/10/{1 + i % 5:02d} 12:{i % 60:02d}:00"
        fila[pf.COL_CORREO] = f"persona{i + 1:02d}@ejemplo.cl"
        fila[pf.P_NOMBRE] = nombre
        fila[pf.P_TELEFONO] = f"+5690000{i + 1:04d}"
        fila[pf.P_ROL] = rng.choices(roles, weights=([5, 1, 2, 2] + [1] * len(roles))[: len(roles)])[0]
        asiste = rng.random() > 0.1
        fila[pf.P_ASISTE] = textos.opcion_si if asiste else textos.opcion_no
        if textos.pregunta_chiste.strip() and textos.opciones_chiste:
            fila[textos.pregunta_chiste.strip()] = rng.choice(textos.opciones_chiste)
        if asiste:
            dias = [d for d in config.dias if rng.random() < 0.65] or [rng.choice(config.dias)]
            marcados: dict[str, list[str]] = {b: [] for b in config.bloques}
            for d in dias:
                largo = rng.randint(2, min(6, len(config.bloques)))
                inicio = rng.randint(0, len(config.bloques) - largo)
                for b in config.bloques[inicio : inicio + largo]:
                    marcados[b].append(d)
                fila[f"{pf.P_MAXIMO} [{d}]"] = rng.choice(pf.OPCIONES_MAXIMO[:3] + ["Sin límite"])
            for b, ds in marcados.items():
                fila[f"{pf.P_BLOQUES} [{b}]"] = ", ".join(ds)
            if rng.random() < 0.5:
                fila[pf.P_LUGARES] = pf.DONDE_ME_NECESITEN
            else:
                k = rng.randint(1, len(config.lugares))
                fila[pf.P_LUGARES] = ", ".join(rng.sample(config.nombres_lugares, k))
            if insumos:
                con_auto = [d for d in dias if rng.random() < 0.3]
                fila[pf.P_AUTO] = ", ".join(con_auto) if con_auto else pf.SIN_AUTO
                bodega = [d for d in config.dias if rng.random() < 0.15]
                fila[pf.P_BODEGA] = ", ".join(bodega) if bodega else pf.SIN_BODEGA
                if bodega:
                    calle, comuna = rng.choice(_CALLES)
                    fila[pf.P_DIRECCION] = f"{calle}, {comuna}"
                    fila[pf.P_COMUNA] = comuna
        filas.append(fila)
    return pd.DataFrame(filas, columns=pf.encabezados(config))
