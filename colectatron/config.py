"""Configuración de una colecta: días, bloques, lugares y reglas del modelo.

Todo lo que antes estaba escrito en el código (horarios, días, capacidad, pesos)
vive aquí y se puede guardar/cargar como JSON desde la app.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

# Deben coincidir con ejemplos/config_*.json (lo verifica tests/test_reportes_y_bodegas.py).
BLOQUES_FINANCIAMIENTO = [
    "7:00 - 8:30",
    "8:30 - 10:00",
    "10:00 - 11:30",
    "11:30 - 13:00",
    "13:00 - 14:30",
    "14:30 - 16:00",
    "16:00 - 17:30",
    "17:30 - 19:00",
    "19:00 - 20:00",
]
BLOQUES_INSUMOS = [
    "10:00 - 11:30",
    "11:30 - 13:00",
    "13:00 - 14:30",
    "14:30 - 16:00",
    "16:00 - 17:30",
    "17:30 - 19:00",
    "19:00 - 20:30",
    "20:30 - 21:30",
]

# Los bloques extremos pesan menos: se prefiere cubrir el centro del día (10 si no aparece).
PESOS_BLOQUE_FINANCIAMIENTO = {"7:00 - 8:30": 8, "19:00 - 20:00": 5}
PESOS_BLOQUE_INSUMOS = {b: 8 for b in BLOQUES_INSUMOS[:6]} | {"19:00 - 20:30": 5, "20:30 - 21:30": 5}

TIPO_FINANCIAMIENTO = "financiamiento"
TIPO_INSUMOS = "insumos"


@dataclass
class Lugar:
    nombre: str
    direccion: str = ""
    comuna: str = ""
    capacidad: int = 5


@dataclass
class Reglas:
    # Quien no es jefe no puede quedar solo en un bloque.
    nadie_solo: bool = True
    # Cada lugar abre en un horario continuo (sin huecos a mitad del día).
    horario_continuo_por_lugar: bool = False
    # En el último bloque abierto de cada lugar debe haber alguien con auto
    # (traslado de cierre a la bodega). Si no se puede, se avisa.
    auto_al_cierre: bool = False
    # Premia tener personas con auto repartidas durante el día (traslados intermedios).
    autos_durante_el_dia: bool = False
    # Asigna a cada lugar abierto una casa-bodega por día.
    asignar_bodegas: bool = False


@dataclass
class Pesos:
    """Pesos de la función objetivo. Mientras más grande, más importa."""

    cobertura: float = 1000  # por cada bloque (día, horario, lugar) cubierto
    por_persona: float = 100  # por cada persona que recibe al menos un turno
    jefe: float = 500  # por cada turno asignado a un jefe
    falta_auto_al_cierre: float = 400  # castigo si el cierre queda sin auto
    auto_presente: float = 20  # por cada bloque con alguien con auto
    bloque: dict[str, float] = field(default_factory=dict)  # peso por turno; 10 si no aparece

    def peso_bloque(self, bloque: str) -> float:
        return self.bloque.get(bloque, 10)


@dataclass
class TextosForm:
    """Textos del Google Form que no afectan la lectura: invitación, chistes y despedida.

    Los títulos de las preguntas que la app lee están fijos en `plantilla_form`.
    """

    titulo: str
    invitacion: str
    roles: list[str]
    ayuda_rol: str
    opcion_si: str  # debe empezar con "Sí"
    opcion_no: str  # debe empezar con "No"
    pregunta_chiste: str
    opciones_chiste: list[str]
    chiste_obligatorio: bool
    despedida: str
    foto_url: str = ""


@dataclass
class ConfigColecta:
    nombre: str
    tipo: str
    dias: list[str]
    bloques: list[str]
    lugares: list[Lugar]
    # Respuestas de la pregunta de rol que cuentan como jefe (texto exacto o parcial).
    roles_jefe: list[str] = field(default_factory=list)
    reglas: Reglas = field(default_factory=Reglas)
    pesos: Pesos = field(default_factory=Pesos)
    tiempo_limite_s: float = 60
    mip_gap: float = 0.01
    # Textos del Form; None = los de la plantilla (ver plantilla_form.textos_de).
    form: TextosForm | None = None

    @property
    def nombres_lugares(self) -> list[str]:
        return [lugar.nombre for lugar in self.lugares]

    def lugar(self, nombre: str) -> Lugar:
        for lugar in self.lugares:
            if lugar.nombre == nombre:
                return lugar
        raise KeyError(nombre)

    def validar(self) -> list[str]:
        """Devuelve una lista de problemas; vacía si la configuración sirve."""
        problemas = []
        if not self.dias:
            problemas.append("Falta al menos un día.")
        if not self.bloques:
            problemas.append("Falta al menos un bloque horario.")
        if not self.lugares:
            problemas.append("Falta al menos un lugar.")
        for grupo, nombre in ((self.dias, "días"), (self.bloques, "bloques"), (self.nombres_lugares, "lugares")):
            repetidos = {x for x in grupo if grupo.count(x) > 1}
            if repetidos:
                problemas.append(f"Hay {nombre} repetidos: {', '.join(sorted(repetidos))}.")
        for lugar in self.lugares:
            if not lugar.nombre.strip():
                problemas.append("Hay un lugar sin nombre.")
            if lugar.capacidad < 1:
                problemas.append(f"La capacidad de «{lugar.nombre}» debe ser al menos 1.")
        return problemas

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> ConfigColecta:
        data = dict(data)
        data["lugares"] = [Lugar(**lugar) for lugar in data.get("lugares", [])]
        data["reglas"] = Reglas(**data.get("reglas", {}))
        data["pesos"] = Pesos(**data.get("pesos", {}))
        if data.get("form"):
            data["form"] = TextosForm(**data["form"])
        return cls(**data)

    @classmethod
    def from_json(cls, texto: str) -> ConfigColecta:
        return cls.from_dict(json.loads(texto))


def config_financiamiento() -> ConfigColecta:
    """Colecta de dinero en esquinas (viernes y sábado)."""
    return ConfigColecta(
        nombre="Colecta de financiamiento",
        tipo=TIPO_FINANCIAMIENTO,
        dias=["Viernes", "Sábado"],
        bloques=list(BLOQUES_FINANCIAMIENTO),
        lugares=[
            Lugar("Francisco Bilbao con Tobalaba", comuna="Providencia"),
            Lugar("Los Leones con Eliodoro Yáñez", comuna="Providencia"),
            Lugar("Tobalaba con El Bosque", comuna="Providencia"),
            Lugar("Holanda con Pocuro", comuna="Providencia"),
        ],
        roles_jefe=["Jefx de comisión", "Familia", "Staff", "Voluntario/a"],
        reglas=Reglas(nadie_solo=True),
        pesos=Pesos(bloque=dict(PESOS_BLOQUE_FINANCIAMIENTO)),
    )


def config_insumos() -> ConfigColecta:
    """Colecta de insumos en supermercados (sábado y domingo)."""
    return ConfigColecta(
        nombre="Colecta de insumos",
        tipo=TIPO_INSUMOS,
        dias=["Sábado", "Domingo"],
        bloques=list(BLOQUES_INSUMOS),
        lugares=[
            Lugar("Unimarc Irarrázaval", "Av. Irarrázaval 4354", "Ñuñoa", 4),
            Lugar("Unimarc Príncipe de Gales", "Príncipe de Gales 7271", "La Reina", 4),
            Lugar("Unimarc Los Militares", "Av. Manquehue Norte 457", "Las Condes", 4),
        ],
        # Siempre hay un jefe de insumos en el local: no hace falta priorizar ni proteger.
        roles_jefe=[],
        reglas=Reglas(
            nadie_solo=False,
            horario_continuo_por_lugar=True,
            auto_al_cierre=True,
            autos_durante_el_dia=True,
            asignar_bodegas=True,
        ),
        pesos=Pesos(jefe=0, bloque=dict(PESOS_BLOQUE_INSUMOS)),
    )


PLANTILLAS = {
    TIPO_FINANCIAMIENTO: config_financiamiento,
    TIPO_INSUMOS: config_insumos,
}
