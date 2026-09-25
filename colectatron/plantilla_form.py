"""Plantilla del Google Form unificado.

Los títulos de las preguntas están aquí una sola vez: los usa el script que
crea el Form, el generador de datos de ejemplo y (por palabras clave) el lector.
"""

from __future__ import annotations

import json
from datetime import date

from .config import TIPO_INSUMOS, ConfigColecta, TextosForm

P_NOMBRE = "Nombre completo"
P_TELEFONO = "Número de teléfono (formato +569XXXXXXXX)"
P_ASISTE = "¿Puedes ir a la colecta?"
P_ROL = "¿Eres...? (declaración formal de rol)"
P_BLOQUES = "¿Qué bloques puedes?"
P_MAXIMO = "¿Cuántos bloques como máximo por día?"
P_LUGARES = "¿En qué lugares puedes?"
P_AUTO = "¿Qué días tienes auto disponible?"
P_BODEGA = "¿Qué días puedes guardar insumos en tu casa?"
P_DIRECCION = "Dirección donde guardarías los insumos"
P_COMUNA = "Comuna"
P_COMENTARIOS = "Comentarios"

# Encabezado que pone Google al recolectar correos (Form en español).
COL_CORREO = "Dirección de correo electrónico"
COL_MARCA = "Marca temporal"

OPCIONES_MAXIMO = ["1", "2", "3", "4", "Sin límite"]
DONDE_ME_NECESITEN = "Donde me necesiten"
SIN_AUTO = "No tengo auto"
SIN_BODEGA = "No puedo"

# Roles de financiamiento: a inicios de junio salen los resultados de inscripción a los
# trabajos voluntarios; desde ahí existe Staff. En insumos no se pregunta el rol, porque
# siempre hay un jefe de la comisión a cargo del supermercado.
ROLES_ANTES_DE_RESULTADOS = ["Familia", "Voluntario/a"]
ROLES_DESPUES_DE_RESULTADOS = ["Familia", "Staff", "Voluntario/a"]
MES_RESULTADOS = 6


def resultados_publicados(hoy: date | None = None) -> bool:
    """Si ya salieron los resultados de inscripción (desde junio hasta fin de año)."""
    return (hoy or date.today()).month >= MES_RESULTADOS


def roles_financiamiento(resultados: bool) -> list[str]:
    return list(ROLES_DESPUES_DE_RESULTADOS if resultados else ROLES_ANTES_DE_RESULTADOS)


def _enumerar(cosas: list[str]) -> str:
    if len(cosas) <= 1:
        return "".join(cosas)
    return ", ".join(cosas[:-1]) + " y " + cosas[-1]


def textos_por_defecto(config: ConfigColecta, resultados: bool | None = None) -> TextosForm:
    """Textos con el espíritu del Form de la primera colecta del año.

    `resultados`: si ya salieron los resultados de inscripción (define si se ofrece Staff).
    Por defecto se decide por la fecha de hoy.
    """
    if resultados is None:
        resultados = resultados_publicados()
    insumos = config.tipo == TIPO_INSUMOS
    dias = _enumerar([d.lower() for d in config.dias])
    lugares = _enumerar(config.nombres_lugares)
    donde = f"En los supermercados {lugares}." if insumos else f"En las esquinas {lugares}."
    para_que = "juntar los insumos del proyecto 📦" if insumos else "financiar el proyecto 💰"
    invitacion = (
        "¡Atención gente! Se viene una gran colecta y no se la pueden perder 💸💰\n\n"
        f"¿Cuándo? 📅 El {dias} (completa las fechas).\n"
        f"¿Dónde? 📍 {donde}\n\n"
        f"Motívense!! Es muy importante para {para_que}, así que denle con todo 💪💪💪!!\n\n"
        "LA ASIGNACIÓN DE TURNOS ESTÁ AUTOMATIZADA, ES TU RESPONSABILIDAD LLENAR BIEN EL FORMULARIO. "
        "(Si ofreces tres bloques, es probable que el algoritmo efectivamente te dé tres bloques seguidos)"
    )
    if insumos:
        return TextosForm(
            titulo="COLECTA DE INSUMOS 🛒🥫",
            invitacion=invitacion,
            roles=[],
            ayuda_rol="",
            opcion_si="Sí, voy con todo 🛒",
            opcion_no="No, odio a insumos 😔",
            pregunta_chiste="¿Cuál es tu mood insumístico? (importantísimo)",
            opciones_chiste=["Enlatado", "Congelado", "Vencido", "Aplastado", "A granel", "En oferta"],
            chiste_obligatorio=True,
            despedida="Atentamente, la comisión favorita de todxs, insumos 🛒🛒",
        )
    return TextosForm(
        titulo="COLECTA 🤑💵",
        invitacion=invitacion,
        roles=roles_financiamiento(resultados),
        ayuda_rol="Declaración formal de rol. Familia y Staff pueden quedar a cargo de una esquina; "
        "si no lo declaras, podrías quedar solx en una esquina...",
        opcion_si="Sí, voy con todo 🤑",
        opcion_no="No, odio a financiamiento 😔",
        pregunta_chiste="¿Cuál es tu mood financiero? (importantísimo)",
        opciones_chiste=["Demacrada", "Debilitado", "Destruida", "Desmejorado", "Depauperada", "Desmedrado"],
        chiste_obligatorio=True,
        despedida="Atentamente, la comisión favorita de todxs, financiamiento 🤑🤑",
    )


