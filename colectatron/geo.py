"""Ubicaciones en el mapa y tiempos de traslado en auto.

Usa servicios gratuitos de OpenStreetMap:

* Nominatim para convertir direcciones en coordenadas (máximo 1 consulta por segundo).
* OSRM (servidor público de demostración) para tiempos de viaje en auto.

Si OSRM no responde, se estima el tiempo con la distancia en línea recta.
Estas funciones envían direcciones a terceros: la app pide confirmación antes.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

import requests

NOMINATIM = "https://nominatim.openstreetmap.org/search"
OSRM = "https://router.project-osrm.org/table/v1/driving/"
AGENTE = "colectatron8000 (asignacion de turnos de voluntariado)"

# Para la estimación sin OSRM: calles no son rectas (factor 1,3) y ~25 km/h en ciudad.
FACTOR_RUTA = 1.3
KMH_CIUDAD = 25


@dataclass(frozen=True)
class Punto:
    lat: float
    lon: float


def geocodificar(direccion: str, comuna: str = "", pais: str = "Chile", pausa_s: float = 1.0) -> Punto | None:
    """Coordenadas de una dirección, o None si no se encontró."""
    consulta = ", ".join(p for p in (direccion, comuna, pais) if p and p.strip())
    if not direccion.strip():
        return None
    try:
        resp = requests.get(
            NOMINATIM,
            params={"q": consulta, "format": "json", "limit": 1},
            headers={"User-Agent": AGENTE},
            timeout=15,
        )
        resp.raise_for_status()
        datos = resp.json()
    except (requests.RequestException, ValueError):
        return None
    finally:
        time.sleep(pausa_s)  # política de uso de Nominatim
    if not datos:
        return None
    return Punto(float(datos[0]["lat"]), float(datos[0]["lon"]))


def distancia_km(a: Punto, b: Punto) -> float:
    r = 6371.0
    dlat = math.radians(b.lat - a.lat)
    dlon = math.radians(b.lon - a.lon)
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(a.lat)) * math.cos(math.radians(b.lat)) * math.sin(dlon / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(h))


def minutos_estimados(a: Punto, b: Punto) -> float:
    return distancia_km(a, b) * FACTOR_RUTA / KMH_CIUDAD * 60


def tiempos_auto(origenes: list[Punto], destinos: list[Punto]) -> tuple[list[list[float]], bool]:
    """Matriz de minutos en auto origen→destino. El booleano indica si viene de OSRM (True) o es estimada."""
    if not origenes or not destinos:
        return [], False
    puntos = origenes + destinos
    coords = ";".join(f"{p.lon:.6f},{p.lat:.6f}" for p in puntos)
    params = {
        "sources": ";".join(str(i) for i in range(len(origenes))),
        "destinations": ";".join(str(len(origenes) + j) for j in range(len(destinos))),
        "annotations": "duration",
    }
    try:
        resp = requests.get(OSRM + coords, params=params, headers={"User-Agent": AGENTE}, timeout=20)
        resp.raise_for_status()
        datos = resp.json()
        if datos.get("code") == "Ok":
            return [[(s or 0) / 60 for s in fila] for fila in datos["durations"]], True
    except (requests.RequestException, ValueError, KeyError):
        pass
    return [[minutos_estimados(a, b) for b in destinos] for a in origenes], False
