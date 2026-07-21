#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
metricas_gobernanza.py -- DIU y CDL: medir la GOBERNANZA MISMA (no el corpus).

Un sistema humano-IA (VIA C) DEFIERE decisiones al humano. Pero deferir no es gratis
ni siempre util: una deferencia puede INFORMAR (dice QUE falta y POR QUE, y cambiar el
curso) o ser CORTINA (deferir por deferir, sin contenido). Estas dos metricas lo miden:

  DIU  (Deferral Information Utilisation) -- ¿las deferencias APORTAN informacion?
       media de la media GEOMETRICA por deferencia: (spec * causal * bshift)^(1/3).
       Geometrica a proposito: exige las TRES dimensiones no-nulas (una floja hunde el
       termino, no se compensa). ~1 = deferencias ricas; ~0 = flojas en alguna dimension.

  CDL  (Cosmetic Deadlock rate) -- ¿que fraccion son CORTINA?
       |{d : spec(d) < theta  OR  causal(d) < theta}| / |deferencias|,  theta=0.3.
       Bajo = bueno; alto = muchas deferencias que ni especifican que falta (spec) ni
       explican por que se difiere (causal). bshift NO entra en CDL (una deferencia
       puede ser especifica y causal aunque no cambie el resultado).

Las TRES dimensiones de cada deferencia, en [0,1]:
  - spec   (specificity): ¿dice CONCRETAMENTE que informacion/decision falta?
  - causal (causality)  : ¿explica POR QUE se difiere (que la hace irreducible al sistema)?
  - bshift (bias-shift) : ¿la deferencia CAMBIA el curso frente a decidir por defecto?

Instrumento contra el SOBRE-FILTRADO (memoria guardar-contra-sobrefiltrado): si el
sistema difiere mucho a Juan pero con DIU bajo / CDL alto, las deferencias son ruido,
no gobernanza -- y hay que subir el liston de "cuando merece la pena parar y preguntar".

