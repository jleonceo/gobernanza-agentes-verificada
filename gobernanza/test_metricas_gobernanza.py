#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_metricas_gobernanza.py -- suite de las metricas de gobernanza DIU/CDL.

Miden la GOBERNANZA MISMA: cuando el sistema DEFIERE una decision al humano (VIA C),
¿esa deferencia INFORMA (dice que falta y por que) o es CORTINA (deferir por deferir)?
Prior art: mech-gov-framework de SantanderAI (metrics/governance/{diu,cdl}.py),
fuente primaria leida el 08/07 (Radar_Santander_Seguimiento_08072026.md §2.4). Fórmulas
re-implementadas desde la descripcion, NO copiadas; adaptadas a nuestra VIA C.

Convencion del kit (sin pytest): funciones test_*; main() corre todas e informa.
    python gobernanza/test_metricas_gobernanza.py
"""
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from metricas_gobernanza import compute_diu, compute_cdl, evaluar, THETA_DEFECTO

_fallos = []


def chk(cond, msg):
    print(f"  [{'OK' if cond else 'FALLO'}] {msg}")
    if not cond:
        _fallos.append(msg)


def _d(idd, spec, causal, bshift):
    return {"id": idd, "spec": spec, "causal": causal, "bshift": bshift}


# --- DIU: media de la media geometrica (spec*causal*bshift)^(1/3) --------------
def test_diu_perfecto_es_1():
    ds = [_d("a", 1.0, 1.0, 1.0), _d("b", 1.0, 1.0, 1.0)]
    chk(abs(compute_diu(ds) - 1.0) < 1e-9, "DIU de deferencias perfectas = 1.0")


def test_diu_media_geometrica_una_dimension_cero_hunde():
    """Media GEOMETRICA: si una dimension es 0, ese termino es 0 (no se compensa con
    las otras dos altas). Es la propiedad clave: exige las TRES dimensiones no-nulas."""
    ds = [_d("a", 0.0, 1.0, 1.0)]
    chk(compute_diu(ds) == 0.0, "una dimension a 0 -> media geometrica 0 (no compensa)")


def test_diu_valor_conocido():
    """(0.5*0.5*0.5)^(1/3) = 0.5 exacto; con otra deferencia a 1.0 -> media 0.75."""
    ds = [_d("a", 0.5, 0.5, 0.5), _d("b", 1.0, 1.0, 1.0)]
    chk(abs(compute_diu(ds) - 0.75) < 1e-9, "DIU media de 0.5 y 1.0 = 0.75")


def test_diu_sin_deferencias_es_none():
    """Sin deferencias no hay valor: None (no se finge 0 ni 1)."""
    chk(compute_diu([]) is None, "DIU de lista vacia = None (indefinido, no 0/1)")


# --- CDL: fraccion de deferencias CORTINA (spec<theta OR causal<theta) ---------
def test_cdl_ninguna_cortina():
    ds = [_d("a", 0.9, 0.9, 0.1), _d("b", 0.5, 0.5, 0.0)]
    chk(compute_cdl(ds) == 0.0, "CDL 0 si spec y causal >= theta (bshift NO cuenta para CDL)")


def test_cdl_cuenta_spec_o_causal_baja():
    ds = [_d("a", 0.1, 0.9, 0.9),   # spec baja -> cortina
          _d("b", 0.9, 0.1, 0.9),   # causal baja -> cortina
          _d("c", 0.9, 0.9, 0.9)]   # ok
    chk(abs(compute_cdl(ds) - 2/3) < 1e-9, "CDL = 2/3 (spec baja O causal baja)")


def test_cdl_theta_es_estricto():
    """El umbral es ESTRICTO (< theta): spec == theta NO es cortina."""
    ds = [_d("a", THETA_DEFECTO, THETA_DEFECTO, 0.0)]
    chk(compute_cdl(ds) == 0.0, "spec == theta exacto NO cuenta como cortina (< estricto)")


def test_cdl_sin_deferencias_es_none():
    chk(compute_cdl([]) is None, "CDL de lista vacia = None")


# --- Validacion: fail-fast, sin clamp silencioso ------------------------------
def test_rechaza_fuera_de_rango():
    malos = 0
    for mala in (_d("x", 1.5, 0.5, 0.5), _d("x", -0.1, 0.5, 0.5), _d("x", 0.5, 0.5, "a")):
        try:
            compute_diu([mala])
        except (ValueError, TypeError):
            malos += 1
    chk(malos == 3, "puntuacion fuera de [0,1] o no numerica -> error (no clamp silencioso)")


def test_rechaza_dimension_ausente():
    try:
        compute_diu([{"id": "x", "spec": 0.5, "causal": 0.5}])  # falta bshift
        chk(False, "dimension ausente deberia fallar")
    except (KeyError, ValueError):
        chk(True, "dimension ausente -> error (no se inventa)")


# --- evaluar(): informe completo con interpretacion ---------------------------
def test_evaluar_informe():
    ds = [_d("a", 0.9, 0.9, 0.8), _d("b", 0.1, 0.9, 0.9)]
    rep = evaluar(ds)
    chk(rep["n"] == 2, "evaluar cuenta las deferencias")
    chk(0.0 <= rep["diu"] <= 1.0, "diu en rango")
    chk(abs(rep["cdl"] - 0.5) < 1e-9, "cdl = 0.5 (una de dos es cortina)")
    chk(isinstance(rep["interpretacion"], str) and rep["interpretacion"], "hay interpretacion textual")
    chk(rep["theta"] == THETA_DEFECTO, "el theta usado se reporta (explicabilidad)")


def test_evaluar_vacio_no_revienta():
    rep = evaluar([])
    chk(rep["n"] == 0 and rep["diu"] is None and rep["cdl"] is None,
        "evaluar sin deferencias -> n=0, diu/cdl None (no traceback, no cifra falsa)")


def main():
    for fn in sorted(k for k in globals() if k.startswith("test_")):
        print(f"\n{fn}:")
        globals()[fn]()
    print("\n" + "=" * 60)
    if _fallos:
        print(f"[ROJO] {len(_fallos)} fallo(s): " + "; ".join(_fallos))
        sys.exit(1)
    print("[VERDE] metricas de gobernanza DIU/CDL: formulas y bordes OK.")


if __name__ == "__main__":
    main()
