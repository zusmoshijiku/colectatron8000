"""Informe de la asignación en LaTeX, con sus figuras, empaquetado en un .zip.

El .zip trae `informe.tex` y la carpeta `figuras/` (PNG). Se compila con pdflatex
o se sube tal cual a Overleaf (New project → Upload project).

Para no repartir datos de contacto, el informe lleva nombres pero no teléfonos
ni correos: esos están en el planner en Excel.
"""

from __future__ import annotations

import io
import math
import re
import unicodedata
import zipfile
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator

from . import geo
from .config import TIPO_INSUMOS, ConfigColecta
from .formulario import Lectura, Voluntario
from .reportes import cobertura, por_persona, rango_horario, resumen, sin_turno
from .solver import Resultado
from .texto import minutos_inicio

MESES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]
AZUL, CELESTE, NARANJO, ROJO, GRIS = "#2b6cb0", "#a3c4e6", "#dd6b20", "#c53030", "#718096"
ESTILOS_DIA = ["-", "--", ":", "-."]
ANCHO_CM = 17.0  # ancho de texto con márgenes de 2 cm en A4

# ---------------------------------------------------------------------------
# Textos
# ---------------------------------------------------------------------------

# Además de ASCII, pdflatex (utf8 + T1) entiende estos sin paquetes extra.
_PERMITIDOS = set("áéíóúÁÉÍÓÚñÑüÜ¡¿«»°")
_ESPECIALES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def limpio(valor) -> str:
    """Texto sin emojis ni caracteres que pdflatex o matplotlib no saben dibujar."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    partes = []
    for c in str(valor):
        if (ord(c) < 128 and (c.isprintable() or c.isspace())) or c in _PERMITIDOS:
            partes.append(c)
        else:  # "é" compuesto, letras de otros idiomas: su base ASCII; emojis: nada
            partes.append(unicodedata.normalize("NFKD", c).encode("ascii", "ignore").decode())
    return re.sub(r"\s+", " ", "".join(partes)).strip()


def tex(valor) -> str:
    """Texto escapado para LaTeX."""
    return "".join(_ESPECIALES.get(c, c) for c in limpio(valor))


def _mpl(valor) -> str:
    return limpio(valor).replace("$", r"\$")


def _num(x: float, decimales: int = 1) -> str:
    return f"{x:.{decimales}f}".replace(".", ",")


def _fecha(d: date) -> str:
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def _duracion_min(bloque: str) -> int:
    partes = str(bloque).split("-")
    if len(partes) != 2:
        return 0
    a, b = minutos_inicio(partes[0]), minutos_inicio(partes[1])
    return b - a if a is not None and b is not None and b > a else 0


def _tramos(indices: list[int]) -> list[list[int]]:
    tramos: list[list[int]] = []
    for i in sorted(indices):
        if tramos and tramos[-1][-1] == i - 1:
            tramos[-1].append(i)
        else:
            tramos.append([i])
    return tramos


# ---------------------------------------------------------------------------
# Figuras
# ---------------------------------------------------------------------------


def _png(fig: Figure) -> bytes:
    salida = io.BytesIO()
    fig.savefig(salida, format="png", dpi=200, bbox_inches="tight", facecolor="white")
    return salida.getvalue()


def _mostrar_autos(config: ConfigColecta) -> bool:
    return config.reglas.auto_al_cierre or config.reglas.autos_durante_el_dia


def figura_ocupacion(config: ConfigColecta, asignaciones: pd.DataFrame, dia: str) -> bytes:
    """Mapa de calor lugares × bloques: personas asignadas, coloreado según la capacidad."""
    lugares, bloques = config.nombres_lugares, config.bloques
    cob = cobertura(config, asignaciones)
    matriz = np.zeros((len(lugares), len(bloques)))
    for fila in cob[cob["dia"] == dia].itertuples():
        matriz[lugares.index(fila.lugar), bloques.index(fila.bloque)] = fila.personas
    capacidad = np.array([[config.lugar(lugar).capacidad] for lugar in lugares], dtype=float)
    con_auto = set()
    if not asignaciones.empty and _mostrar_autos(config):
        del_dia = asignaciones[(asignaciones["dia"] == dia) & asignaciones["auto"].astype(bool)]
        con_auto = set(zip(del_dia["lugar"], del_dia["bloque"], strict=True))

    fig = Figure(figsize=(max(6.0, 0.85 * len(bloques) + 3), 0.55 * len(lugares) + 1.3))
    ax = fig.subplots()
    ax.imshow(matriz / capacidad, cmap="Blues", vmin=0, vmax=1.15, aspect="auto")
    for i, lugar in enumerate(lugares):
        for j, bloque in enumerate(bloques):
            n = int(matriz[i, j])
            lleno = n / capacidad[i, 0] > 0.6
            ax.text(
                j, i, str(n) if n else "–", ha="center", va="center", fontsize=9, color="white" if lleno else "black"
            )
            if (lugar, bloque) in con_auto:
                ax.plot(j + 0.36, i - 0.3, marker="o", markersize=4, color=NARANJO)
    ax.set_xticks(range(len(bloques)), [b.replace(" - ", "\n") for b in bloques], fontsize=7.5)
    ax.set_yticks(range(len(lugares)), [_mpl(lugar) for lugar in lugares], fontsize=8.5)
    ax.xaxis.tick_top()
    ax.set_xticks(np.arange(-0.5, len(bloques)), minor=True)
    ax.set_yticks(np.arange(-0.5, len(lugares)), minor=True)
    ax.grid(which="minor", color="white", linewidth=2)
    ax.tick_params(which="both", length=0)
    for borde in ax.spines.values():
        borde.set_visible(False)
    return _png(fig)


def figura_oferta(config: ConfigColecta, voluntarios: list[Voluntario], asignaciones: pd.DataFrame, dia: str) -> bytes:
    """Por bloque: cuántas personas lo ofrecieron, cuántas quedaron asignadas y la capacidad total."""
    bloques = config.bloques
    ofrecieron = [
        sum(1 for v in voluntarios if v.max_turnos.get(dia, 0) > 0 and b in v.disponibilidad.get(dia, []))
        for b in bloques
    ]
    del_dia = asignaciones[asignaciones["dia"] == dia] if not asignaciones.empty else asignaciones
    asignadas = [del_dia[del_dia["bloque"] == b]["id"].nunique() if not del_dia.empty else 0 for b in bloques]
    capacidad = sum(lugar.capacidad for lugar in config.lugares)

    fig = Figure(figsize=(max(6.0, 0.75 * len(bloques) + 2), 3.0))
    ax = fig.subplots()
    x = np.arange(len(bloques))
    ancho = 0.38
    ax.bar(x - ancho / 2, ofrecieron, ancho, color=CELESTE, label="Ofrecieron el bloque")
    ax.bar(x + ancho / 2, asignadas, ancho, color=AZUL, label="Asignadas")
    ax.axhline(capacidad, color=GRIS, linestyle="--", linewidth=1, label=f"Capacidad total ({capacidad})")
    ax.set_xticks(x, [b.split("-")[0].strip() for b in bloques], fontsize=8)
    ax.set_ylabel("Personas", fontsize=9)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.tick_params(labelsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=8, ncol=3, loc="lower center", bbox_to_anchor=(0.5, 1.0))
    return _png(fig)


@dataclass
class Casa:
    codigo: str
    voluntario: Voluntario
    punto: tuple[float, float] | None
    asignada: list[tuple[str, str]]  # (día, lugar)


def casas_del_informe(voluntarios: list[Voluntario], bodegas: pd.DataFrame | None, puntos: dict | None) -> list[Casa]:
    """Casas-bodega asignadas y las demás ubicadas en el mapa, con un código corto (C1, C2…)."""
    por_nombre = {v.nombre: v for v in voluntarios}
    asignada: dict[str, list[tuple[str, str]]] = defaultdict(list)
    if bodegas is not None:
        for _, f in bodegas.iterrows():
            v = por_nombre.get(f["Casa-bodega"])
            if v is not None:
                asignada[v.id].append((f["Día"], f["Lugar"]))
    ubicadas = (puntos or {}).get("casas", {})
    elegidas = [v for v in voluntarios if v.id in asignada] + [
        v for v in voluntarios if v.id not in asignada and ubicadas.get(v.id)
    ]
    return [Casa(f"C{i}", v, ubicadas.get(v.id), asignada.get(v.id, [])) for i, v in enumerate(elegidas, 1)]


def figura_mapa(
    config: ConfigColecta,
    casas: list[Casa],
    puntos: dict,
    teselas: Callable | None = geo.fondo_mapa,
) -> tuple[bytes, bool] | None:
    """Mapa de lugares y casas-bodega con la asignación de cada día. El booleano dice si tiene fondo de OSM."""
    lugares = {n: geo.mercator(*p) for n, p in puntos.get("lugares", {}).items() if p}
    ubicadas = [(c, geo.mercator(*c.punto)) for c in casas if c.punto]
    todos = list(lugares.values()) + [xy for _, xy in ubicadas]
    if not todos:
        return None
    xs, ys = [p[0] for p in todos], [p[1] for p in todos]
    margen = max(600.0, 0.12 * max(max(xs) - min(xs), max(ys) - min(ys)))
    x0, x1, y0, y1 = min(xs) - margen, max(xs) + margen, min(ys) - margen, max(ys) + margen

    alto = min(9.0, max(4.0, 7.5 * (y1 - y0) / (x1 - x0)))
    fig = Figure(figsize=(7.5, alto))
    ax = fig.subplots()
    fondo = teselas(x0, x1, y0, y1) if teselas else None
    if fondo:
        imagen, extension = fondo
        ax.imshow(imagen, extent=extension, origin="upper", zorder=0, alpha=0.85)

    for c, (cx, cy) in ubicadas:
        for dia, lugar in c.asignada:
            if lugar in lugares and dia in config.dias:
                lx, ly = lugares[lugar]
                estilo = ESTILOS_DIA[config.dias.index(dia) % len(ESTILOS_DIA)]
                ax.plot([lx, cx], [ly, cy], linestyle=estilo, color="#2d3748", linewidth=1.6, zorder=2)
    for c, (cx, cy) in ubicadas:
        color, tam = (AZUL, 70) if c.asignada else ("#a0aec0", 35)
        ax.scatter([cx], [cy], s=tam, color=color, edgecolor="white", linewidth=1, zorder=3)
        ax.annotate(c.codigo, (cx, cy), xytext=(4, -10), textcoords="offset points", fontsize=7.5, zorder=4)
    for nombre, (lx, ly) in lugares.items():
        ax.scatter([lx], [ly], s=80, marker="s", color=ROJO, edgecolor="white", linewidth=1, zorder=3)
        ax.annotate(
            _mpl(nombre),
            (lx, ly),
            xytext=(6, 6),
            textcoords="offset points",
            fontsize=8,
            zorder=4,
            bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "edgecolor": "none", "alpha": 0.8},
        )

    # Escala: en Web Mercator un metro del mapa son cos(latitud) metros reales.
    latitudes = [p[0] for p in puntos.get("lugares", {}).values() if p] + [c.punto[0] for c, _ in ubicadas]
    factor = math.cos(math.radians(sum(latitudes) / len(latitudes)))
    ancho_km = (x1 - x0) * factor / 1000
    largo = max([x for x in (0.2, 0.5, 1, 2, 5, 10, 20) if x <= ancho_km / 4] or [0.2])
    bx, by = x0 + 0.04 * (x1 - x0), y0 + 0.05 * (y1 - y0)
    ax.plot([bx, bx + largo * 1000 / factor], [by, by], color="black", linewidth=3, zorder=5)
    ax.annotate(f"{largo:g} km".replace(".", ","), (bx, by), xytext=(0, 5), textcoords="offset points", fontsize=8)
    if fondo:
        ax.text(
            0.99,
            0.01,
            geo.ATRIBUCION,
            transform=ax.transAxes,
            ha="right",
            va="bottom",
            fontsize=6,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.7, "pad": 1},
        )

    leyenda = [
        Line2D([], [], marker="s", color=ROJO, linestyle="none", label="Lugar"),
        Line2D([], [], marker="o", color=AZUL, linestyle="none", label="Casa-bodega asignada"),
    ]
    if any(not c.asignada for c, _ in ubicadas):
        leyenda.append(Line2D([], [], marker="o", color="#a0aec0", linestyle="none", label="Otra casa disponible"))
    dias_con_lineas = [d for d in config.dias if any(d == dia for c, _ in ubicadas for dia, _ in c.asignada)]
    for d in dias_con_lineas:
        estilo = ESTILOS_DIA[config.dias.index(d) % len(ESTILOS_DIA)]
        leyenda.append(Line2D([], [], color="#2d3748", linestyle=estilo, label=_mpl(d)))
    ax.legend(handles=leyenda, fontsize=7.5, loc="upper left", framealpha=0.9)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    return _png(fig), bool(fondo)


# ---------------------------------------------------------------------------
# LaTeX
# ---------------------------------------------------------------------------


def _col(ancho_cm: float, alineacion: str = "raggedright") -> str:
    return f">{{\\{alineacion}\\arraybackslash}}p{{{ancho_cm:.2f}cm}}"


def _ancho_util(columnas: int) -> float:
    """Ancho disponible para el contenido de `columnas` columnas (descuenta el espacio entre ellas)."""
    return ANCHO_CM - 0.43 * columnas


def _tabla(encabezados: list[str], filas: list[list[str]], anchos: list[float], tamano: str = r"\small") -> list[str]:
    """longtable con encabezado repetido en cada página. Las celdas ya vienen escapadas."""
    disponible = _ancho_util(len(anchos))
    if sum(anchos) > disponible:  # achica todo en proporción para no pasarse del margen
        anchos = [a * disponible / sum(anchos) for a in anchos]
    especificacion = "".join(_col(a) for a in anchos)
    lineas = [
        "{" + tamano,
        f"\\begin{{longtable}}{{@{{}}{especificacion}@{{}}}}",
        r"\toprule",
        " & ".join(f"\\textbf{{{tex(e)}}}" for e in encabezados) + r" \\",
        r"\midrule",
        r"\endhead",
        r"\bottomrule",
        r"\endfoot",
    ]
    lineas += [" & ".join(f) + r" \\" for f in filas]
    lineas += [r"\end{longtable}", "}"]
    return lineas


def _figura(archivo: str, leyenda: str, ancho: str = r"\linewidth") -> list[str]:
    return [
        r"\begin{figure}[!htbp]",
        r"\centering",
        f"\\includegraphics[width={ancho}]{{{archivo}}}",
        f"\\caption{{{leyenda}}}",
        r"\end{figure}",
    ]


def _itemize(cosas: list[str]) -> list[str]:
    return [r"\begin{itemize}", *[f"\\item {c}" for c in cosas], r"\end{itemize}"]


def armar_informe(
    config: ConfigColecta,
    lectura: Lectura,
    resultado: Resultado,
    bodegas: pd.DataFrame | None = None,
    avisos: list[str] | None = None,
    puntos: dict | None = None,
    minutos: dict[tuple[str, str], float] | None = None,
    teselas: Callable | None = geo.fondo_mapa,
    hoy: date | None = None,
) -> tuple[str, dict[str, bytes]]:
    """Devuelve el código LaTeX y las figuras (ruta dentro del .zip → PNG)."""
    vols = lectura.voluntarios
    asig = resultado.asignaciones
    avisos = resultado.avisos if avisos is None else avisos
    figuras: dict[str, bytes] = {}
    res = resumen(config, vols, asig)
    hay_jefes = bool(config.roles_jefe) or any(v.es_jefe for v in vols)
    insumos = config.tipo == TIPO_INSUMOS

    L = [
        "% Informe generado por Colectatron8000.",
        "% Compílalo con pdflatex (dos veces, para el índice) o sube el .zip completo a Overleaf.",
        r"\documentclass[11pt,a4paper]{article}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage{lmodern}",
        r"\usepackage[spanish,es-noshorthands,es-tabla,es-nodecimaldot]{babel}",
        r"\usepackage[margin=2cm]{geometry}",
        r"\usepackage{graphicx,booktabs,longtable,array}",
        r"\usepackage[hidelinks]{hyperref}",
        r"\setlength{\parindent}{0pt}",
        r"\setlength{\parskip}{5pt}",
        f"\\title{{Informe de asignación de turnos\\\\\\large {tex(config.nombre)}}}",
        r"\author{Colectatron8000}",
        f"\\date{{{_fecha(hoy or date.today())}}}",
        r"\begin{document}",
        r"\maketitle",
        r"\tableofcontents",
        "",
    ]

    # --- Resumen -------------------------------------------------------------
    horas = sum(_duracion_min(b) for b in asig["bloque"]) / 60 if not asig.empty else 0
    por_cabeza = asig.groupby("id").size().value_counts().sort_index() if not asig.empty else pd.Series(dtype=int)
    filas_resumen = [
        ("Respuestas recibidas", str(lectura.total_respuestas)),
        ("Asisten / no asisten", f"{len(vols)} / {len(lectura.no_asisten)}"),
    ]
    if hay_jefes:
        filas_resumen.append(("Jefes (" + tex(", ".join(config.roles_jefe)) + ")", str(sum(v.es_jefe for v in vols))))
    filas_resumen += [
        (
            "Personas con turno",
            f"{res['con_turno']} de {res['personas']} ({_num(res['porcentaje_con_turno'], 0)}\\,\\%)",
        ),
        ("Turnos asignados (bloques)", str(res["turnos"])),
        ("Horas de colecta (persona-hora)", _num(horas)),
        ("Bloques cubiertos", f"{res['bloques_cubiertos']} de {res['bloques_totales']}"),
    ]
    if not por_cabeza.empty:
        filas_resumen.append(
            (
                "Bloques por persona",
                "; ".join(f"{n} {'bloque' if n == 1 else 'bloques'}: {k}" for n, k in por_cabeza.items()),
            )
        )
    filas_resumen.append(
        (
            "Cálculo",
            f"{_num(resultado.segundos)} s, "
            + ("solución óptima" if resultado.optimo else "límite de tiempo (buena, quizás no la mejor)"),
        )
    )
    L += [r"\section{Resumen}", r"\begin{tabular}{@{}" + _col(7.0) + _col(9.0) + "@{}}", r"\toprule"]
    L += [f"{a} & {b} \\\\" for a, b in filas_resumen]
    L += [r"\bottomrule", r"\end{tabular}", ""]

    # --- Alertas -------------------------------------------------------------
    L += [r"\section{Alertas}"]
    L += _itemize([tex(a) for a in avisos]) if avisos else ["Sin alertas: no hay nada pendiente de la asignación."]
    revisar = list(lectura.avisos)
    if revisar:
        L += [
            r"\subsection*{Para revisar en las respuestas}",
            "No impidieron asignar, pero conviene revisarlas (la fila es la de la hoja del Form).",
        ]
        filas = [["" if a.fila is None else str(a.fila), tex(a.persona), tex(a.mensaje)] for a in revisar]
        util = _ancho_util(3)
        L += _tabla(["Fila", "Persona", "Problema"], filas, [1.1, 4.2, util - 5.3], r"\footnotesize")
    L.append("")

    # --- Ocupación -----------------------------------------------------------
    L += [
        r"\section{Ocupación por bloque}",
        "Cada celda dice cuántas personas quedaron en ese lugar y bloque; el color indica qué tan lleno está "
        "respecto de la capacidad del lugar."
        + (" El punto naranjo marca los bloques con alguien con auto." if _mostrar_autos(config) else ""),
    ]
    for i, d in enumerate(config.dias, 1):
        ruta = f"figuras/ocupacion_{i}.png"
        figuras[ruta] = figura_ocupacion(config, asig, d)
        L += _figura(ruta, f"Ocupación del {tex(d).lower()}.")

    encabezados = ["Día", "Lugar", "Horario cubierto", "Bloques", "Personas", "Turnos"]
    anchos = [1.5, 4.0, 3.4, 1.5, 1.6, 1.3]
    if config.reglas.auto_al_cierre:
        encabezados.append("Auto al cierre")
        anchos.append(1.7)
    orden = {s: i for i, s in enumerate(config.bloques)}
    sin_auto = set(resultado.cierres_sin_auto)
    filas = []
    for d in config.dias:
        for lugar in config.nombres_lugares:
            aqui = asig[(asig["dia"] == d) & (asig["lugar"] == lugar)] if not asig.empty else asig
            indices = sorted({orden[s] for s in aqui["bloque"]}) if not aqui.empty else []
            horario = ", ".join(rango_horario([config.bloques[i] for i in t]) for t in _tramos(indices)) or "Cerrado"
            fila = [
                tex(d),
                tex(lugar),
                tex(horario),
                f"{len(indices)} de {len(config.bloques)}",
                str(aqui["id"].nunique()) if not aqui.empty else "0",
                str(len(aqui)),
            ]
            if config.reglas.auto_al_cierre:
                fila.append("—" if not indices else ("No" if (d, lugar) in sin_auto else "Sí"))
            filas.append(fila)
    L += [r"\subsection*{Por lugar}"] + _tabla(encabezados, filas, anchos, r"\footnotesize") + [""]

    # --- Oferta vs asignación ------------------------------------------------
    L += [
        r"\section{Oferta y asignación por bloque}",
        "Cuántas personas ofrecieron cada bloque, cuántas quedaron asignadas y la capacidad total de los lugares. "
        "Donde las barras claras son bajas falta gente; donde las oscuras no alcanzan a las claras, "
        "hubo personas disponibles que no se usaron (por capacidad, por su máximo de bloques o de días, "
        "o porque sus bloques no eran seguidos).",
    ]
    for i, d in enumerate(config.dias, 1):
        ruta = f"figuras/oferta_{i}.png"
        figuras[ruta] = figura_oferta(config, vols, asig, d)
        L += _figura(ruta, f"Oferta y asignación del {tex(d).lower()}.")
    L.append("")

    # --- Asignación detallada --------------------------------------------------
    datos = {v.id: v for v in vols}
    marcas = []
    if hay_jefes:
        marcas.append("en negrita, jefes")
    if insumos or _mostrar_autos(config):
        marcas.append("(A), tiene auto ese día")
    L += [r"\section{Asignación por día}"]
    if marcas:
        L.append("Marcas: " + "; ".join(marcas) + ".")
    n = len(config.lugares)
    ancho_bloque = 1.7
    ancho_lugar = (_ancho_util(n + 1) - ancho_bloque) / n
    for d in config.dias:
        filas = []
        del_dia = asig[asig["dia"] == d] if not asig.empty else asig
        for s in config.bloques:
            fila = [tex(s)]
            for lugar in config.nombres_lugares:
                gente = (
                    del_dia[(del_dia["bloque"] == s) & (del_dia["lugar"] == lugar)] if not del_dia.empty else del_dia
                )
                nombres = []
                for vid in sorted(gente["id"], key=lambda i: datos[i].nombre) if not gente.empty else []:
                    v = datos[vid]
                    nombre = f"\\textbf{{{tex(v.nombre)}}}" if v.es_jefe and hay_jefes else tex(v.nombre)
                    nombres.append(nombre + (" (A)" if d in v.auto else ""))
                fila.append(r" \newline ".join(nombres))
            filas.append(fila)
        L += [f"\\subsection{{{tex(d)}}}"]
        L += _tabla(["Bloque"] + config.nombres_lugares, filas, [ancho_bloque] + [ancho_lugar] * n, r"\footnotesize")
    L.append("")

    # --- Por persona ---------------------------------------------------------
    pp = por_persona(config, vols, asig)
    filas = [
        [tex(f["Nombre"]), tex(f["Día"]), tex(f["Lugar"]), tex(f["Horario"]), str(f["Bloques"]), tex(f["Auto"])]
        for _, f in pp.iterrows()
    ]
    L += [
        r"\section{Turnos por persona}",
        "Los teléfonos y correos no se incluyen en este informe; están en el planner en Excel.",
    ]
    L += _tabla(["Nombre", "Día", "Lugar", "Horario", "Bloques", "Auto"], filas, [4.0, 1.6, 4.1, 2.4, 1.5, 1.0])
    L.append("")

    # --- Sin turno -----------------------------------------------------------
    faltan = sin_turno(vols, asig)
    L += [f"\\section{{Sin turno ({len(faltan)})}}"]
    if faltan.empty:
        L.append("Todas las personas que asisten tienen al menos un turno.")
    else:
        por_nombre = {v.nombre: v for v in vols}
        filas = []
        for _, f in faltan.iterrows():
            v = por_nombre.get(f["Nombre"])
            ofrecio = (
                ", ".join(f"{d} ({len(v.disponibilidad.get(d, []))})" for d in config.dias if v.disponibilidad.get(d))
                if v
                else ""
            )
            filas.append([tex(f["Nombre"]), tex(f["Motivo"]), tex(ofrecio) or "—"])
        L.append("Entre paréntesis, cuántos bloques ofreció cada día.")
        L += _tabla(["Nombre", "Motivo", "Ofreció"], filas, [4.5, 4.5, _ancho_util(3) - 9.0])
    L.append("")

    # --- Casas-bodega, mapa y tiempos ----------------------------------------
    if config.reglas.asignar_bodegas and bodegas is not None:
        L += [r"\section{Casas-bodega}"]
        filas = [
            [
                tex(f["Día"]),
                tex(f["Lugar"]),
                tex(f["Casa-bodega"]),
                tex(f.get("Dirección")),
                tex(f.get("Comuna")),
                "" if pd.isna(f.get("Minutos en auto")) else str(int(f["Minutos en auto"])),
            ]
            for _, f in bodegas.iterrows()
        ]
        L += _tabla(
            ["Día", "Lugar", "Casa-bodega", "Dirección", "Comuna", "Min."],
            filas,
            [1.5, 3.3, 3.0, 3.3, 2.2, 1.0],
            r"\footnotesize",
        )
        casas = casas_del_informe(vols, bodegas, puntos)
        mapa = figura_mapa(config, casas, puntos, teselas) if puntos else None
        if mapa:
            png, con_fondo = mapa
            figuras["figuras/mapa.png"] = png
            leyenda = "Lugares (cuadrados) y casas-bodega (círculos, con su código). Las líneas unen cada lugar con su casa-bodega; el estilo indica el día."
            if con_fondo:
                leyenda += r" Mapa: \copyright{} OpenStreetMap contributors."
            L += [r"\subsection{Mapa}"] + _figura("figuras/mapa.png", leyenda, r"0.95\linewidth")
            ubicadas = [c for c in casas if c.punto]
            filas = [
                [
                    c.codigo,
                    tex(c.voluntario.nombre),
                    tex(c.voluntario.comuna),
                    tex("; ".join(f"{d}: {lu}" for d, lu in c.asignada)) or "—",
                ]
                for c in ubicadas
            ]
            L += _tabla(["Código", "Casa-bodega", "Comuna", "Asignada a"], filas, [1.4, 4.2, 3.0, _ancho_util(4) - 8.6])
            no_ubicados = [n for n, p in puntos.get("lugares", {}).items() if not p]
            no_ubicados += [
                c.voluntario.nombre for c in casas if c.voluntario.id in puntos.get("casas", {}) and not c.punto
            ]
            if no_ubicados:
                L.append("No se encontraron en el mapa: " + tex(", ".join(no_ubicados)) + ". Revisa esas direcciones.")
        else:
            L.append(
                "Para incluir el mapa y los tiempos en auto, presiona «Ubicar en el mapa y calcular tiempos» "
                "en la app antes de preparar el informe."
            )

        if minutos:
            codigo = {c.voluntario.id: c.codigo for c in casas}
            asignadas = {(lu, c.voluntario.id) for c in casas for _, lu in c.asignada}
            ids = list(dict.fromkeys(vid for _, vid in minutos))
            posicion = {c.voluntario.id: i for i, c in enumerate(casas)}
            ids.sort(key=lambda vid: posicion.get(vid, len(casas)))
            lugares = [lu for lu in config.nombres_lugares if any((lu, vid) in minutos for vid in ids)]
            filas = []
            for vid in ids:
                v = datos.get(vid)
                fila = [tex(f"{codigo.get(vid, '')} {v.nombre if v else vid}".strip())]
                for lu in lugares:
                    if (lu, vid) not in minutos:
                        fila.append("")
                    else:
                        m = str(round(minutos[lu, vid]))
                        fila.append(f"\\textbf{{{m}}}" if (lu, vid) in asignadas else m)
                filas.append(fila)
            real = bool((puntos or {}).get("osrm"))
            L += [
                r"\subsection{Tiempos en auto}",
                "Minutos en auto desde cada lugar hasta cada casa "
                + ("(rutas de OSRM). " if real else "(estimados en línea recta: el servicio de rutas no respondió). ")
                + "En negrita, los trayectos de la asignación.",
            ]
            ancho_casa = 4.2
            ancho = (_ancho_util(len(lugares) + 1) - ancho_casa) / max(1, len(lugares))
            L += _tabla(["Casa-bodega"] + lugares, filas, [ancho_casa] + [ancho] * len(lugares), r"\footnotesize")
        L.append("")

    # --- Configuración -------------------------------------------------------
    r = config.reglas
    reglas = [
        ("Nadie solo (salvo jefes)", r.nadie_solo),
        ("Horario continuo por lugar", r.horario_continuo_por_lugar),
        ("Auto en el cierre", r.auto_al_cierre),
        ("Autos repartidos en el día", r.autos_durante_el_dia),
        ("Asignar casas-bodega", r.asignar_bodegas),
    ]
    tope = config.max_dias_por_persona
    L += [
        r"\section{Configuración usada}",
        f"\\textbf{{Días:}} {tex(', '.join(config.dias))}.",
        "",
        f"\\textbf{{Bloques:}} {tex(', '.join(config.bloques))}.",
        "",
        r"\textbf{Reglas:} "
        + "; ".join(f"{nombre}: {'sí' if activa else 'no'}" for nombre, activa in reglas)
        + f"; máximo de días por persona: {tope if tope > 0 else 'sin límite'}.",
    ]
    if config.roles_jefe:
        L += ["", f"\\textbf{{Roles que cuentan como jefe:}} {tex(', '.join(config.roles_jefe))}."]
    filas = [[tex(lu.nombre), tex(lu.direccion), tex(lu.comuna), str(lu.capacidad)] for lu in config.lugares]
    L += [r"\subsection*{Lugares}"]
    L += _tabla(["Lugar", "Dirección", "Comuna", "Capacidad"], filas, [5.0, 5.0, 3.0, _ancho_util(4) - 13.0])
    L += ["", r"\end{document}", ""]
    return "\n".join(L), figuras


def informe_zip(*args, **kwargs) -> bytes:
    """El .zip con `informe.tex` y `figuras/`. Recibe lo mismo que `armar_informe`."""
    codigo, figuras = armar_informe(*args, **kwargs)
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("informe.tex", codigo)
        for ruta, datos in figuras.items():
            z.writestr(ruta, datos)
    return salida.getvalue()
