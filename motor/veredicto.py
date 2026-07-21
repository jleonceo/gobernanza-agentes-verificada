#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
motor/veredicto.py — el tipo de retorno homogéneo del contrato + la agregación.

EXTRAÍDO de verificacion_determinista.py (el `Veredicto = namedtuple(...)` del
guardián determinista de TechAcces), DES-ACOPLADO del dominio contable: aquí no hay
cuadre ΣDebe/ΣHaber, ni tolerancias de céntimo, ni imports de motores de negocio.
Solo queda la pieza universal: un veredicto homogéneo y su agregación a semáforo.

CONTRATO (ver CONTRATO_DETECTOR.md §2):
    Veredicto(id, ok, esperado, obtenido, detalle)
    · id       : str   — id del invariante (p.ej. "INV-R1", "LINT-WIKILINK")
    · ok       : bool  — True = sano; False = defecto detectado
    · esperado : str   — qué se esperaba (texto normalizado, comparable)
    · obtenido : str   — qué se obtuvo (texto normalizado, comparable)
    · detalle  : str   — explicación humana (NO se usa para comparar veredictos)

La SEVERIDAD no vive en el Veredicto ni en el detector: llega desde
config/invariantes.yaml (por `id`). El detector solo dice ok=True/False; es el
runner quien mapea id -> severidad -> semáforo agregado. Por eso la agregación
recibe el mapa {id: severidad} desde fuera y NUNCA lo inventa.

Determinista, stdlib puro, READ-ONLY. No imprime, no escribe.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Veredicto:
    """Veredicto homogéneo de cualquier detector determinista (contrato §2).

    frozen=True: inmutable, hashable y comparable por valor — un Veredicto es un
    HECHO producido por el detector, no un objeto mutable. Que sea comparable por
    valor permite al verificador_minimo (método 2) contrastar sin ambigüedad.
    """
    id: str
    ok: bool
    esperado: str
    obtenido: str
    detalle: str


# --- Semáforo agregado -----------------------------------------------------
# Los tres estados del sistema (fijos, agnósticos a la empresa — SPEC FIJO #2).
SANO = "SANO"
VIGILAR = "VIGILAR"
ENFERMO = "ENFERMO"

# Severidades reconocidas. "alta" -> ENFERMO; "media"/"baja"/aviso -> VIGILAR.
# El mapeo es FIJO; qué id tiene qué severidad es VARIABLE (invariantes.yaml).
SEVERIDADES_ALTAS = frozenset({"alta", "critica", "critical", "high"})


def veredicto_de_uno(v, severidad):
    """Semáforo que le corresponde a un único Veredicto según su severidad.

    · ok=True                       -> SANO   (no importa la severidad)
    · ok=False y severidad alta     -> ENFERMO
    · ok=False y severidad media/baja/aviso -> VIGILAR
    """
    if v.ok:
        return SANO
    if (severidad or "").strip().lower() in SEVERIDADES_ALTAS:
        return ENFERMO
    return VIGILAR


def agregar(veredictos, severidades):
    """Agrega una lista de Veredicto a un semáforo SANO/VIGILAR/ENFERMO.

    `severidades`: dict {id -> severidad} proveniente de invariantes.yaml. La
    severidad NUNCA la decide el detector (SPEC/CONTRATO §2): la inyecta el runner.

    Regla de agregación (peor caso manda):
      - algún ok=False de severidad alta        -> ENFERMO
      - si no, algún ok=False (media/baja/aviso) -> VIGILAR
      - todos ok=True                            -> SANO

    Un id sin severidad declarada se trata como aviso (VIGILAR si falla), NUNCA se
    silencia a SANO: un defecto sin clasificar no puede colar un falso verde.
    """
    severidades = severidades or {}
    hay_enfermo = False
    hay_vigilar = False
    for v in veredictos:
        if v.ok:
            continue
        estado = veredicto_de_uno(v, severidades.get(v.id))
        if estado == ENFERMO:
            hay_enfermo = True
        else:
            hay_vigilar = True
    if hay_enfermo:
        return ENFERMO
    if hay_vigilar:
        return VIGILAR
    return SANO
