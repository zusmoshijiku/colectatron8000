"""Colectatron8000: asignación de turnos para colectas, en el navegador.

Para correrla en tu computador:  streamlit run streamlit_app.py
"""

from __future__ import annotations

import hashlib
import hmac

import altair as alt
import pandas as pd
import pydeck as pdk
import streamlit as st

from colectatron import geo
from colectatron.bodegas import asignar_bodegas
from colectatron.config import PLANTILLAS, TIPO_INSUMOS, ConfigColecta, Lugar, Pesos, Reglas, TextosForm
from colectatron.ejemplo import respuestas_ejemplo
from colectatron.formulario import (
    CAMPOS,
    FORMATO_ANTIGUO,
    FORMATO_UNIFICADO,
    GRILLAS,
    Lectura,
    detectar_columnas,
    grillas_del_archivo,
    leer_respuestas,
    leer_tabla,
    valores_de_rol,
)
from colectatron.plantilla_form import script_apps, textos_de, textos_por_defecto, validar_textos
from colectatron.reportes import cobertura, planner_excel, por_persona, resumen, sin_turno
from colectatron.solver import resolver

st.set_page_config(page_title="Colectatron8000", page_icon="🗓️", layout="wide")

ESTADO = st.session_state


# ---------------------------------------------------------------------------
# Contraseña (se define en los "Secrets" de Streamlit Cloud como password = "...")
# ---------------------------------------------------------------------------


def _clave_configurada() -> str | None:
    try:
        return st.secrets.get("password")
    except Exception:  # sin archivo de secretos: uso local
        return None


def _pedir_clave() -> None:
    clave = _clave_configurada()
    if not clave or ESTADO.get("autenticado"):
        return
    st.title("🗓️ Colectatron8000")
    escrita = st.text_input("Contraseña", type="password")
    if escrita:
        if hmac.compare_digest(escrita.encode(), str(clave).encode()):
            ESTADO["autenticado"] = True
            st.rerun()
        st.error("Contraseña incorrecta.")
    st.stop()


_pedir_clave()


# ---------------------------------------------------------------------------
# Estado inicial
# ---------------------------------------------------------------------------

if "config" not in ESTADO:
    ESTADO["config"] = PLANTILLAS[TIPO_INSUMOS]()
    ESTADO["version_config"] = 0


def _cargar_config(config: ConfigColecta) -> None:
    ESTADO["config"] = config
    ESTADO["version_config"] = ESTADO.get("version_config", 0) + 1  # reinicia los editores
    ESTADO.pop("resultado", None)


def _huella(*partes) -> str:
    h = hashlib.sha256()
    for p in partes:
        h.update(str(p).encode())
    return h.hexdigest()


st.title("🗓️ Colectatron8000")
st.caption("Asigna voluntarios a turnos de colecta: sube las respuestas del Form, revisa y descarga el planner.")

tab_colecta, tab_form, tab_respuestas, tab_resultados = st.tabs(
    ["1 · Colecta", "2 · Formulario", "3 · Respuestas", "4 · Resultados"]
)


# ---------------------------------------------------------------------------
# 1. Configuración de la colecta
# ---------------------------------------------------------------------------

