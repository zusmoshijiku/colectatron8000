"""Utilidades para comparar textos escritos por personas (acentos, emojis, espacios)."""

from __future__ import annotations

import re
import unicodedata

import pandas as pd


def normalizar(texto) -> str:
    """Minúsculas, sin acentos, sin emojis y con espacios simples.

    >>> normalizar("  Sí voy con todo🤑 ")
    'si voy con todo'
    """
    if texto is None or (isinstance(texto, float) and pd.isna(texto)):
        return ""
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower()
    # Deja letras, números y la puntuación que importa en horarios ("7:00 - 8:30").
    texto = re.sub(r"[^a-z0-9:\-+@. ]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def vacio(valor) -> bool:
    return normalizar(valor) == ""


def es_si(valor) -> bool | None:
    """True para "Sí…", False para "No…", None si no se entiende o está vacío."""
    n = normalizar(valor)
    if not n:
        return None
    if n == "si" or n.startswith("si "):
        return True
    if n == "no" or n.startswith("no "):
        return False
    return None


def normalizar_bloque(texto) -> str:
    """Horario sin espacios, para comparar "7:00-8:30" con "7:00 - 8:30"."""
    return normalizar(texto).replace(" ", "")


def minutos_inicio(bloque: str) -> int | None:
    """Minutos desde medianoche del inicio de un bloque "HH:MM - HH:MM"."""
    m = re.match(r"\s*(\d{1,2})[:.](\d{2})", str(bloque))
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def parece_bloque(texto: str) -> bool:
    return re.match(r"^\s*\d{1,2}[:.]\d{2}\s*-\s*\d{1,2}[:.]\d{2}\s*$", str(texto)) is not None
