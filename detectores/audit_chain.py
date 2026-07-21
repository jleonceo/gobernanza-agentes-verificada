#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
audit_chain.py — Detector del audit trail encadenado (STANDALONE, des-acoplado).
================================================================================

Verifica la INTEGRIDAD y el ORDEN de un audit trail tamper-evident (hash chain
SHA-256) recomputando la cadena génesis -> cola. READ-ONLY absoluto: NO escribe (la
única función que escribe es `motor.audit_trail.anexar`, opt-in, y este detector no la
llama). CERO literal de ruta: la ruta del trail llega de config vía `ctx.audit_trail`
y se resuelve relativa a `ctx.root` (nunca expanduser).

CONTRATO (CONTRATO_DETECTOR.md): `run(ctx) -> list[Veredicto]`.
- Devuelve SIEMPRE una lista. No imprime. No escribe.
- INERTE cuando NO hay trail (`return []`): así no ensucia los runs de routing/lint
  (sus fixtures no tienen trail y siguen SANO), y la cobertura-motor no se rompe.

INVARIANTES QUE EMITE (solo ON-DEMAND, cuando hay trail Y está roto)
--------------------------------------------------------------------
· INV-AUDIT-CADENA    : una huella recomputada no casa con la almacenada.
· INV-AUDIT-ENLACE    : el prev de una entrada no casa con la huella real de la anterior.
· INV-AUDIT-SECUENCIA : seq no contiguo desde 0 (hueco, salto, reordenación).

Los tres se declaran en invariantes.yaml -> severidades_on_demand (severidad alta ->
ENFERMO), NO en la lista contada: sobre las fixtures de routing (sin trail) este
detector devuelve [], así que meterlos en la lista contada rompería la cobertura-motor
(declarados != ejecutados) — mismo criterio que INV-R4 / RESULT-CONTRACT.
"""

from pathlib import Path

# BOOTSTRAP de sys.path (para el uso STANDALONE `python detectores/audit_chain.py` y
# para que `import motor.*` resuelva). Idempotente cuando lo importa el runner (la raíz
# ya está en sys.path). READ-ONLY, sin efectos fuera del proceso.
import sys as _sys
_RAIZ_KIT = Path(__file__).resolve().parent.parent
if str(_RAIZ_KIT) not in _sys.path:
    _sys.path.insert(0, str(_RAIZ_KIT))

from motor.runner import registrar
from motor import audit_trail


def _get(obj, key, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _audit_cfg(ctx):
    """Config del trail inyectada en ctx (audit_trail.yaml). Si el ctx no la expone
    (p.ej. un ctx de un tercero sin este bloque), degrada a {} -> detector inerte."""
    ac = _get(ctx, "audit_trail")
    if ac is None:
        cfg = _get(ctx, "config")
        ac = _get(cfg, "audit_trail")
    return ac or {}


def _trail_path(ctx):
    """Ruta RELATIVA del trail desde config (audit_trail.trail_path). Sin literal en el
    módulo: si no está declarada, None -> detector inerte (degrada con gracia)."""
    return _get(_audit_cfg(ctx), "trail_path")


@registrar("audit_chain")
def run(ctx):
    """Detector del audit trail. Devuelve list[Veredicto]. READ-ONLY.

    - Sin trail declarado o sin fichero de trail -> [] (INERTE): las fixtures de routing/
      lint no llevan trail, así que aquí no se emite nada y siguen SANO.
    - Con trail -> lo lee con `ctx.read_text` (READ-ONLY vía helpers del ctx), lo carga
      con `audit_trail.cargar` (recibe TEXTO, AMB-2) y recomputa la cadena con
      `audit_trail.verificar_cadena`.
    """
    trail = _trail_path(ctx)
    if not trail:
        return []
    if not ctx.existe(trail):
        return []                                       # inerte donde no hay trail
    entradas = audit_trail.cargar(ctx.read_text(trail))  # READ-ONLY vía helpers de ctx
    return audit_trail.verificar_cadena(entradas)