with tab_colecta:
    cfg: ConfigColecta = ESTADO["config"]
    v = ESTADO["version_config"]

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Partir de una plantilla**")
        tipo = st.selectbox(
            "Tipo de colecta",
            list(PLANTILLAS),
            format_func=lambda t: {"financiamiento": "Financiamiento (esquinas)", "insumos": "Insumos (supermercados)"}[
                t
            ],
            index=list(PLANTILLAS).index(cfg.tipo),
            key=f"tipo_{v}",
        )
        if tipo != cfg.tipo:
            _cargar_config(PLANTILLAS[tipo]())
            st.rerun()
    with c2:
        st.markdown("**…o cargar una configuración guardada**")
        subida = st.file_uploader("Archivo .json", type=["json"], key=f"cfg_json_{v}", label_visibility="collapsed")
        if subida is not None:
            try:
                _cargar_config(ConfigColecta.from_json(subida.getvalue().decode("utf-8")))
                st.rerun()
            except Exception as e:  # archivo mal formado
                st.error(f"No se pudo leer la configuración: {e}")

    nombre = st.text_input("Nombre de la colecta", cfg.nombre, key=f"nombre_{v}")

    col_dias, col_bloques = st.columns([1, 2])
    with col_dias:
        st.markdown("**Días**")
        dias_df = st.data_editor(
            pd.DataFrame({"Día": cfg.dias}), num_rows="dynamic", hide_index=True, key=f"dias_{v}", width="stretch"
        )
    with col_bloques:
        st.markdown("**Bloques horarios** (peso: cuánto se prefiere llenar ese bloque; normal = 10)")
        bloques_df = st.data_editor(
            pd.DataFrame({"Bloque": cfg.bloques, "Peso": [cfg.pesos.peso_bloque(b) for b in cfg.bloques]}),
            num_rows="dynamic",
            hide_index=True,
            key=f"bloques_{v}",
            width="stretch",
            column_config={"Peso": st.column_config.NumberColumn(min_value=0, max_value=100, step=1)},
        )

    st.markdown("**Lugares** (esquinas o supermercados) · capacidad = máximo de personas por bloque")
    lugares_df = st.data_editor(
        pd.DataFrame(
            {
                "Nombre": [x.nombre for x in cfg.lugares],
                "Dirección": [x.direccion for x in cfg.lugares],
                "Comuna": [x.comuna for x in cfg.lugares],
                "Capacidad": [x.capacidad for x in cfg.lugares],
            }
        ),
        num_rows="dynamic",
        hide_index=True,
        key=f"lugares_{v}",
        width="stretch",
        column_config={"Capacidad": st.column_config.NumberColumn(min_value=1, max_value=50, step=1, default=4)},
    )

    st.markdown("**Reglas**")
    r = cfg.reglas
    rc1, rc2 = st.columns(2)
    with rc1:
        nadie_solo = st.toggle(
            "Nadie solo (salvo jefes)",
            r.nadie_solo,
            key=f"r1_{v}",
            help="Quien no es jefe solo puede estar en un bloque si hay al menos otra persona.",
        )
        continuo = st.toggle(
            "Horario continuo por lugar",
            r.horario_continuo_por_lugar,
            key=f"r2_{v}",
            help="Cada lugar abre en un solo tramo por día (puede empezar más tarde o terminar antes, pero sin huecos).",
        )
        asignar_casas = st.toggle(
            "Asignar casas-bodega",
            r.asignar_bodegas,
            key=f"r5_{v}",
            help="A cada lugar abierto se le asigna una casa donde guardar lo recolectado ese día.",
        )
    with rc2:
        auto_cierre = st.toggle(
            "Auto en el cierre",
            r.auto_al_cierre,
            key=f"r3_{v}",
            help="En el último bloque de cada lugar debe haber alguien con auto para el traslado final. Si no hay, se avisa.",
        )
        autos_dia = st.toggle(
            "Autos repartidos en el día",
            r.autos_durante_el_dia,
            key=f"r4_{v}",
            help="Prefiere que haya personas con auto en varios bloques, para hacer traslados intermedios.",
        )

    with st.expander("Opciones avanzadas"):
        p = cfg.pesos
        a1, a2, a3 = st.columns(3)
        cobertura_peso = a1.number_input(
            "Premio por bloque cubierto", 0.0, value=float(p.cobertura), step=100.0, key=f"p1_{v}"
        )
        persona_peso = a2.number_input(
            "Premio por persona con turno", 0.0, value=float(p.por_persona), step=10.0, key=f"p2_{v}"
        )
        jefe_peso = a3.number_input("Premio por turno de jefe", 0.0, value=float(p.jefe), step=50.0, key=f"p3_{v}")
        falta_auto = a1.number_input(
            "Castigo por cierre sin auto", 0.0, value=float(p.falta_auto_al_cierre), step=50.0, key=f"p4_{v}"
        )
        auto_presente = a2.number_input(
            "Premio por bloque con auto", 0.0, value=float(p.auto_presente), step=5.0, key=f"p5_{v}"
        )
        tiempo = a3.number_input(
            "Tiempo máximo del solver (s)", 5.0, 600.0, value=float(cfg.tiempo_limite_s), step=5.0, key=f"t_{v}"
        )

    def _texto_limpio(serie) -> list[str]:
        return [str(x).strip() for x in serie if pd.notna(x) and str(x).strip()]

    bloques_validos = bloques_df.dropna(subset=["Bloque"])
    bloques_validos = bloques_validos[bloques_validos["Bloque"].astype(str).str.strip() != ""]
    nuevo = ConfigColecta(
        nombre=nombre.strip() or "Colecta",
        tipo=cfg.tipo,
        dias=_texto_limpio(dias_df["Día"]),
        bloques=[str(b).strip() for b in bloques_validos["Bloque"]],
        lugares=[
            Lugar(
                str(f["Nombre"]).strip(),
                "" if pd.isna(f["Dirección"]) else str(f["Dirección"]).strip(),
                "" if pd.isna(f["Comuna"]) else str(f["Comuna"]).strip(),
                int(f["Capacidad"]) if pd.notna(f["Capacidad"]) else 4,
            )
            for _, f in lugares_df.iterrows()
            if pd.notna(f["Nombre"]) and str(f["Nombre"]).strip()
        ],
        roles_jefe=cfg.roles_jefe,
        reglas=Reglas(nadie_solo, continuo, auto_cierre, autos_dia, asignar_casas),
        pesos=Pesos(
            cobertura=cobertura_peso,
            por_persona=persona_peso,
            jefe=jefe_peso,
            falta_auto_al_cierre=falta_auto,
            auto_presente=auto_presente,
            bloque={
                str(f["Bloque"]).strip(): float(f["Peso"])
                for _, f in bloques_validos.iterrows()
                if pd.notna(f["Peso"]) and float(f["Peso"]) != 10
            },
        ),
        tiempo_limite_s=tiempo,
        mip_gap=cfg.mip_gap,
        form=cfg.form,
    )
    ESTADO["config"] = nuevo

    for problema in nuevo.validar():
        st.error(problema)

    # Se llena al final, cuando la pestaña Formulario ya agregó sus textos.
    lugar_boton_guardar = st.empty()

