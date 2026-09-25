from __future__ import annotations

import io

import pandas as pd

from colectatron import plantilla_form as pf
from colectatron.config import config_financiamiento, config_insumos
from colectatron.ejemplo import respuestas_ejemplo
from colectatron.formulario import (
    COLUMNAS_ANTIGUAS,
    FORMATO_ANTIGUO,
    detectar_columnas,
    es_jefe,
    interpretar_lugares,
    interpretar_maximo,
    leer_respuestas,
    leer_tabla,
)
from colectatron.texto import es_si, normalizar


def test_normalizar_y_si_no():
    assert normalizar("  Sí voy con todo🤑 ") == "si voy con todo"
    assert es_si("Si") is True
    assert es_si("Sí, voy con todo🤑") is True
    assert es_si("No, odio a financiamiento") is False
    assert es_si("No, odio a insumos 😔") is False
    assert es_si("Sí, voy con todo 🛒") is True
    assert es_si("") is None
    assert es_si("quizás") is None


def test_detecta_columnas_de_la_plantilla():
    config = config_insumos()
    mapa = detectar_columnas(respuestas_ejemplo(config, 5))
    assert mapa["correo"] == pf.COL_CORREO
    assert mapa["nombre"] == pf.P_NOMBRE
    assert mapa["direccion"] == pf.P_DIRECCION
    assert mapa["bodega"] == pf.P_BODEGA
    assert mapa["auto"] == pf.P_AUTO
    assert mapa["lugares"] == pf.P_LUGARES
    assert mapa["bloques"] == pf.P_BLOQUES
    assert mapa["maximo"] == pf.P_MAXIMO
    assert mapa["rol"] is None  # en insumos no se pregunta el rol
    assert detectar_columnas(respuestas_ejemplo(config_financiamiento(), 5))["rol"] == pf.P_ROL
    assert mapa["asiste"] == pf.P_ASISTE
    assert pf.textos_de(config).pregunta_chiste not in mapa.values()


def test_detecta_columnas_en_cualquier_orden():
    config = config_insumos()
    df = respuestas_ejemplo(config, 5)
    df = df[list(reversed(df.columns))]
    assert detectar_columnas(df)["bloques"] == pf.P_BLOQUES


def _fila(config, **cambios):
    fila = dict.fromkeys(pf.encabezados(config), "")
    fila.update(cambios)
    return fila


def test_lee_respuestas_unificadas():
    config = config_insumos()
    b = config.bloques
    filas = [
        _fila(
            config,
            **{
                pf.COL_CORREO: "ana@ejemplo.cl",
                pf.P_NOMBRE: "Ana",
                pf.P_TELEFONO: "+56911111111",
                pf.P_ASISTE: "Si",  # sin tilde
                f"{pf.P_BLOQUES} [{b[0]}]": "Sábado, Domingo",
                f"{pf.P_BLOQUES} [{b[1]}]": "Sabado",
                f"{pf.P_MAXIMO} [Sábado]": "Sin límite",
                f"{pf.P_MAXIMO} [Domingo]": "1",
                pf.P_LUGARES: config.nombres_lugares[0],
                pf.P_AUTO: "Domingo",
                pf.P_BODEGA: pf.SIN_BODEGA,
            },
        ),
        _fila(config, **{pf.COL_CORREO: "beto@ejemplo.cl", pf.P_NOMBRE: "Beto", pf.P_ASISTE: "No"}),
        # Beto responde de nuevo: vale la última respuesta.
        _fila(
            config,
            **{
                pf.COL_CORREO: "Beto@Ejemplo.cl",
                pf.P_NOMBRE: "Beto",
                pf.P_ASISTE: "Sí",
                f"{pf.P_BLOQUES} [{b[2]}]": "Domingo",
                pf.P_LUGARES: "Supermercado Inventado",
            },
        ),
    ]
    lectura = leer_respuestas(pd.DataFrame(filas), config)
    por_nombre = {v.nombre: v for v in lectura.voluntarios}

    ana = por_nombre["Ana"]
    assert ana.disponibilidad == {"Sábado": [b[0], b[1]], "Domingo": [b[0]]}
    assert ana.max_turnos == {"Sábado": len(b), "Domingo": 1}
    assert ana.lugares["Sábado"] == [config.nombres_lugares[0]]
    assert ana.auto == {"Domingo"}
    assert ana.bodega == set()

    beto = por_nombre["Beto"]
    assert beto.fila == 4
    assert beto.lugares["Domingo"] == config.nombres_lugares  # lugar desconocido → todos, con aviso
    assert not lectura.no_asisten
    mensajes = " ".join(a.mensaje for a in lectura.avisos)
    assert "más de una vez" in mensajes
    assert "supermercado inventado" in mensajes.lower()


