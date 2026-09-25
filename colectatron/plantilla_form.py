"""Plantilla del Google Form unificado.

Los títulos de las preguntas están aquí una sola vez: los usa el script que
crea el Form, el generador de datos de ejemplo y (por palabras clave) el lector.
"""

from __future__ import annotations

import json

from .config import TIPO_INSUMOS, ConfigColecta

P_NOMBRE = "Nombre y apellido"
P_TELEFONO = "Teléfono (WhatsApp)"
P_ASISTE = "¿Vas a asistir a la colecta?"
P_ROL = "¿Cuál es tu rol?"
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

ROLES_POR_DEFECTO = {
    "financiamiento": ["Comisionado/a", "Familia", "Staff"],
    "insumos": ["Comisionado/a", "Jefe/a de insumos", "Voluntario/a"],
}


def encabezados(config: ConfigColecta) -> list[str]:
    """Columnas que exporta Google Sheets para el Form generado con `script_apps`."""
    cols = [COL_MARCA, COL_CORREO, P_NOMBRE, P_TELEFONO, P_ROL, P_ASISTE]
    cols += [f"{P_BLOQUES} [{b}]" for b in config.bloques]
    cols += [f"{P_MAXIMO} [{d}]" for d in config.dias]
    cols.append(P_LUGARES)
    if config.tipo == TIPO_INSUMOS:
        cols += [P_AUTO, P_BODEGA, P_DIRECCION, P_COMUNA]
    cols.append(P_COMENTARIOS)
    return cols


def script_apps(config: ConfigColecta, roles: list[str] | None = None) -> str:
    """Código de Google Apps Script que crea el Form con esta configuración.

    Se pega en https://script.google.com (Nuevo proyecto), se guarda y se
    ejecuta la función `crearFormulario`.
    """
    roles = roles or ROLES_POR_DEFECTO.get(config.tipo, ROLES_POR_DEFECTO["financiamiento"])
    datos = {
        "titulo": config.nombre,
        "dias": config.dias,
        "bloques": config.bloques,
        "lugares": config.nombres_lugares,
        "roles": roles,
        "insumos": config.tipo == TIPO_INSUMOS,
        "maximo": OPCIONES_MAXIMO,
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
// Los chistes y emojis pueden ir en las descripciones (setHelpText), que no se exportan.

const DATOS = __DATOS__;

const P = __PREGUNTAS__;

function crearFormulario() {
  const form = FormApp.create(DATOS.titulo);
  form.setDescription(
    'Inscripción de turnos. Tus datos se usan solo para organizar la colecta ' +
    'y se borran al terminar.'
  );
  try {
    form.setEmailCollectionType(FormApp.EmailCollectionType.VERIFIED);
  } catch (e) {
    form.setCollectEmail(true);
  }

  form.addTextItem().setTitle(P.nombre).setRequired(true);
  form.addTextItem()
    .setTitle(P.telefono)
    .setHelpText('Formato +569XXXXXXXX')
    .setRequired(true)
    .setValidation(
      FormApp.createTextValidation()
        .requireTextMatchesPattern('^\\\\+569\\\\d{8}$')
        .setHelpText('Escribe el número como +569XXXXXXXX')
        .build()
    );
  form.addListItem().setTitle(P.rol).setChoiceValues(DATOS.roles).setRequired(true);

  const asiste = form.addMultipleChoiceItem().setTitle(P.asiste).setRequired(true);

  // Si responde "No", el Form se envía de inmediato.
  const pagina = form.addPageBreakItem().setTitle('Disponibilidad');
  asiste.setChoices([
    asiste.createChoice('Sí', pagina),
    asiste.createChoice('No', FormApp.PageNavigationType.SUBMIT),
  ]);

  form.addCheckboxGridItem()
    .setTitle(P.bloques)
    .setHelpText('Marca todos los bloques en que puedes estar, para cada día.')
    .setRows(DATOS.bloques)
    .setColumns(DATOS.dias);
  form.addGridItem()
    .setTitle(P.maximo)
    .setHelpText('Los bloques que te asignemos serán seguidos.')
    .setRows(DATOS.dias)
    .setColumns(DATOS.maximo);
  form.addCheckboxItem()
    .setTitle(P.lugares)
    .setChoiceValues(DATOS.lugares.concat([P.donde]))
    .setRequired(true);

  if (DATOS.insumos) {
    form.addCheckboxItem()
      .setTitle(P.auto)
      .setHelpText('Para llevar los insumos a la casa-bodega. Quien tenga auto hará un turno en el supermercado.')
      .setChoiceValues(DATOS.dias.concat([P.sinAuto]));
    form.addCheckboxItem()
      .setTitle(P.bodega)
      .setChoiceValues(DATOS.dias.concat([P.sinBodega]));
    form.addTextItem()
      .setTitle(P.direccion)
      .setHelpText('Solo si puedes guardar insumos. Calle, número y comuna.');
    form.addTextItem().setTitle(P.comuna);
  }

  form.addParagraphTextItem().setTitle(P.comentarios);

  Logger.log('Para responder: ' + form.getPublishedUrl());
  Logger.log('Para editar:    ' + form.getEditUrl());
}
"""