config: ConfigColecta = ESTADO["config"]


# ---------------------------------------------------------------------------
# 2. Formulario
# ---------------------------------------------------------------------------

with tab_form:
    st.markdown(
        """
Con este script se crea el Google Form con **exactamente** las preguntas que la app sabe leer,
usando los días, bloques y lugares de la pestaña *Colecta* y los textos de abajo. No hay que programar nada:

1. Entra a [script.google.com](https://script.google.com) con la cuenta de la comisión y crea un **Nuevo proyecto**.
2. Borra lo que aparece, pega el código del final (botón de copiar en la esquina) y guarda.
3. Arriba elige la función `crearFormulario` y presiona **Ejecutar**. Acepta los permisos.
4. En el *Registro de ejecución* aparecen los links para responder y para editar el Form.
5. En el Form, pestaña **Respuestas → Vincular con Hojas de cálculo**.

Después puedes cambiar colores, agregar imágenes y emojis en el editor del Form, pero **no cambies los títulos
ni las opciones** de las preguntas de disponibilidad: la app los usa para leer las respuestas.
"""
    )

    textos = textos_de(config)
    vf = f"{ESTADO['version_config']}_{ESTADO.get('version_form', 0)}"

    st.markdown("#### Inicio del Form")
    f_titulo = st.text_input("Título", textos.titulo, key=f"f_titulo_{vf}")
    f_invitacion = st.text_area(
        "Invitación",
        textos.invitacion,
        height=230,
        key=f"f_inv_{vf}",
        help="Completa las fechas en ¿Cuándo?. Los emojis se ven igual en el Form.",
    )
    c1, c2 = st.columns(2)
    f_si = c1.text_input("Opción para ir (debe empezar con «Sí»)", textos.opcion_si, key=f"f_si_{vf}")
    f_no = c2.text_input("Opción para no ir (debe empezar con «No»)", textos.opcion_no, key=f"f_no_{vf}")
    f_roles = c1.text_input("Opciones de rol (separadas por coma)", ", ".join(textos.roles), key=f"f_roles_{vf}")
    f_ayuda_rol = c2.text_input("Descripción de la pregunta de rol", textos.ayuda_rol, key=f"f_ayuda_{vf}")

    st.markdown("#### Final del Form")
    st.caption("Lo ven todas las personas, también quienes responden que no van. La app no usa estas respuestas.")
    f_chiste = st.text_input(
        "Pregunta chiste (déjala vacía para no incluirla)", textos.pregunta_chiste, key=f"f_chiste_{vf}"
    )
    c1, c2 = st.columns([3, 1])
    f_opciones = c1.text_area(
        "Opciones de la pregunta chiste (una por línea)",
        "\n".join(textos.opciones_chiste),
        height=160,
        key=f"f_opciones_{vf}",
        help="Para ponerle una foto a cada opción, como en la primera colecta, usa el ícono de imagen "
        "junto a cada opción en el editor del Form.",
    )
    f_obligatoria = c2.checkbox("Obligatoria", textos.chiste_obligatorio, key=f"f_oblig_{vf}")
    f_despedida = st.text_input("Despedida (va junto a la foto)", textos.despedida, key=f"f_desp_{vf}")
    f_foto = st.text_input(
        "Link a la foto de la comisión",
        textos.foto_url,
        key=f"f_foto_{vf}",
        help="Link de Google Drive (compartido con «cualquier persona con el enlace») o link directo a una imagen. "
        "Si lo dejas vacío, agrega la foto a mano en el editor del Form: Insertar imagen.",
    )

    nuevos = TextosForm(
        titulo=f_titulo.strip() or textos.titulo,
        invitacion=f_invitacion.strip(),
        roles=[x.strip() for x in f_roles.split(",") if x.strip()],
        ayuda_rol=f_ayuda_rol.strip(),
        opcion_si=f_si.strip(),
        opcion_no=f_no.strip(),
        pregunta_chiste=f_chiste.strip(),
        opciones_chiste=[x.strip() for x in f_opciones.splitlines() if x.strip()],
        chiste_obligatorio=f_obligatoria,
        despedida=f_despedida.strip(),
        foto_url=f_foto.strip(),
    )
    config.form = None if nuevos == textos_por_defecto(config) else nuevos
    if config.form is not None and st.button("Volver a los textos de la plantilla"):
        config.form = None
        ESTADO["version_form"] = ESTADO.get("version_form", 0) + 1
        st.rerun()

    problemas_form = validar_textos(nuevos)
    for problema in problemas_form:
        st.error(problema)

    st.markdown("#### Script")
    st.caption("Los textos quedan guardados en la configuración (.json) de la pestaña Colecta.")
    if not problemas_form:
        codigo = script_apps(config)
        st.download_button("Descargar script (.gs)", codigo.encode("utf-8"), file_name="crear_formulario.gs")
        st.code(codigo, language="javascript")


