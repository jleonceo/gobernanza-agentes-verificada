#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ci_gate.py — CI del gate (cadencia). Orquesta las corridas EXISTENTES del kit.
=============================================================================

Problema (SPEC_CI_Gate.md): hoy el gate se corre a mano; sin cadencia, la deriva
SANO->VIGILAR pasa desapercibida. Este runner encadena, en un solo comando apto
para hook de git / log de CI, los DOS métodos del gate + su convergencia, más el
guardarraíl anti-drift doc<->kit:

    1. gate/run_gate.py --fixtures ambas       (MÉTODO 1 + convergencia directa M1/M2)
    2. gate/verificador_minimo.py              (MÉTODO 2, verificador independiente)
    3. gate/test_install_sincronizado.py       (anti-drift: install.md y README.md
                                                sincronizados con el kit real)

Agrega los resultados y devuelve **exit 0 SOLO si TODO es verde**; exit != 0 en
cuanto un check degrade. Una línea por check + un veredicto final legible.

Alcance (SPEC §Fuera de alcance): NO modifica el gate ni los detectores ni la
config; SOLO los invoca. Determinista, sin red, stdlib puro. Cada check corre
como subproceso independiente (aislamiento: un `sys.exit` de un método no aborta
el otro; ambos se ejecutan y se reporta el conjunto).

Uso:
    python ci_gate.py            # corre todos los checks; exit 0 si TODO verde
    python ci_gate.py --quiet    # solo el veredicto final (para hooks silenciosos)

Contrato de salida:
    - exit 0  -> TODOS los checks verdes (SANO). Apto para dejar pasar el commit.
    - exit 1  -> algún check degradó. stderr lleva el detalle del que falló.
"""

import argparse
import subprocess
import sys
from pathlib import Path

# Raíz del kit = carpeta de este fichero. Los scripts que orquesta viven en gate/.
# Ruta INYECTADA por __file__ (no expanduser/HOME), coherente con el resto del kit.
RAIZ_KIT = Path(__file__).resolve().parent
GATE = RAIZ_KIT / "gate"

# --- CHECKS que se orquestan --------------------------------------------------
# Cada check: (etiqueta legible, argv del subproceso). El argv se construye con
# sys.executable para usar EXACTAMENTE el intérprete con el que se lanzó ci_gate
# (mismo entorno/venv), y rutas absolutas para no depender del cwd.
CHECKS = [
    ("gate (metodo 1 + convergencia M1/M2)",
     [sys.executable, str(GATE / "run_gate.py"), "--fixtures", "ambas"]),
    ("verificador_minimo (metodo 2)",
     [sys.executable, str(GATE / "verificador_minimo.py")]),
    ("install_sincronizado (anti-drift doc<->kit: install.md + README.md)",
     [sys.executable, str(GATE / "test_install_sincronizado.py")]),
]


def _correr_check(etiqueta, argv):
    """Corre UN check como subproceso independiente y devuelve (ok, etiqueta, detalle).

    ok = (returncode == 0). El subproceso se aísla (su exit no tumba a ci_gate), se
    ejecuta desde la raíz del kit (cwd) para que el bootstrap de sys.path de los
    scripts resuelva `motor`/`detectores`, y se captura salida para el detalle.

    Se COMPRUEBA el código de retorno (no se asume verde): un subproceso que termina
    con returncode != 0 es rojo aunque imprima algo. Barrido de corner case: un fallo
    del propio arranque del script (ImportError, traza) también da returncode != 0 y
    se reporta como rojo — no como "todo correcto".
    """
    try:
        p = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            cwd=str(RAIZ_KIT),
        )
    except OSError as e:
        # El intérprete/script no se pudo lanzar: es rojo, no verde silencioso.
        return (False, etiqueta, "no se pudo lanzar el check: %s" % e)

    ok = (p.returncode == 0)
    if ok:
        # Última línea no vacía del stdout como resumen (el sello VERDE del script).
        lineas = [l for l in p.stdout.splitlines() if l.strip()]
        detalle = lineas[-1] if lineas else "(sin salida)"
    else:
        # Rojo: prioriza stderr (los scripts escriben el motivo ahí con "ROJO: ...").
        err = (p.stderr or p.stdout or "").strip()
        detalle = "rc=%d :: %s" % (p.returncode, err.replace("\n", " | ")[:400])
    return (ok, etiqueta, detalle)


def main():
    ap = argparse.ArgumentParser(
        description="CI del gate: encadena los 2 métodos del kit + el guardarraíl anti-drift.")
    ap.add_argument("--quiet", action="store_true",
                    help="solo imprime el veredicto final (para hooks silenciosos).")
    args = ap.parse_args()

    resultados = [_correr_check(etiqueta, argv) for etiqueta, argv in CHECKS]

    # Una línea por check (SPEC §2): [OK]/[ROJO] etiqueta -> detalle.
    if not args.quiet:
        for ok, etiqueta, detalle in resultados:
            marca = "OK  " if ok else "ROJO"
            print("[%s] %s -> %s" % (marca, etiqueta, detalle))

    total = len(resultados)
    verdes = sum(1 for ok, _, _ in resultados if ok)
    todo_verde = (verdes == total)

    # Veredicto final legible (SPEC §2). Los rojos, además, a stderr para el log de CI.
    if todo_verde:
        print("CI-GATE VERDE: %d/%d checks SANO." % (verdes, total))
        return 0

    fallidos = [etiqueta for ok, etiqueta, _ in resultados if not ok]
    print("CI-GATE ROJO: %d/%d checks verdes; degradaron: %s"
          % (verdes, total, ", ".join(fallidos)))
    sys.stderr.write("CI-GATE ROJO: degradaron -> %s\n" % ", ".join(fallidos))
    for ok, etiqueta, detalle in resultados:
        if not ok:
            sys.stderr.write("  - %s: %s\n" % (etiqueta, detalle))
    return 1


if __name__ == "__main__":
    sys.exit(main())
