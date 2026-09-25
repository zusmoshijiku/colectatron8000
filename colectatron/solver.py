"""Modelo de asignación de turnos (programación entera) resuelto con HiGHS.

Variables principales
    x[v, d, s, l]  1 si la persona v hace el bloque s del día d en el lugar l
    c[d, s, l]     1 si ese bloque queda cubierto (al menos una persona)
    y[v, d, l]     1 si la persona v está en el lugar l el día d
    u[v]           1 si la persona v recibe al menos un turno

Restricciones siempre activas
    * capacidad máxima por lugar y bloque
    * una persona está en un solo lugar por día
    * nadie hace más bloques de los que ofreció ese día
    * los bloques de una persona en un día son seguidos

Reglas activables (ver `config.Reglas`)
    * nadie solo: quien no es jefe no puede quedar solo en un bloque
    * horario continuo por lugar: cada lugar abre en un solo tramo por día
    * auto al cierre: en el último bloque abierto de cada lugar hay alguien con auto
      (regla blanda: si no se puede, se castiga y se avisa)
    * autos durante el día: premia bloques con alguien con auto
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field

import highspy
import numpy as np
import pandas as pd

from .config import ConfigColecta
from .formulario import Voluntario
from .inicial import solucion_inicial

COLUMNAS_ASIGNACION = ["id", "nombre", "dia", "bloque", "lugar", "auto", "jefe"]


@dataclass
class Resultado:
    asignaciones: pd.DataFrame
    estado: str
    optimo: bool
    segundos: float
    avisos: list[str] = field(default_factory=list)
    cierres_sin_auto: list[tuple[str, str]] = field(default_factory=list)  # (día, lugar)

    @property
    def vacio(self) -> bool:
        return self.asignaciones.empty


def _qsum(h: highspy.Highs, terminos):
    terminos = list(terminos)
    return h.qsum(terminos) if terminos else 0


def disponibilidad(config: ConfigColecta, voluntarios: list[Voluntario]) -> list[tuple[str, str, str, str]]:
    """Combinaciones (persona, día, bloque, lugar) posibles según la configuración."""
    lugares_validos = set(config.nombres_lugares)
    filas = []
    for v in voluntarios:
        for d in config.dias:
            if v.max_turnos.get(d, 0) <= 0:
                continue
            for s in v.disponibilidad.get(d, []):
                if s not in config.bloques:
                    continue
                for lugar in v.lugares.get(d, config.nombres_lugares):
                    if lugar in lugares_validos:
                        filas.append((v.id, d, s, lugar))
    return filas


def resolver(
    config: ConfigColecta,
    voluntarios: list[Voluntario],
    silencioso: bool = True,
    opciones_highs: dict | None = None,
) -> Resultado:
    inicio = time.perf_counter()
    reglas, pesos = config.reglas, config.pesos
    por_id = {v.id: v for v in voluntarios}
    orden = {s: i for i, s in enumerate(config.bloques)}
    combinaciones = disponibilidad(config, voluntarios)

    if not combinaciones:
        return Resultado(
            pd.DataFrame(columns=COLUMNAS_ASIGNACION),
            "Sin disponibilidad",
            False,
            0.0,
            ["Nadie tiene horarios compatibles con la configuración."],
        )

    h = highspy.Highs()
    if silencioso:
        h.silent()
    h.setOptionValue("time_limit", float(config.tiempo_limite_s))
    h.setOptionValue("mip_rel_gap", float(config.mip_gap))
    for opcion, valor in (opciones_highs or {}).items():
        h.setOptionValue(opcion, valor)

    # --- Variables -----------------------------------------------------------
    x = {k: h.addBinary() for k in combinaciones}
    por_bloque = defaultdict(list)  # (d, s, l) -> [(v, var)]
    por_persona_dia = defaultdict(list)  # (v, d) -> [(s, l, var)]
    for (v, d, s, lugar), var in x.items():
        por_bloque[d, s, lugar].append((v, var))
        por_persona_dia[v, d].append((s, lugar, var))

    c = {k: h.addBinary() for k in por_bloque}
    y = {}
    for (v, d), items in por_persona_dia.items():
        for lugar in {lugar for _, lugar, _ in items}:
            y[v, d, lugar] = h.addBinary()
    u = {v: h.addBinary() for v in {v for v, *_ in combinaciones}}

    objetivo = []

    # --- Cobertura y capacidad -----------------------------------------------
    for (d, s, lugar), items in por_bloque.items():
        total = _qsum(h, (var for _, var in items))
        # c = 1 exactamente cuando hay alguien: c <= total <= capacidad·c.
        h.addConstr(c[d, s, lugar] <= total)
        tope = min(config.lugar(lugar).capacidad, len(items))
        h.addConstr(total <= tope * c[d, s, lugar])
        objetivo.append(pesos.cobertura * c[d, s, lugar])

        if reglas.nadie_solo:
            for v, var in items:
                if not por_id[v].es_jefe:
                    # Si v va, debe haber al menos otra persona: 2·x_v <= total.
                    if len(items) == 1:
                        h.addConstr(var <= 0)
                    else:
                        h.addConstr(2 * var <= total)

    # --- Turnos por persona y día --------------------------------------------
    for (v, d), items in por_persona_dia.items():
        for _, lugar, var in items:
            h.addConstr(var <= y[v, d, lugar])
        lugares_dia = [y[v, d, lugar] for lugar in {lugar for _, lugar, _ in items}]
        if len(lugares_dia) > 1:
            h.addConstr(_qsum(h, lugares_dia) <= 1)

        h.addConstr(_qsum(h, (var for *_, var in items)) <= por_id[v].max_turnos.get(d, 0))

        # Bloques seguidos: a lo más un "inicio" en el día.
        z = defaultdict(list)
        for s, _, var in items:
            z[orden[s]].append(var)
        inicios = []
        for i in sorted(z):
            actual = _qsum(h, z[i])
            anterior = _qsum(h, z.get(i - 1, []))
            if i - 1 in z:
                inicio_var = h.addVariable(lb=0, ub=1)
                h.addConstr(inicio_var >= actual - anterior)
                inicios.append(inicio_var)
            else:
                inicios.append(actual)
        if len(inicios) > 1:
            h.addConstr(_qsum(h, inicios) <= 1)

    # --- Objetivo por turno y por persona ------------------------------------
    for (v, _, s, _), var in x.items():
        peso = pesos.peso_bloque(s)
        if por_id[v].es_jefe:
            peso += pesos.jefe
        objetivo.append(peso * var)
    for v, var in u.items():
        h.addConstr(var <= _suma_persona(h, v, por_persona_dia, config))
        objetivo.append(pesos.por_persona * var)

    # --- Reglas por lugar y día ----------------------------------------------
    cierres = {}
    for d in config.dias:
        for lugar in config.nombres_lugares:
            bloques = [(orden[s], c[d, s, lugar]) for s in config.bloques if (d, s, lugar) in c]
            if not bloques:
                continue
            bloques.sort()
            por_indice = dict(bloques)

            if reglas.horario_continuo_por_lugar and len(bloques) > 1:
                aperturas = []
                for i, var in bloques:
                    if i - 1 in por_indice:
                        a = h.addVariable(lb=0, ub=1)
                        h.addConstr(a >= var - por_indice[i - 1])
                        aperturas.append(a)
                    else:
                        aperturas.append(var)
                h.addConstr(_qsum(h, aperturas) <= 1)

            if reglas.auto_al_cierre or reglas.autos_durante_el_dia:
                for i, var in bloques:
                    s = config.bloques[i]
                    con_auto = [xv for v, xv in por_bloque[d, s, lugar] if d in por_id[v].auto]
                    if reglas.autos_durante_el_dia and con_auto:
                        hay_auto = h.addBinary()
                        h.addConstr(hay_auto <= _qsum(h, con_auto))
                        objetivo.append(pesos.auto_presente * hay_auto)
                    if reglas.auto_al_cierre:
                        # cierre >= c_s - c_{s+1}: vale 1 si el bloque es el último abierto.
                        cierre = h.addVariable(lb=0, ub=1)
                        siguiente = por_indice.get(i + 1)
                        if siguiente is None:
                            h.addConstr(cierre >= var)
                        else:
                            h.addConstr(cierre >= var - siguiente)
                        falta = h.addVariable(lb=0, ub=1)
                        h.addConstr(_qsum(h, con_auto) + falta >= cierre)
                        objetivo.append(-pesos.falta_auto_al_cierre * falta)
                        cierres[d, s, lugar] = falta

    # El objetivo se fija antes de la solución inicial: cambiarlo después la descarta.
    h.setObjective(_qsum(h, objetivo), highspy.ObjSense.kMaximize)

    # Punto de partida rápido: acelera mucho los casos grandes.
    # Se entregan x, c, y, u; HiGHS completa el resto de las variables auxiliares.
    inicial = solucion_inicial(config, voluntarios, combinaciones)
    valores = {var.index: float(k in inicial) for k, var in x.items()}
    valores.update(
        {
            var.index: float(any((v, d, s, lugar) in inicial for v, _ in por_bloque[d, s, lugar]))
            for (d, s, lugar), var in c.items()
        }
    )
    valores.update(
        {
            var.index: float(any((v, d, s, lugar) in inicial for s, lu, _ in por_persona_dia[v, d] if lu == lugar))
            for (v, d, lugar), var in y.items()
        }
    )
    con_turno = {k[0] for k in inicial}
    valores.update({var.index: float(v in con_turno) for v, var in u.items()})
    h.setSolution(
        len(valores),
        np.array(list(valores), dtype=np.int32),
        np.array(list(valores.values()), dtype=np.float64),
    )

    h.solve()

    estado = h.getModelStatus()
    segundos = time.perf_counter() - inicio
    texto_estado = h.modelStatusToString(estado)
    tiene_solucion = h.getInfo().primal_solution_status == 2  # kSolutionStatusFeasible
    if not tiene_solucion:
        return Resultado(
            pd.DataFrame(columns=COLUMNAS_ASIGNACION),
            texto_estado,
            False,
            segundos,
            [f"El solver no encontró una solución ({texto_estado})."],
        )

    valores = dict(zip(x.keys(), h.vals(list(x.values())), strict=True))
    filas = []
    for (v, d, s, lugar), val in valores.items():
        if val > 0.5:
            persona = por_id[v]
            filas.append(
                {
                    "id": v,
                    "nombre": persona.nombre,
                    "dia": d,
                    "bloque": s,
                    "lugar": lugar,
                    "auto": d in persona.auto,
                    "jefe": persona.es_jefe,
                }
            )
    asignaciones = pd.DataFrame(filas, columns=COLUMNAS_ASIGNACION)
    asignaciones = ordenar_asignaciones(asignaciones, config)

    avisos = []
    optimo = estado == highspy.HighsModelStatus.kOptimal
    if not optimo:
        avisos.append(
            f"Se alcanzó el límite de tiempo ({config.tiempo_limite_s:.0f} s); la solución es buena pero puede no ser la mejor."
        )

    cierres_sin_auto = []
    if reglas.auto_al_cierre and cierres:
        faltas = dict(zip(cierres.keys(), h.vals(list(cierres.values())), strict=True))
        for (d, s, lugar), val in faltas.items():
            if val > 0.5:
                cierres_sin_auto.append((d, lugar))
                avisos.append(f"{d} en {lugar}: nadie con auto en el último bloque ({s}). Hay que conseguir un auto.")

    return Resultado(asignaciones, texto_estado, optimo, segundos, avisos, cierres_sin_auto)


def _suma_persona(h, v, por_persona_dia, config):
    return _qsum(h, (var for d in config.dias for *_, var in por_persona_dia.get((v, d), [])))


def ordenar_asignaciones(df: pd.DataFrame, config: ConfigColecta) -> pd.DataFrame:
    if df.empty:
        return df.reset_index(drop=True)
    orden_dia = {d: i for i, d in enumerate(config.dias)}
    orden_bloque = {s: i for i, s in enumerate(config.bloques)}
    orden_lugar = {lugar: i for i, lugar in enumerate(config.nombres_lugares)}
    claves = df.assign(_d=df["dia"].map(orden_dia), _s=df["bloque"].map(orden_bloque), _l=df["lugar"].map(orden_lugar))
    return claves.sort_values(["_d", "_s", "_l", "nombre"]).drop(columns=["_d", "_s", "_l"]).reset_index(drop=True)
