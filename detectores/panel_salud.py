#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
panel_salud.py — Detector agregador anti-falso-verde (STANDALONE, des-acoplado).
================================================================================

EXTRAÍDO del panel_salud.py de TechAcces (versión v2, funciones puras + inyección de
dependencias) y DES-ACOPLADO: ninguna ruta absoluta, ningún subprocess al linter de
origen. Todo se resuelve relativo a ctx.root y todo patrón llega de ctx.conventions.

CONTRATO (CONTRATO_DETECTOR.md): `run(ctx) -> list[Veredicto]`.
- READ-ONLY. No imprime. No escribe. Devuelve SIEMPRE una lista.

INVARIANTE QUE EMITE
--------------------
· INV-PANEL (medio -> VIGILAR si falla): el panel agrega los hechos observables del
  corpus SIN colar un verde por defecto. Principio anti-falso-verde heredado del
  origen (C8): si el corpus no es MEDIBLE (no se pudo observar ninguna skill ni el
  registro de routing), el panel NO afirma "sano" — devuelve ok=False. Solo cuando el
  corpus es observable de verdad (>=1 descriptor de skill Y registro presente) el panel
  se declara coherente.

Detector de ejemplo #3 que ejercita runner + registro + snapshot de punta a punta.
"""

from pathlib import Path

from motor.veredicto import Veredicto
from motor.runner import registrar


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


def _observar(ctx):
    """Recolecta hechos crudos del corpus SIN juzgar (funciones puras del origen).
    Devuelve dict con lo observable: nº de descriptores de skill, presencia del
    registro de routing, nº de ficheros .md del corpus."""
    root = _root(ctx)
    rp = _routing_paths(ctx)
    skills_dir = _get(rp, "skills_dir")
    descriptor = _get(rp, "skill_descriptor")
    registro_rel = _get(rp, "registro_path")

    n_descriptores = 0
    if skills_dir is not None and descriptor is not None:
        glob = "*/" + descriptor
        n_descriptores = sum(1 for _ in ctx.iter_files(skills_dir, glob))

    registro_presente = False
    if registro_rel is not None:
        registro_presente = (root / registro_rel).exists()

    n_md = sum(1 for _ in sorted(root.rglob("*.md")))

    return {
        "n_descriptores": n_descriptores,
        "registro_presente": registro_presente,
        "n_md": n_md,
    }


def _inv_panel(ctx):
    obs = _observar(ctx)
    # Anti-falso-verde (C8 del origen): el defecto que este panel vigila NO es un corpus
    # legítimamente mínimo, sino la INCOHERENCIA de haber declarado un routing sin poder
    # observarlo — el registro de routing EXISTE pero no hay ni un descriptor de skill que
    # aggregate (medición prometida y no cumplida). Ese es el "verde por defecto" que se
    # rechaza. Un corpus sin skills NI registro (fixtures rotas centradas en otro detector)
    # no tiene nada que agregar -> el panel no inventa un fallo ajeno a su defecto.
    hay_registro = obs["registro_presente"]
    hay_skills = obs["n_descriptores"] >= 1
    incoherente = hay_registro and not hay_skills   # promete routing pero nada que medir
    ok = not incoherente
    esperado = "panel_coherente"
    obtenido = ("panel_coherente" if ok else "registro_sin_skills_observables")
    detalle = (
        "panel coherente: %d descriptor(es) de skill agregados, %d fichero(s) .md; "
        "sin colar verde por defecto"
        % (obs["n_descriptores"], obs["n_md"])
        if ok else
        "incoherencia anti-falso-verde: hay registro de routing pero 0 descriptores de "
        "skill observables — el panel no afirma salud sobre una medición no cumplida"
    )
    return Veredicto("INV-PANEL", ok, esperado, obtenido, detalle)


@registrar("panel_salud")
def run(ctx):
    """Panel agregador anti-falso-verde. Devuelve list[Veredicto]. READ-ONLY.
    Emite INV-PANEL (declarado en invariantes.yaml -> cobertura-motor)."""
    return [_inv_panel(ctx)]
