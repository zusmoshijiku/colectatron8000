from __future__ import annotations

import pytest

from colectatron.config import ConfigColecta, Lugar, Pesos, Reglas
from colectatron.formulario import Voluntario

BLOQUES = ["9:00 - 10:00", "10:00 - 11:00", "11:00 - 12:00", "12:00 - 13:00"]


@pytest.fixture
def config_chica() -> ConfigColecta:
    return ConfigColecta(
        nombre="Prueba",
        tipo="insumos",
        dias=["Sábado"],
        bloques=list(BLOQUES),
        lugares=[Lugar("A", comuna="Ñuñoa", capacidad=3), Lugar("B", comuna="Providencia", capacidad=3)],
        reglas=Reglas(nadie_solo=False),
        pesos=Pesos(),
    )


def persona(
    id: str,
    bloques: list[str] | None = None,
    maximo: int = 4,
    lugares: list[str] | None = None,
    dia: str = "Sábado",
    jefe: bool = False,
    auto: bool = False,
    bodega: bool = False,
    comuna: str = "",
) -> Voluntario:
    bloques = BLOQUES if bloques is None else bloques
    return Voluntario(
        id=id,
        fila=1,
        nombre=id,
        es_jefe=jefe,
        disponibilidad={dia: list(bloques)},
        max_turnos={dia: maximo},
        lugares={dia: lugares or ["A", "B"]},
        auto={dia} if auto else set(),
        bodega={dia} if bodega else set(),
        direccion="Calle 1" if bodega else "",
        comuna=comuna,
    )