lugar_boton_guardar.download_button(
    "💾 Guardar esta configuración (.json)",
    config.to_json().encode("utf-8"),
    file_name=f"{config.nombre.lower().replace(' ', '_')}.json",
    mime="application/json",
    help="Incluye los textos del Form. Guárdala para reutilizarla en la próxima colecta: se carga arriba a la derecha.",
)


# ---------------------------------------------------------------------------
# 3. Respuestas
# ---------------------------------------------------------------------------

with tab_respuestas:
    st.markdown(
        "Descarga las respuestas desde la hoja de cálculo del Form (**Archivo → Descargar → Microsoft Excel** o **CSV**) "
        "y súbelas tal cual. No hace falta ordenar ni borrar columnas."
    )
    c1, c2 = st.columns([3, 1])
    archivo = c1.file_uploader("Respuestas del Form", type=["xlsx", "xls", "csv"])
    if c2.button("Probar con respuestas de ejemplo", help="Datos inventados, con el formato del Form unificado."):
        ESTADO["df"] = respuestas_ejemplo(config, n=60)
        ESTADO["origen"] = "ejemplo"
    if archivo is not None and ESTADO.get("origen") != archivo.file_id:
        try:
            ESTADO["df"] = leer_tabla(archivo, archivo.name)
            ESTADO["origen"] = archivo.file_id
        except Exception as e:
            st.error(f"No se pudo leer el archivo: {e}")

    df: pd.DataFrame | None = ESTADO.get("df")
    lectura: Lectura | None = None
    if df is None:
        st.info("Sube un archivo para continuar.")
    else:
        st.caption(
            f"{len(df)} filas · {df.shape[1]} columnas"
            + (" · datos de ejemplo" if ESTADO.get("origen") == "ejemplo" else "")
        )
        formato = st.radio(
            "Formato del Form",
            [FORMATO_UNIFICADO, FORMATO_ANTIGUO],
            format_func=lambda f: {
                FORMATO_UNIFICADO: "Form unificado (plantilla nueva)",
                FORMATO_ANTIGUO: "Form antiguo de financiamiento (columnas en orden fijo)",
            }[f],
            horizontal=True,
        )

        mapa = detectar_columnas(df)
        if formato == FORMATO_UNIFICADO:
            falta = [k for k in ("nombre", "bloques") if not mapa.get(k)]
            with st.expander("Columnas reconocidas", expanded=bool(falta)):
                st.caption("La app reconoce las columnas por el texto de la pregunta. Corrige aquí si algo no calza.")
                opciones_simples = [None] + list(df.columns)
                opciones_grilla = [None] + list(grillas_del_archivo(list(df.columns)))
                cols = st.columns(3)
                for i, (clave, campo) in enumerate(CAMPOS.items()):
                    actual = mapa.get(clave)
                    mapa[clave] = cols[i % 3].selectbox(
                        campo.etiqueta + (" *" if campo.obligatorio else ""),
                        opciones_simples,
                        index=opciones_simples.index(actual) if actual in opciones_simples else 0,
                        format_func=lambda x: "— ninguna —" if x is None else x,
                        key=f"map_{clave}",
                    )
                for i, (clave, etiqueta) in enumerate(GRILLAS.items()):
                    actual = mapa.get(clave)
                    mapa[clave] = cols[i % 3].selectbox(
                        etiqueta + (" *" if clave == "bloques" else ""),
                        opciones_grilla,
                        index=opciones_grilla.index(actual) if actual in opciones_grilla else 0,
                        format_func=lambda x: "— ninguna —" if x is None else x,
                        key=f"map_{clave}",
                    )
            columna_rol = mapa.get("rol")
        else:
            columna_rol = df.columns[16] if df.shape[1] > 16 else None

        roles = valores_de_rol(df, columna_rol)
        if roles:
            por_defecto = [x for x in roles if any(j.lower() in x.lower() for j in config.roles_jefe)]
            jefes = st.multiselect(
                "¿Qué respuestas de rol cuentan como jefe?",
                roles,
                default=por_defecto,
                help="Los jefes pueden quedar solos en un bloque y reciben prioridad (según las reglas).",
            )
            config.roles_jefe = jefes

        lectura = leer_respuestas(df, config, formato, mapa)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Respuestas", lectura.total_respuestas)
        m2.metric("Asisten", len(lectura.voluntarios))
        m3.metric("No asisten", len(lectura.no_asisten))
        m4.metric("Jefes", sum(v.es_jefe for v in lectura.voluntarios))

        errores = [a for a in lectura.avisos if a.nivel == "error"]
        for a in errores:
            st.error(a.mensaje)
        avisos_df = lectura.avisos_df()
        if not avisos_df.empty and not errores:
            st.warning(f"{len(avisos_df)} cosas para revisar (no impiden continuar):")
            st.dataframe(avisos_df, hide_index=True, width="stretch")

        with st.expander("Ver disponibilidad leída"):
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Nombre": x.nombre,
                            "Rol": x.rol,
                            "Jefe": x.es_jefe,
                            **{d: ", ".join(x.disponibilidad.get(d, [])) for d in config.dias},
                            "Máximo": ", ".join(f"{d}: {n}" for d, n in x.max_turnos.items()),
                            "Lugares": ", ".join(next(iter(x.lugares.values()), [])),
                            "Auto": ", ".join(sorted(x.auto)),
                            "Guarda": ", ".join(sorted(x.bodega)),
                        }
                        for x in lectura.voluntarios
                    ]
                ),
                hide_index=True,
                width="stretch",
            )
        ESTADO["lectura"] = lectura
        ESTADO["huella_entrada"] = _huella(config.to_json(), formato, mapa, pd.util.hash_pandas_object(df).sum())


