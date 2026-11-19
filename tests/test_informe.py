from __future__ import annotations

import io
import re
import shutil
import subprocess
import zipfile

import pytest

from colectatron import geo
from colectatron.bodegas import asignar_bodegas
from colectatron.config import config_financiamiento, config_insumos
from colectatron.ejemplo import respuestas_ejemplo
from colectatron.formulario import leer_respuestas
from colectatron.informe import armar_informe, informe_zip, tex
from colectatron.solver import resolver


def test_tex_escapa_y_quita_emojis():
    assert tex("A&B_50% $ #1 {x} ~^\\") == (
        r"A\&B\_50\% \$ \#1 \{x\} \textasciitilde{}\textasciicircum{}\textbackslash{}"
    )
    assert tex("  José 🤑  Ñuñoa ⚠️ ") == "José Ñuñoa"
    assert tex(None) == ""


def _caso(config, con_mapa: bool):
    lectura = leer_respuestas(respuestas_ejemplo(config, 40), config)
    resultado = resolver(config, lectura.voluntarios)
    puntos = minutos = None
    if con_mapa:
        lugares = {lugar.nombre: (-33.45 + 0.01 * i, -70.60 + 0.01 * i) for i, lugar in enumerate(config.lugares)}
        casas = {
            v.id: (-33.44 - 0.002 * i, -70.58 - 0.002 * i)
            for i, v in enumerate(x for x in lectura.voluntarios if x.bodega and x.direccion)
        }
        puntos = {"lugares": lugares, "casas": casas, "osrm": False}
        minutos = {
            (n, k): geo.minutos_estimados(geo.Punto(*p), geo.Punto(*q))
            for n, p in lugares.items()
            for k, q in casas.items()
        }
    bodegas, avisos = asignar_bodegas(config, lectura.voluntarios, resultado.asignaciones, minutos)
    return config, lectura, resultado, bodegas, resultado.avisos + avisos, puntos, minutos


def test_informe_de_insumos_con_mapa():
    codigo, figuras = armar_informe(*_caso(config_insumos(), con_mapa=True), teselas=None)
    for seccion in ("Resumen", "Alertas", "Ocupación por bloque", "Casas-bodega", "Tiempos en auto"):
        assert seccion in codigo
    incluidas = set(re.findall(r"\\includegraphics\[[^]]*\]\{([^}]+)\}", codigo))
    assert incluidas == set(figuras)
    assert "figuras/mapa.png" in figuras
    assert all(png.startswith(b"\x89PNG") for png in figuras.values())
    assert codigo.count(r"\begin{longtable}") == codigo.count(r"\end{longtable}")


def test_informe_sin_mapa_lo_explica():
    codigo, figuras = armar_informe(*_caso(config_insumos(), con_mapa=False), teselas=None)
    assert "figuras/mapa.png" not in figuras
    assert "Ubicar en el mapa" in codigo


def test_informe_de_financiamiento_no_tiene_bodegas():
    codigo, _ = armar_informe(*_caso(config_financiamiento(), con_mapa=False), teselas=None)
    assert "Casas-bodega" not in codigo
    assert r"\textbf{Jefes" not in codigo  # la fila del resumen se llama "Jefes (Familia, Staff)"
    assert "Jefes (Familia, Staff)" in codigo


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex no está instalado")
def test_informe_compila_con_pdflatex(tmp_path):
    datos = informe_zip(*_caso(config_insumos(), con_mapa=True), teselas=None)
    zipfile.ZipFile(io.BytesIO(datos)).extractall(tmp_path)
    proceso = subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "informe.tex"],
        cwd=tmp_path,
        capture_output=True,
        timeout=180,
    )
    assert proceso.returncode == 0, proceso.stdout.decode(errors="replace")[-2000:]
    assert (tmp_path / "informe.pdf").exists()
