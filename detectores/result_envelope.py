#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
result_envelope.py — Detector que ENVUELVE el result_contract (STANDALONE).
============================================================================

Puente entre `contrato/result_contract.py` (validador stdlib puro del envelope de
handoff) y el CONTRATO del detector `run(ctx) -> list[Veredicto]`. El validador vive
aparte a propósito (stdlib puro, sin PyYAML, sin motor/); este wrapper lo pasea por el
registro del runner para que el envelope entre en el mismo semáforo que routing y lint.

CONTRATO (CONTRATO_DETECTOR.md): `run(ctx) -> list[Veredicto]`.
- READ-ONLY. No imprime. No escribe. Devuelve SIEMPRE una lista.
- CERO patrón de parseo hardcodeado: el nombre del fichero envelope y el glob se leen
  de ctx.routing_paths (envelope_glob); el parseo lo hace result_contract (stdlib).

INVARIANTE QUE EMITE
--------------------
· RESULT-CONTRACT (DURO -> ENFERMO si falla): cada envelope.json del corpus cumple la
  gramática del contrato de handoff (status/risk en enum, campos presentes, y la regla
  dura BLOCKED|ERROR => summary no vacío). Un envelope que rompe el contrato -> FALLO.

Igual que INV-R4 en gate_routing, RESULT-CONTRACT se emite SÓLO cuando hay al menos un
envelope que ROMPE el contrato. Sobre un corpus con envelopes válidos (o sin envelopes)
no se emite, de modo que el conjunto de ids ejecutados sobre las fixtures LIMPIAS sigue
siendo exactamente {INV-R1, LINT-WIKILINK, INV-PANEL} (cobertura-motor intacta). Sobre
las fixtures rotas 04/05 aparece RESULT-CONTRACT en FALLO.
"""

from pathlib import Path

from motor.veredicto import Veredicto
from motor.runner import registrar
import contrato.result_contract as result_contract


def _get(obj, key, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _root(ctx):
    return Path(_get(ctx, "root"))


def _routing_paths(ctx):
    rp = _get(ctx, "routing_paths")
    if rp is None:
        cfg = _get(ctx, "config")
        rp = _get(cfg, "routing_paths")
    return rp or {}


def _envelope_glob(ctx):
    """Glob de los ficheros envelope del corpus. Sin literal en el módulo: llega de
    routing_paths.envelope_glob; si no está declarado, no se busca envelope alguno
    (degrada con gracia, no inventa un patrón hardcodeado)."""
    rp = _routing_paths(ctx)
    return _get(rp, "envelope_glob")


def _envelopes(ctx):
    """Ficheros envelope del corpus en orden canónico (sorted). READ-ONLY."""
    glob = _envelope_glob(ctx)
    if not glob:
        return []
    root = _root(ctx)
    return sorted(root.rglob(glob))


def _validar_uno(ctx, path):
    """Valida un envelope contra el result_contract. Devuelve (ok, motivo)."""
    root = _root(ctx)
    rel = path.relative_to(root).as_posix()
    texto = ctx.read_text(path)
    res = result_contract.validar(texto)
    if res.ok:
        return True, rel
    motivo = "; ".join(res.errores) or res.estado
    return False, "%s (%s)" % (rel, motivo)


def _result_contract(ctx):
    envs = _envelopes(ctx)
    fallos = []
    for p in envs:
        ok, info = _validar_uno(ctx, p)
        if not ok:
            fallos.append(info)
    ok = not fallos
    esperado = "envelopes_validos"
    obtenido = ("envelopes_validos" if ok else "envelopes_invalidos:" + " | ".join(fallos))
    detalle = ("todos los envelopes del corpus cumplen el contrato de handoff" if ok
               else "envelope(s) que rompen el contrato de handoff: " + " | ".join(fallos))
    return Veredicto("RESULT-CONTRACT", ok, esperado, obtenido, detalle)


@registrar("result_contract")
def run(ctx):
    """Detector-wrapper del result_contract. Devuelve list[Veredicto]. READ-ONLY.

    Emite RESULT-CONTRACT SOLO cuando hay un envelope que rompe el contrato, para no
    contaminar la cobertura-motor sobre las fixtures limpias (donde el conjunto de ids
    ejecutados debe seguir siendo {INV-R1, LINT-WIKILINK, INV-PANEL})."""
    v = _result_contract(ctx)
    if v.ok:
        return []
    return [v]