# ---------------------------------------------------------------------------
# 4. Resultados
# ---------------------------------------------------------------------------


@st.cache_data(show_spinner=False, max_entries=500)
def _ubicar(direccion: str, comuna: str) -> tuple[float, float] | None:
    punto = geo.geocodificar(direccion, comuna)
    return (punto.lat, punto.lon) if punto else None


def _mapa_de_calor(cob: pd.DataFrame, dia: str) -> alt.Chart:
    datos = cob[cob["dia"] == dia]
    base = alt.Chart(datos).encode(
        x=alt.X("bloque:N", sort=config.bloques, title=None, axis=alt.Axis(labelAngle=0, orient="top")),
        y=alt.Y("lugar:N", sort=config.nombres_lugares, title=None, axis=alt.Axis(labelLimit=260)),
    )
    celdas = base.mark_rect(stroke="white").encode(
        color=alt.Color("personas:Q", scale=alt.Scale(scheme="blues", domainMin=0), title="Personas"),
        tooltip=["lugar", "bloque", "personas"],
    )
    texto = base.mark_text().encode(
        text="personas:Q",
        color=alt.condition(alt.datum.personas > 2, alt.value("white"), alt.value("black")),
    )
    return (celdas + texto).properties(title=dia)


with tab_resultados:
    lectura = ESTADO.get("lectura")
    problemas_config = config.validar()
    if lectura is None:
        st.info("Primero sube las respuestas en la pestaña 3.")
    elif problemas_config:
        st.error("Corrige la configuración en la pestaña 1: " + " ".join(problemas_config))
    elif any(a.nivel == "error" for a in lectura.avisos):
        st.error("Hay errores en la lectura de respuestas (pestaña 3).")
    else:
        if st.button("⚙️ Asignar turnos", type="primary"):
            with st.spinner("Buscando la mejor asignación…"):
                resultado = resolver(config, lectura.voluntarios)
            ESTADO["resultado"] = resultado
            ESTADO["huella_resultado"] = ESTADO.get("huella_entrada")
            ESTADO.pop("minutos", None)
            ESTADO.pop("puntos", None)

        resultado = ESTADO.get("resultado")
        if resultado is not None:
            if ESTADO.get("huella_resultado") != ESTADO.get("huella_entrada"):
                st.warning("Cambiaste la configuración o las respuestas: presiona **Asignar turnos** de nuevo.")
            if resultado.vacio:
                for a in resultado.avisos:
                    st.error(a)
            else:
                asignaciones = resultado.asignaciones
                vols = lectura.voluntarios
                res = resumen(config, vols, asignaciones)
                m1, m2, m3, m4 = st.columns(4)
                m1.metric(
                    "Personas con turno",
                    f"{res['con_turno']} de {res['personas']}",
                    f"{res['porcentaje_con_turno']:.0f}%",
                    delta_color="off",
                )
                m2.metric("Turnos asignados", res["turnos"])
                m3.metric("Bloques cubiertos", f"{res['bloques_cubiertos']} de {res['bloques_totales']}")
                m4.metric(
                    "Tiempo de cálculo",
                    f"{resultado.segundos:.1f} s",
                    "óptimo" if resultado.optimo else "límite de tiempo",
                    delta_color="off",
                )

                bodegas_df, avisos_bodega = None, []
                if config.reglas.asignar_bodegas:
                    bodegas_df, avisos_bodega = asignar_bodegas(config, vols, asignaciones, ESTADO.get("minutos"))
                todos_avisos = resultado.avisos + avisos_bodega
                for a in todos_avisos:
                    st.warning(a)

                st.download_button(
                    "📥 Descargar planner (Excel)",
                    planner_excel(config, vols, asignaciones, bodegas_df, todos_avisos),
                    file_name=f"planner_{config.nombre.lower().replace(' ', '_')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary",
                )

                st.subheader("Ocupación por bloque")
                cob = cobertura(config, asignaciones)
                for d in config.dias:
                    st.altair_chart(_mapa_de_calor(cob, d), width="stretch", height=45 * len(config.lugares) + 70)

                st.subheader("Turnos por persona")
                st.dataframe(por_persona(config, vols, asignaciones), hide_index=True, width="stretch")

                faltan = sin_turno(vols, asignaciones)
                st.subheader(f"Sin turno ({len(faltan)})")
                if faltan.empty:
                    st.success("Todas las personas que asisten tienen al menos un turno.")
                else:
                    st.dataframe(faltan, hide_index=True, width="stretch")

                if config.reglas.asignar_bodegas:
                    st.subheader("Casas-bodega y mapa")
                    st.dataframe(bodegas_df.dropna(axis=1, how="all"), hide_index=True, width="stretch")
                    st.caption(
                        "El mapa busca las direcciones en OpenStreetMap (se envían las direcciones de los lugares y de "
                        "las casas-bodega, sin nombres) y calcula tiempos en auto. Con tiempos, la casa-bodega se elige "
                        "por cercanía."
                    )
                    if st.button("🗺️ Ubicar en el mapa y calcular tiempos"):
                        candidatos = [x for x in vols if x.bodega and x.direccion]
                        puntos_lugar, puntos_casa = {}, {}
                        barra = st.progress(0.0, "Buscando direcciones…")
                        total = len(config.lugares) + len(candidatos)
                        for i, lugar in enumerate(config.lugares):
                            puntos_lugar[lugar.nombre] = _ubicar(lugar.direccion or lugar.nombre, lugar.comuna)
                            barra.progress((i + 1) / total, "Buscando direcciones…")
                        for j, x in enumerate(candidatos):
                            puntos_casa[x.id] = _ubicar(x.direccion, x.comuna)
                            barra.progress((len(config.lugares) + j + 1) / total, "Buscando direcciones…")
                        barra.empty()
                        origenes = [(n, p) for n, p in puntos_lugar.items() if p]
                        destinos = [(k, p) for k, p in puntos_casa.items() if p]
                        matriz, real = geo.tiempos_auto(
                            [geo.Punto(*p) for _, p in origenes], [geo.Punto(*p) for _, p in destinos]
                        )
                        ESTADO["minutos"] = {
                            (origenes[i][0], destinos[j][0]): matriz[i][j]
                            for i in range(len(origenes))
                            for j in range(len(destinos))
                        }
                        ESTADO["puntos"] = {"lugares": puntos_lugar, "casas": puntos_casa, "osrm": real}
                        st.rerun()

                    puntos = ESTADO.get("puntos")
                    if puntos:
                        no_ubicados = [n for n, p in {**puntos["lugares"]}.items() if not p]
                        no_ubicados += [x.nombre for x in vols if x.id in puntos["casas"] and not puntos["casas"][x.id]]
                        if no_ubicados:
                            st.warning(
                                "No se encontraron en el mapa: " + ", ".join(no_ubicados) + ". Revisa esas direcciones."
                            )
                        if not puntos["osrm"]:
                            st.info("El servicio de rutas no respondió; los tiempos son estimados en línea recta.")
                        por_nombre = {x.nombre: x for x in vols}
                        filas = [
                            {"nombre": n, "tipo": "Lugar", "lat": p[0], "lon": p[1], "color": [220, 60, 60]}
                            for n, p in puntos["lugares"].items()
                            if p
                        ]
                        filas += [
                            {
                                "nombre": f"Casa de {x.nombre}",
                                "tipo": "Casa-bodega",
                                "lat": p[0],
                                "lon": p[1],
                                "color": [40, 110, 220],
                            }
                            for x in vols
                            if (p := puntos["casas"].get(x.id))
                        ]
                        lineas = []
                        for _, f in bodegas_df.iterrows():
                            x = por_nombre.get(f["Casa-bodega"])
                            a, b = puntos["lugares"].get(f["Lugar"]), puntos["casas"].get(x.id) if x else None
                            if a and b:
                                lineas.append(
                                    {
                                        "desde": [a[1], a[0]],
                                        "hasta": [b[1], b[0]],
                                        "nombre": f"{f['Día']}: {f['Lugar']} → {x.nombre}",
                                    }
                                )
                        if filas:
                            puntos_df = pd.DataFrame(filas)
                            st.pydeck_chart(
                                pdk.Deck(
                                    initial_view_state=pdk.ViewState(
                                        latitude=puntos_df["lat"].mean(), longitude=puntos_df["lon"].mean(), zoom=12
                                    ),
                                    layers=[
                                        pdk.Layer(
                                            "LineLayer",
                                            pd.DataFrame(lineas),
                                            get_source_position="desde",
                                            get_target_position="hasta",
                                            get_color=[90, 90, 90],
                                            get_width=3,
                                            pickable=True,
                                        ),
                                        pdk.Layer(
                                            "ScatterplotLayer",
                                            puntos_df,
                                            get_position=["lon", "lat"],
                                            get_fill_color="color",
                                            get_radius=120,
                                            pickable=True,
                                        ),
                                    ],
                                    tooltip={"text": "{nombre}"},
                                )
                            )
                            st.caption("🔴 Lugares · 🔵 Casas-bodega · líneas: asignación de cada día")
                        if ESTADO.get("minutos"):
                            tabla = pd.DataFrame(
                                [
                                    {
                                        "Lugar": lugar,
                                        "Casa-bodega": next((x.nombre for x in vols if x.id == vid), vid),
                                        "Minutos en auto": round(mins),
                                    }
                                    for (lugar, vid), mins in ESTADO["minutos"].items()
                                ]
                            )
                            st.markdown("**Tiempos en auto (minutos)**")
                            st.dataframe(
                                tabla.pivot(index="Casa-bodega", columns="Lugar", values="Minutos en auto"),
                                width="stretch",
                            )
