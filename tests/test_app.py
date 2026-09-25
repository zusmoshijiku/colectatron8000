"""Prueba de humo de la app: carga ejemplo, asigna y ofrece la descarga."""

from __future__ import annotations

import pathlib

from streamlit.testing.v1 import AppTest

APP = str(pathlib.Path(__file__).resolve().parents[1] / "streamlit_app.py")


def _boton(at, texto):
    return next(b for b in at.button if texto in b.label)


def test_flujo_con_datos_de_ejemplo():
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    assert not at.exception

    _boton(at, "ejemplo").click()
    at.run()
    assert not at.exception
    assert at.metric[0].value == "60"

    _boton(at, "Asignar turnos").click()
    at.run()
    assert not at.exception
    etiquetas = [m.label for m in at.metric]
    assert "Personas con turno" in etiquetas
    assert not at.error


def test_pide_contrasena_si_esta_configurada():
    at = AppTest.from_file(APP)
    at.secrets["password"] = "secreta"
    at.run()
    assert len(at.text_input) == 1 and not at.tabs
    at.text_input[0].input("otra").run()
    assert at.error
    at.text_input[0].input("secreta").run()
    assert at.tabs


def test_mapa_de_casas_bodega(monkeypatch):
    from colectatron import geo

    coordenadas = iter(range(1000))

    def falso_geocodificar(direccion, comuna="", **_):
        i = next(coordenadas)
        return geo.Punto(-33.45 + i * 0.001, -70.60 - i * 0.001)

    monkeypatch.setattr(geo, "geocodificar", falso_geocodificar)
    monkeypatch.setattr(geo, "tiempos_auto", lambda o, d: ([[5.0 + j for j in range(len(d))] for _ in o], True))

    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    _boton(at, "ejemplo").click()
    at.run()
    _boton(at, "Asignar turnos").click()
    at.run()
    _boton(at, "Ubicar en el mapa").click()
    at.run()
    assert not at.exception
    assert not at.error
