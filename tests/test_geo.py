"""Pruebas del módulo de mapa sin salir a internet (se simulan las respuestas)."""

from __future__ import annotations

import requests

from colectatron import geo


class _Resp:
    def __init__(self, datos):
        self._datos = datos

    def raise_for_status(self):
        pass

    def json(self):
        return self._datos


def test_geocodificar(monkeypatch):
    llamadas = []

    def falso_get(url, params=None, headers=None, timeout=None):
        llamadas.append(params["q"])
        return _Resp([{"lat": "-33.45", "lon": "-70.60"}])

    monkeypatch.setattr(geo.requests, "get", falso_get)
    punto = geo.geocodificar("Av. Grecia 1800", "Ñuñoa", pausa_s=0)
    assert punto == geo.Punto(-33.45, -70.60)
    assert llamadas == ["Av. Grecia 1800, Ñuñoa, Chile"]
    assert geo.geocodificar("", "Ñuñoa", pausa_s=0) is None


def test_geocodificar_sin_resultado_o_sin_red(monkeypatch):
    monkeypatch.setattr(geo.requests, "get", lambda *a, **k: _Resp([]))
    assert geo.geocodificar("No existe 123", pausa_s=0) is None

    def sin_red(*a, **k):
        raise requests.ConnectionError

    monkeypatch.setattr(geo.requests, "get", sin_red)
    assert geo.geocodificar("Av. Grecia 1800", pausa_s=0) is None


def test_tiempos_osrm_y_respaldo(monkeypatch):
    a, b = geo.Punto(-33.45, -70.60), geo.Punto(-33.46, -70.62)
    monkeypatch.setattr(geo.requests, "get", lambda *a, **k: _Resp({"code": "Ok", "durations": [[600.0]]}))
    assert geo.tiempos_auto([a], [b]) == ([[10.0]], True)

    def sin_red(*a, **k):
        raise requests.ConnectionError

    monkeypatch.setattr(geo.requests, "get", sin_red)
    matriz, real = geo.tiempos_auto([a], [b])
    assert not real and 3 < matriz[0][0] < 10  # ~2,2 km en línea recta