def test_falta_columna_obligatoria():
    config = config_insumos()
    lectura = leer_respuestas(pd.DataFrame({"Algo": ["x"]}), config)
    assert any(a.nivel == "error" for a in lectura.avisos)
    assert not lectura.voluntarios


def test_roles_de_financiamiento_segun_la_epoca():
    from datetime import date

    assert not pf.resultados_publicados(date(2026, 4, 20))
    assert pf.resultados_publicados(date(2026, 9, 25))
    antes = pf.textos_por_defecto(config_financiamiento(), resultados=False).roles
    despues = pf.textos_por_defecto(config_financiamiento(), resultados=True).roles
    assert antes == ["Familia", "Voluntario/a"]
    assert despues == ["Familia", "Staff", "Voluntario/a"]
    jefes = config_financiamiento().roles_jefe
    assert [r for r in despues if es_jefe(r, jefes)] == ["Familia", "Staff"]
    # En insumos no hay pregunta de rol.
    assert pf.textos_de(config_insumos()).roles == []
    assert '"roles": []' in pf.script_apps(config_insumos())  # el script salta la pregunta
    assert pf.P_ROL not in pf.encabezados(config_insumos())
    assert pf.P_ROL in pf.encabezados(config_financiamiento())


def test_jefes_por_rol():
    assert es_jefe("Familia", ["Familia", "Staff"])
    assert es_jefe("Staff 2026", ["Staff"])
    assert not es_jefe("Comunerx/Comisionadx", ["Familia", "Staff"])
    assert not es_jefe("No", ["Familia"])  # el error del código antiguo
    assert not es_jefe("", ["Familia"])


def test_interpretar_lugares_y_maximo():
    lugares = ["Tobalaba con El Bosque", "Holanda con Pocuro"]
    assert interpretar_lugares("Donde me necesiten", lugares) == (lugares, [])
    assert interpretar_lugares("", lugares) == (lugares, [])
    assert interpretar_lugares("holanda con pocuro, Otra", lugares) == (["Holanda con Pocuro"], ["otra"])
    assert interpretar_maximo("Sin límite", 9) == 9
    assert interpretar_maximo("3", 9) == 3
    assert interpretar_maximo("Todo el día🤯🤯", 9) == 9
    assert interpretar_maximo("muchos", 9) is None


def test_formato_antiguo():
    config = config_financiamiento()
    b = config.bloques
    fila = ["" for _ in COLUMNAS_ANTIGUAS]
    fila[0], fila[1], fila[2], fila[3] = "a@x.cl", "Ana", "56912345678", "Sí voy con todo🤑"
    fila[4] = "Ambos días"
    fila[11], fila[12] = "2", f"{b[0]}, {b[1]}"
    fila[13], fila[14] = "Todo el día🤯🤯", "Todo el día🤯🤯"
    fila[15] = "Donde me necesiten"
    fila[16] = "Comunerx/Comisionadx"
    otra = list(fila)
    otra[0], otra[1], otra[3] = "b@x.cl", "Bea", "No, odio a financiamiento"
    df = pd.DataFrame([fila, otra], columns=COLUMNAS_ANTIGUAS)

    lectura = leer_respuestas(df, config, FORMATO_ANTIGUO)
    assert [v.nombre for v in lectura.voluntarios] == ["Ana"]
    assert [v.nombre for v in lectura.no_asisten] == ["Bea"]
    ana = lectura.voluntarios[0]
    assert ana.disponibilidad == {"Viernes": b[:2], "Sábado": b}
    assert ana.max_turnos == {"Viernes": 2, "Sábado": len(b)}
    assert not ana.es_jefe


def test_leer_tabla_csv_y_excel():
    config = config_insumos()
    df = respuestas_ejemplo(config, 4)

    texto = df.to_csv(index=False, sep=";").encode("cp1252", errors="replace")
    assert leer_tabla(io.BytesIO(texto), "respuestas.csv").shape == df.shape

    salida = io.BytesIO()
    df.to_excel(salida, index=False)
    leido = leer_tabla(io.BytesIO(salida.getvalue()), "respuestas.xlsx")
    assert list(leido.columns) == list(df.columns)
    assert leido[pf.P_TELEFONO].iloc[0].startswith("+569")