def textos_de(config: ConfigColecta) -> TextosForm:
    return config.form or textos_por_defecto(config)


def validar_textos(textos: TextosForm) -> list[str]:
    """Problemas que harían que la app no entienda las respuestas."""
    from .texto import es_si

    problemas = []
    if es_si(textos.opcion_si) is not True:
        problemas.append("La opción para asistir debe empezar con «Sí».")
    if es_si(textos.opcion_no) is not False:
        problemas.append("La opción para no asistir debe empezar con «No».")
    if textos.pregunta_chiste.strip() and not textos.opciones_chiste:
        problemas.append("La pregunta chiste necesita al menos una opción.")
    return problemas


def encabezados(config: ConfigColecta) -> list[str]:
    """Columnas que exporta Google Sheets para el Form generado con `script_apps`."""
    cols = [COL_MARCA, COL_CORREO, P_NOMBRE, P_TELEFONO]
    if textos_de(config).roles:
        cols.append(P_ROL)
    cols.append(P_ASISTE)
    cols += [f"{P_BLOQUES} [{b}]" for b in config.bloques]
    cols += [f"{P_MAXIMO} [{d}]" for d in config.dias]
    cols.append(P_LUGARES)
    if config.tipo == TIPO_INSUMOS:
        cols += [P_AUTO, P_BODEGA, P_DIRECCION, P_COMUNA]
    cols.append(P_COMENTARIOS)
    chiste = textos_de(config).pregunta_chiste.strip()
    if chiste:
        cols.append(chiste)
    return cols


def script_apps(config: ConfigColecta) -> str:
    """Código de Google Apps Script que crea el Form con esta configuración.

    Se pega en https://script.google.com (Nuevo proyecto), se guarda y se
    ejecuta la función `crearFormulario`.
    """
    textos = textos_de(config)
    datos = {
        "titulo": textos.titulo,
        "invitacion": textos.invitacion,
        "dias": config.dias,
        "bloques": config.bloques,
        "lugares": config.nombres_lugares,
        "roles": textos.roles,
        "ayudaRol": textos.ayuda_rol,
        "si": textos.opcion_si,
        "no": textos.opcion_no,
        "insumos": config.tipo == TIPO_INSUMOS,
        "maximo": OPCIONES_MAXIMO,
        "chiste": textos.pregunta_chiste.strip(),
        "opcionesChiste": textos.opciones_chiste,
        "chisteObligatorio": textos.chiste_obligatorio,
        "despedida": textos.despedida,
        "foto": textos.foto_url.strip(),
    }
    p = {
        "nombre": P_NOMBRE,
        "telefono": P_TELEFONO,
        "asiste": P_ASISTE,
        "rol": P_ROL,
        "bloques": P_BLOQUES,
        "maximo": P_MAXIMO,
        "lugares": P_LUGARES,
        "auto": P_AUTO,
        "bodega": P_BODEGA,
        "direccion": P_DIRECCION,
        "comuna": P_COMUNA,
        "comentarios": P_COMENTARIOS,
        "donde": DONDE_ME_NECESITEN,
        "sinAuto": SIN_AUTO,
        "sinBodega": SIN_BODEGA,
    }
    return _PLANTILLA_JS.replace("__DATOS__", json.dumps(datos, ensure_ascii=False, indent=2)).replace(
        "__PREGUNTAS__", json.dumps(p, ensure_ascii=False, indent=2)
    )


