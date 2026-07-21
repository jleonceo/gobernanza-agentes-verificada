#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_ci_gate.py — Suite de ci_gate.py (CI del gate).
====================================================

Verifica los criterios de SPEC_CI_Gate.md §4:
  1. Con el repo LIMPIO, `python ci_gate.py` sale 0 (todos los checks verdes).
  2. Forzando un fixture degradado de forma EFÍMERA, `ci_gate.py` sale != 0.
  3. La degradación se LIMPIA siempre (finally), deje el gate como estaba.

Además (SPEC §5, no-regresión indirecta): que el veredicto final legible aparezca
y que el degradado nombre el check que rompió.

Convención de test (estilo del kit, sin pytest): funciones test_*; main() las corre,
imprime PASA/FALLA por test, sale 0 si todas pasan, 1 si alguna falla. Determinista,
READ-ONLY salvo el fixture efímero que crea y borra en el mismo test.
    python test_ci_gate.py
"""

import subprocess
import sys
from pathlib import Path

RAIZ_KIT = Path(__file__).resolve().parent
CI_GATE = RAIZ_KIT / "ci_gate.py"
LIMPIAS = RAIZ_KIT / "gate" / "fixtures" / "limpias"
PYTHON = sys.executable

# Nombre único e inconfundible para el fixture efímero. Prefijo _ci_gate_test_ para
# que sea trivialmente identificable si por algún fallo catastrófico sobreviviera.
FIXTURE_EFIMERO = LIMPIAS / "_ci_gate_test_degradado_EFIMERO.md"

# Contenido con un wikilink roto: lint_corpus (LINT-WIKILINK) debe cazarlo, romper la
# fixture 'limpias' (que debe ser SANO) y por tanto tumbar run_gate --fixtures ambas.
CONTENIDO_ROTO = (
    "# Fixture EFIMERO — inyectado por test_ci_gate.py\n\n"
    "Defecto sembrado a proposito para probar que ci_gate.py detecta la degradacion.\n\n"
    "- [[skill-que-no-existe-en-el-corpus]] — puntero roto: sin fichero destino.\n"
)


def _correr_ci_gate():
    """Corre `python ci_gate.py` desde la raíz del kit y devuelve el CompletedProcess."""
    return subprocess.run(
        [PYTHON, str(CI_GATE)],
        capture_output=True, text=True, cwd=str(RAIZ_KIT),
    )


def test_repo_limpio_exit_0():
    """Con el repo tal cual (limpio), ci_gate.py sale 0 y sella VERDE."""
    p = _correr_ci_gate()
    assert p.returncode == 0, (
        "ci_gate.py sobre el repo limpio debe salir 0; salio %d.\nstdout=%s\nstderr=%s"
        % (p.returncode, p.stdout, p.stderr)
    )
    assert "CI-GATE VERDE" in p.stdout, (
        "falta el veredicto final 'CI-GATE VERDE' en stdout:\n%s" % p.stdout
    )


def test_degradacion_efimera_exit_no_cero():
    """Sembrando un defecto EFÍMERO en fixtures/limpias, ci_gate.py sale != 0 y lo reporta.
    El fixture se BORRA siempre (finally), deje el gate como estaba."""
    assert not FIXTURE_EFIMERO.exists(), (
        "el fixture efimero ya existe antes del test (residuo de una corrida previa): %s"
        % FIXTURE_EFIMERO
    )
    try:
        FIXTURE_EFIMERO.write_text(CONTENIDO_ROTO, encoding="utf-8")
        p = _correr_ci_gate()
        assert p.returncode != 0, (
            "con un fixture degradado, ci_gate.py debe salir != 0; salio 0.\nstdout=%s"
            % p.stdout
        )
        assert "CI-GATE ROJO" in p.stdout, (
            "falta el veredicto 'CI-GATE ROJO' en stdout con el gate degradado:\n%s" % p.stdout
        )
        # El check que rompe es el método 1 (run_gate corre las fixtures limpias):
        assert "metodo 1" in (p.stdout + p.stderr), (
            "el degradado debe nombrar el check del metodo 1 que rompio.\nstdout=%s\nstderr=%s"
            % (p.stdout, p.stderr)
        )
    finally:
        # Limpieza incondicional: el gate debe quedar EXACTAMENTE como estaba.
        if FIXTURE_EFIMERO.exists():
            FIXTURE_EFIMERO.unlink()
    assert not FIXTURE_EFIMERO.exists(), "el fixture efimero no se limpio: %s" % FIXTURE_EFIMERO


def test_limpieza_verificada_gate_vuelve_verde():
    """Tras la degradación+limpieza, el gate vuelve a VERDE (prueba que no dejó residuo)."""
    assert not FIXTURE_EFIMERO.exists(), (
        "residuo del fixture efimero: %s" % FIXTURE_EFIMERO
    )
    p = _correr_ci_gate()
    assert p.returncode == 0, (
        "tras limpiar la degradacion, ci_gate.py debe volver a salir 0; salio %d.\nstderr=%s"
        % (p.returncode, p.stderr)
    )


# ---------------------------------------------------------------------------
def main():
    tests = [
        test_repo_limpio_exit_0,
        test_degradacion_efimera_exit_no_cero,
        test_limpieza_verificada_gate_vuelve_verde,
    ]
    fallos = 0
    for t in tests:
        try:
            t()
            print("PASA  %s" % t.__name__)
        except AssertionError as e:
            fallos += 1
            print("FALLA %s\n      %s" % (t.__name__, e))
        except Exception as e:  # noqa: BLE001 — el arnés reporta cualquier error como FALLA
            fallos += 1
            print("FALLA %s (excepcion) \n      %r" % (t.__name__, e))
    total = len(tests)
    print("\n%d/%d tests PASAN" % (total - fallos, total))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
