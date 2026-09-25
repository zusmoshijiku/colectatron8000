"""Solución inicial voraz para ayudar al solver.

Con muchas personas y lugares, HiGHS puede demorar en encontrar su primera
solución. Esta heurística arma rápido una asignación que cumple todas las
restricciones duras (capacidad, un lugar por día, máximo de bloques, bloques
seguidos, nadie solo y horario continuo por lugar) y se la entrega al solver
como punto de partida. El solver luego la mejora.
"""

from __future__ import annotations

from collections import defaultdict

from .config import ConfigColecta
from .formulario import Voluntario

Turno = tuple[str, str, str, int, int]  # (persona, día, lugar, bloque inicial, bloque final) con índices inclusivos


def _ventanas(indices: list[int], maximo: int) -> list[tuple[int, int]]:
    """Tramos seguidos de largo 1..maximo dentro de los bloques disponibles."""
    tramos, disponibles = [], set(indices)
    for i in indices:
        largo = 0
        while largo < maximo and i + largo in disponibles:
            tramos.append((i, i + largo))
            largo += 1
    return tramos


def solucion_inicial(
    config: ConfigColecta,
    voluntarios: list[Voluntario],
    combinaciones: list[tuple[str, str, str, str]],
) -> set[tuple[str, str, str, str]]:
    """Devuelve las combinaciones (persona, día, bloque, lugar) asignadas."""
    reglas, pesos = config.reglas, config.pesos
    por_id = {v.id: v for v in voluntarios}
    orden = {s: i for i, s in enumerate(config.bloques)}
    capacidad = {lugar.nombre: lugar.capacidad for lugar in config.lugares}

    opciones: dict[tuple[str, str], dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for v, d, s, lugar in combinaciones:
        opciones[v, d][lugar].append(orden[s])

    ocupacion: dict[tuple[str, int, str], set[str]] = defaultdict(set)  # (día, bloque, lugar) -> personas
    turnos: dict[tuple[str, str], Turno] = {}

    def cubiertos(d: str, lugar: str) -> set[int]:
        return {i for i in range(len(config.bloques)) if ocupacion[d, i, lugar]}

    def puntaje(v: str, d: str, lugar: str, a: int, b: int) -> float | None:
        if reglas.horario_continuo_por_lugar:
            nuevos = cubiertos(d, lugar) | set(range(a, b + 1))
            if max(nuevos) - min(nuevos) + 1 != len(nuevos):
                return None
        total = 0.0
        for i in range(a, b + 1):
            gente = ocupacion[d, i, lugar]
            if len(gente) >= capacidad[lugar]:
                return None
            if not gente:
                solo = reglas.nadie_solo and not por_id[v].es_jefe
                total += pesos.cobertura * (0.5 if solo else 1)
            total += pesos.peso_bloque(config.bloques[i]) - 5 * len(gente)
            if d in por_id[v].auto:
                total += pesos.auto_presente
        return total

    def asignar(pendientes: list[tuple[str, str]]) -> None:
        for v, d in pendientes:
            if (v, d) in turnos:
                continue
            maximo = por_id[v].max_turnos.get(d, 0)
            mejor, mejor_turno = None, None
            for lugar, indices in opciones[v, d].items():
                for a, b in _ventanas(sorted(indices), maximo):
                    p = puntaje(v, d, lugar, a, b)
                    if p is not None and (mejor is None or p > mejor):
                        mejor, mejor_turno = p, (v, d, lugar, a, b)
            if mejor_turno:
                turnos[v, d] = mejor_turno
                for i in range(mejor_turno[3], mejor_turno[4] + 1):
                    ocupacion[d, i, mejor_turno[2]].add(v)

    def quitar(v: str, d: str) -> None:
        _, _, lugar, a, b = turnos.pop((v, d))
        for i in range(a, b + 1):
            ocupacion[d, i, lugar].discard(v)

    def reparar() -> None:
        """Quita turnos hasta cumplir "nadie solo" y "horario continuo por lugar"."""
        cambio = True
        while cambio:
            cambio = False
            if reglas.nadie_solo:
                for (d, _, _), gente in list(ocupacion.items()):
                    if len(gente) == 1:
                        (v,) = gente
                        if not por_id[v].es_jefe and (v, d) in turnos:
                            quitar(v, d)
                            cambio = True
            if reglas.horario_continuo_por_lugar:
                for d in config.dias:
                    for lugar in config.nombres_lugares:
                        abiertos = sorted(cubiertos(d, lugar))
                        tramos: list[list[int]] = []
                        for i in abiertos:
                            if tramos and tramos[-1][-1] == i - 1:
                                tramos[-1].append(i)
                            else:
                                tramos.append([i])
                        if len(tramos) > 1:
                            largo = max(tramos, key=len)
                            for (v, dd), (_, _, lu, a, b) in list(turnos.items()):
                                if dd == d and lu == lugar and not (largo[0] <= a and b <= largo[-1]):
                                    quitar(v, dd)
                                    cambio = True

    # Primero quienes tienen menos opciones; los jefes antes para que puedan abrir bloques.
    pendientes = sorted(
        opciones,
        key=lambda k: (not por_id[k[0]].es_jefe, sum(len(x) for x in opciones[k].values()), k),
    )
    for _ in range(2):
        asignar(pendientes)
        reparar()

    return {(v, d, config.bloques[i], lugar) for (v, d), (_, _, lugar, a, b) in turnos.items() for i in range(a, b + 1)}
