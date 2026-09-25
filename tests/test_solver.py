from __future__ import annotations

from dataclasses import replace

from conftest import BLOQUES, persona

from colectatron.config import Lugar, Reglas
from colectatron.solver import resolver


def _bloques_de(resultado, id):
    df = resultado.asignaciones
    return df[df["id"] == id]["bloque"].tolist()


def test_respeta_capacidad(config_chica):
    config = replace(config_chica, lugares=[Lugar("A", capacidad=2)])
    vols = [persona(f"p{i}", bloques=[BLOQUES[0]], lugares=["A"]) for i in range(3)]
    r = resolver(config, vols)
    assert r.optimo
    assert len(r.asignaciones) == 2


def test_nadie_solo_salvo_jefes(config_chica):
    config = replace(config_chica, reglas=Reglas(nadie_solo=True))
    r = resolver(config, [persona("solo", bloques=[BLOQUES[0]], lugares=["A"])])
    assert r.asignaciones.empty

    r = resolver(config, [persona("jefa", bloques=[BLOQUES[0]], lugares=["A"], jefe=True)])
    assert len(r.asignaciones) == 1

    # Con alguien más en el bloque, quien no es jefe sí puede ir.
    vols = [persona("a", bloques=[BLOQUES[0]], lugares=["A"]), persona("b", bloques=[BLOQUES[0]], lugares=["A"])]
    r = resolver(config, vols)
    assert len(r.asignaciones) == 2


def test_turnos_seguidos_y_maximo(config_chica):
    # Disponible en 0, 1 y 3: con bloques seguidos no puede tomar 0 y 3 a la vez.
    v = persona("p", bloques=[BLOQUES[0], BLOQUES[1], BLOQUES[3]], maximo=3)
    r = resolver(config_chica, [v])
    tomados = sorted(BLOQUES.index(b) for b in _bloques_de(r, "p"))
    assert tomados == list(range(tomados[0], tomados[-1] + 1))

    r = resolver(config_chica, [persona("q", maximo=2)])
    assert len(_bloques_de(r, "q")) == 2


def test_un_lugar_por_dia(config_chica):
    r = resolver(config_chica, [persona("p")])
    assert r.asignaciones["lugar"].nunique() == 1


def test_prioriza_que_todos_tengan_turno(config_chica):
    # Una sola vacante (capacidad 1, un bloque): gana cualquiera, pero con dos
    # bloques y máximo 1 cada una, ambas personas deben quedar con turno.
    config = replace(config_chica, lugares=[Lugar("A", capacidad=1)], bloques=BLOQUES[:2])
    vols = [persona("a", bloques=BLOQUES[:2], lugares=["A"]), persona("b", bloques=BLOQUES[:2], lugares=["A"])]
    r = resolver(config, vols)
    assert set(r.asignaciones["id"]) == {"a", "b"}


def test_auto_al_cierre_avisa_si_no_hay(config_chica):
    config = replace(config_chica, lugares=[Lugar("A")], reglas=Reglas(nadie_solo=False, auto_al_cierre=True))
    r = resolver(config, [persona("sin_auto", lugares=["A"])])
    assert r.cierres_sin_auto == [("Sábado", "A")]
    assert any("auto" in a for a in r.avisos)


def test_auto_al_cierre_pone_al_del_auto_al_final(config_chica):
    config = replace(config_chica, lugares=[Lugar("A")], reglas=Reglas(nadie_solo=False, auto_al_cierre=True))
    vols = [
        persona("sin_auto", lugares=["A"]),
        persona("con_auto", lugares=["A"], auto=True, maximo=1),
    ]
    r = resolver(config, vols)
    assert r.cierres_sin_auto == []
    assert _bloques_de(r, "con_auto") == [BLOQUES[-1]]


def test_horario_continuo_por_lugar(config_chica):
    config = replace(
        config_chica,
        lugares=[Lugar("A", capacidad=1)],
        reglas=Reglas(nadie_solo=False, horario_continuo_por_lugar=True),
    )
    # Dos personas con un bloque cada una, separadas por un hueco: solo una puede abrir el lugar.
    vols = [
        persona("temprano", bloques=[BLOQUES[0]], lugares=["A"]),
        persona("tarde", bloques=[BLOQUES[2]], lugares=["A"]),
    ]
    r = resolver(config, vols)
    assert len(r.asignaciones) == 1


def test_sin_disponibilidad(config_chica):
    r = resolver(config_chica, [persona("p", bloques=[])])
    assert r.vacio
    assert r.avisos


def test_solucion_inicial_cumple_reglas_duras():
    from collections import Counter

    from colectatron.config import config_financiamiento, config_insumos
    from colectatron.ejemplo import respuestas_ejemplo
    from colectatron.formulario import leer_respuestas
    from colectatron.inicial import solucion_inicial
    from colectatron.solver import disponibilidad

    for config in (config_financiamiento(), config_insumos()):
        lectura = leer_respuestas(respuestas_ejemplo(config, 80), config)
        vols = {v.id: v for v in lectura.voluntarios}
        combinaciones = disponibilidad(config, lectura.voluntarios)
        inicial = solucion_inicial(config, lectura.voluntarios, combinaciones)
        assert inicial and inicial <= set(combinaciones)

        por_bloque = Counter((d, s, lugar) for _, d, s, lugar in inicial)
        assert all(n <= config.lugar(lugar).capacidad for (_, _, lugar), n in por_bloque.items())

        orden = {s: i for i, s in enumerate(config.bloques)}
        for v in vols:
            for d in config.dias:
                mios = [(orden[s], lugar) for vv, dd, s, lugar in inicial if vv == v and dd == d]
                if not mios:
                    continue
                assert len({lugar for _, lugar in mios}) == 1
                indices = sorted(i for i, _ in mios)
                assert indices == list(range(indices[0], indices[-1] + 1))
                assert len(indices) <= vols[v].max_turnos[d]

        if config.reglas.nadie_solo:
            for (d, s, lugar), n in por_bloque.items():
                if n == 1:
                    (v,) = [vv for vv, dd, ss, ll in inicial if (dd, ss, ll) == (d, s, lugar)]
                    assert vols[v].es_jefe