_PLANTILLA_JS = """\
// Crea el Google Form de inscripción para Colectatron8000.
// 1. Entra a https://script.google.com y crea un "Nuevo proyecto".
// 2. Borra lo que aparece, pega todo este código y guarda (ícono de disquete).
// 3. Arriba, elige la función "crearFormulario" y presiona "Ejecutar".
//    Google pedirá permisos la primera vez: acéptalos.
// 4. En "Registro de ejecución" aparecerán los links del Form.
// No cambies los títulos de las preguntas: la app los usa para leer las respuestas.
// Los textos de DATOS (invitación, chiste, despedida) sí se pueden cambiar.

const DATOS = __DATOS__;

const P = __PREGUNTAS__;

function crearFormulario() {
  const form = FormApp.create(DATOS.titulo);
  form.setTitle(DATOS.titulo);
  form.setDescription(
    DATOS.invitacion + '\\n\\n' +
    'Tus datos se usan solo para organizar la colecta y se borran al terminar.'
  );
  form.setConfirmationMessage('¡Gracias por inscribirte! 🙌 Te avisaremos tus turnos.');
  try {
    form.setEmailCollectionType(FormApp.EmailCollectionType.VERIFIED);
  } catch (e) {
    form.setCollectEmail(true);
  }

  form.addTextItem().setTitle(P.nombre).setRequired(true);
  form.addTextItem()
    .setTitle(P.telefono)
    .setRequired(true)
    .setValidation(
      FormApp.createTextValidation()
        .requireTextMatchesPattern('^\\\\+569\\\\d{8}$')
        .setHelpText('Escribe el número como +569XXXXXXXX')
        .build()
    );
  if (DATOS.roles.length) {
    form.addMultipleChoiceItem()
      .setTitle(P.rol)
      .setHelpText(DATOS.ayudaRol)
      .setChoiceValues(DATOS.roles)
      .setRequired(true);
  }
  const asiste = form.addMultipleChoiceItem().setTitle(P.asiste).setRequired(true);

  // --- Disponibilidad ---
  const disponibilidad = form.addPageBreakItem().setTitle('Disponibilidad 🗓️');
  form.addCheckboxGridItem()
    .setTitle(P.bloques)
    .setHelpText('Marca todos los bloques en que puedes estar, para cada día 🕐. Coloca todos los que puedas.')
    .setRows(DATOS.bloques)
    .setColumns(DATOS.dias);
  form.addGridItem()
    .setTitle(P.maximo)
    .setHelpText('Ojo: los bloques que te toquen serán seguidos 🤖')
    .setRows(DATOS.dias)
    .setColumns(DATOS.maximo);
  form.addCheckboxItem()
    .setTitle(P.lugares)
    .setChoiceValues(DATOS.lugares.concat([P.donde]))
    .setRequired(true);

  if (DATOS.insumos) {
    form.addPageBreakItem().setTitle('Automatización automática de autos 🚗');
    form.addCheckboxItem()
      .setTitle(P.auto)
      .setHelpText('Para llevar los insumos a la casa-bodega. Quien tenga auto también hace un turno en el supermercado.')
      .setChoiceValues(DATOS.dias.concat([P.sinAuto]))
      .setRequired(true);
    form.addCheckboxItem()
      .setTitle(P.bodega)
      .setHelpText('Tu casa sería la bodega de los insumos de ese día 🏠📦')
      .setChoiceValues(DATOS.dias.concat([P.sinBodega]))
      .setRequired(true);
    form.addTextItem()
      .setTitle(P.direccion)
      .setHelpText('Solo si puedes guardar insumos. Calle y número.');
    form.addTextItem().setTitle(P.comuna);
  }

  form.addParagraphTextItem()
    .setTitle(P.comentarios)
    .setHelpText('Cualquier cosa que debamos saber.');

  // --- Final: pregunta chiste y despedida (también para quienes no van) ---
  const final = form.addPageBreakItem().setTitle('Para terminar ✨');
  if (DATOS.chiste) {
    form.addMultipleChoiceItem()
      .setTitle(DATOS.chiste)
      .setChoiceValues(DATOS.opcionesChiste)
      .setRequired(DATOS.chisteObligatorio);
  }
  if (DATOS.foto) {
    try {
      form.addImageItem().setTitle(DATOS.despedida).setImage(obtenerImagen(DATOS.foto));
    } catch (e) {
      form.addSectionHeaderItem().setTitle(DATOS.despedida);
      Logger.log('No se pudo cargar la foto (' + e + '). Agrégala a mano: Insertar imagen.');
    }
  } else {
    form.addSectionHeaderItem().setTitle(DATOS.despedida);
    Logger.log('Recuerda agregar la foto de la comisión al final: Insertar imagen.');
  }

  asiste.setChoices([
    asiste.createChoice(DATOS.si, disponibilidad),
    asiste.createChoice(DATOS.no, final),
  ]);

  Logger.log('Para responder: ' + form.getPublishedUrl());
  Logger.log('Para editar:    ' + form.getEditUrl());
}

// Acepta un link de Google Drive ("compartir con cualquiera con el link") o un link directo a la imagen.
function obtenerImagen(url) {
  const id = url.match(/[-\\w]{25,}/);
  if (url.indexOf('drive.google.com') >= 0 && id) {
    return DriveApp.getFileById(id[0]).getBlob();
  }
  return UrlFetchApp.fetch(url).getBlob();
}
"""