Prior art: mech-gov-framework de SantanderAI (`metrics/governance/{diu,cdl}.py`), leido
en fuente primaria el 08/07 (Radar_Santander_Seguimiento_08072026.md §2.4). Las formulas
se RE-IMPLEMENTAN aqui desde su descripcion (media geometrica; theta=0.3 estandar), no se
copia codigo; theta es config-driven. STDLIB PURO, READ-ONLY, determinista. Fail-fast: una
puntuacion fuera de [0,1] o una dimension ausente es un error de dato, NO se clampa en
silencio (misma doctrina que el resto del kit: sin defaults silenciosos).
"""
from __future__ import annotations

from typing import Dict, List, Optional

THETA_DEFECTO = 0.3               # umbral estandar de "cortina" (mech-gov)
_DIMENSIONES = ("spec", "causal", "bshift")


def _puntuacion(deferencia: Dict, dim: str) -> float:
    """Extrae y VALIDA una dimension de una deferencia: presente, numerica y en [0,1].
    Fail-fast (no clamp silencioso): dimension ausente -> KeyError; no numerica ->
    TypeError; fuera de rango -> ValueError. Un dato malo no debe colar una metrica falsa."""
    if dim not in deferencia:
        raise KeyError("deferencia %r sin la dimension obligatoria %r"
                       % (deferencia.get("id", "?"), dim))
    v = deferencia[dim]
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise TypeError("dimension %r de %r no es numerica: %r"
                        % (dim, deferencia.get("id", "?"), v))
    v = float(v)
    if not (0.0 <= v <= 1.0):
        raise ValueError("dimension %r de %r fuera de [0,1]: %r"
                         % (dim, deferencia.get("id", "?"), v))
    return v


def _media_geometrica(deferencia: Dict) -> float:
    """(spec * causal * bshift)^(1/3) de UNA deferencia (validada)."""
    prod = 1.0
    for dim in _DIMENSIONES:
        prod *= _puntuacion(deferencia, dim)
    return prod ** (1.0 / 3.0)


def compute_diu(deferencias: List[Dict]) -> Optional[float]:
    """DIU: media de la media geometrica por deferencia. None si no hay deferencias
    (indefinido: no se finge 0 ni 1)."""
    if not deferencias:
        return None
    return sum(_media_geometrica(d) for d in deferencias) / len(deferencias)


def compute_cdl(deferencias: List[Dict], theta: float = THETA_DEFECTO) -> Optional[float]:
    """CDL: fraccion de deferencias CORTINA (spec < theta OR causal < theta). None si
    no hay deferencias. Umbral ESTRICTO (<): una puntuacion == theta no es cortina."""
    if not deferencias:
        return None
    cortina = 0
    for d in deferencias:
        spec = _puntuacion(d, "spec")
        causal = _puntuacion(d, "causal")
        _puntuacion(d, "bshift")   # valida las tres aunque bshift no entre en CDL
        if spec < theta or causal < theta:
            cortina += 1
    return cortina / len(deferencias)


def _interpretar(diu: Optional[float], cdl: Optional[float], theta: float) -> str:
    """Lectura textual honesta (umbrales explicitos, no magia). Sin deferencias -> se dice."""
    if diu is None or cdl is None:
        return "sin deferencias en la ventana: nada que medir (ni bueno ni malo)."
    partes = []
    if diu >= 0.7:
        partes.append("las deferencias INFORMAN (DIU alto)")
    elif diu >= 0.4:
        partes.append("deferencias de informacion MEDIA (DIU intermedio)")
    else:
        partes.append("deferencias POBRES en informacion (DIU bajo: alguna dimension floja)")
    if cdl <= 0.1:
        partes.append("casi ninguna es cortina (CDL bajo)")
    elif cdl <= 0.3:
        partes.append("hay algo de cortina (CDL medio: revisar)")
    else:
        partes.append("MUCHAS son cortina (CDL alto: se difiere por deferir -> subir el liston)")
    return "; ".join(partes) + f" [theta={theta}]."


def evaluar(deferencias: List[Dict], theta: float = THETA_DEFECTO) -> Dict:
    """Informe de gobernanza sobre una lista de deferencias. READ-ONLY, determinista.
    Devuelve {n, diu, cdl, theta, interpretacion}. Vacio -> n=0, diu/cdl None (no revienta)."""
    diu = compute_diu(deferencias)
    cdl = compute_cdl(deferencias, theta)
    return {
        "n": len(deferencias),
        "diu": diu,
        "cdl": cdl,
        "theta": theta,
        "interpretacion": _interpretar(diu, cdl, theta),
    }


def _main(argv=None):
    """CLI: `python metricas_gobernanza.py <deferencias.json> [theta]`. El JSON es una
    lista de {id, spec, causal, bshift} (o {deferencias:[...]}). Exit 0 siempre que
    calcule; 2 si el fichero no existe / no parsea."""
    import argparse
    import json
    ap = argparse.ArgumentParser(description="Metricas de gobernanza DIU/CDL sobre un log de deferencias.")
    ap.add_argument("deferencias", help="JSON: lista de {id,spec,causal,bshift} o {deferencias:[...]}")
    ap.add_argument("--theta", type=float, default=THETA_DEFECTO)
    args = ap.parse_args(argv)
    import os as _os
    if not _os.path.exists(args.deferencias):
        print("ERROR: no existe %s" % args.deferencias)
        return 2
    with open(args.deferencias, encoding="utf-8") as fh:
        data = json.load(fh)
    ds = data.get("deferencias", data) if isinstance(data, dict) else data
    rep = evaluar(ds, args.theta)
    diu = "None" if rep["diu"] is None else f"{rep['diu']:.3f}"
    cdl = "None" if rep["cdl"] is None else f"{rep['cdl']:.3f}"
    print("== GOBERNANZA (DIU/CDL) ==")
    print(f"  deferencias : {rep['n']}")
    print(f"  DIU         : {diu}   (1 = informan; 0 = pobres)")
    print(f"  CDL         : {cdl}   (0 = ninguna cortina; alto = cortina)")
    print(f"  lectura     : {rep['interpretacion']}")
    return 0


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(_main())
