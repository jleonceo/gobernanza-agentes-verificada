#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_install_sincronizado.py — guardarrail ANTI-DRIFT doc<->kit (auditoria 07/07/2026).

install.md es EL documento del Criterio B (un tercero instala el kit solo con el).
La auditoria del 07/07 (hallazgo #8, verificado) encontro que describia un kit que ya
no existe: (1) la estructura de §1.2 omitia `routing_paths.yaml`, que config_loader
exige como REQUERIDO (seguir el manual estampa al tercero contra el fail-fast);
(2) decia "tres detectores" cuando el gate registra CINCO; (3) cero menciones al
audit trail (grep -ic audit = 0), pese a ser feature del kit.

Este test verifica que install.md esta SINCRONIZADO con el kit real, derivando la
verdad DEL CODIGO (no de listas hardcodeadas aqui):
  (a) todo fichero de config REQUERIDO por `motor.config_loader.FICHEROS_REQUERIDOS`
      aparece en el arbol de §1.2 (el bloque ``` con la estructura del kit);
  (b) todo fichero OPCIONAL (`FICHEROS_OPCIONALES`) esta documentado en el texto;
  (c) el numero de detectores que declara el doc == len(REGISTRO) tras registrar
      los detectores EXACTAMENTE como lo hace `gate/run_gate.py` (importandolo);
      y NO queda ninguna cifra vieja ("tres detectores") en el texto;
  (d) cada detector registrado se nombra en install.md;
  (e) el audit trail se menciona (la feature no puede ser invisible al tercero);
  (f) README.md declara el numero REAL de detectores (mismo criterio que (c):
      derivado de len(REGISTRO), no hardcodeado aqui) — el drift "motor + 3
      detectores" del README fue hallazgo #2.4.1 de la auditoria del 07/07.

Anti-drift: si manana se registra un sexto detector o un nuevo yaml requerido y nadie
toca install.md o README.md, este test se pone ROJO solo. NO toca codigo del kit: solo lee.
Se ejecuta directo con `python gate/test_install_sincronizado.py`.
"""

import re
import sys
from pathlib import Path

_RAIZ_KIT = Path(__file__).resolve().parent.parent
if str(_RAIZ_KIT) not in sys.path:
    sys.path.insert(0, str(_RAIZ_KIT))
_GATE = Path(__file__).resolve().parent
if str(_GATE) not in sys.path:
    sys.path.insert(0, str(_GATE))

# La verdad sale del CODIGO, no de este test:
from motor.config_loader import FICHEROS_REQUERIDOS, FICHEROS_OPCIONALES
import run_gate  # noqa: F401  -> registra los detectores EXACTAMENTE como el gate real
from motor.runner import REGISTRO

INSTALL = _RAIZ_KIT / "install.md"
README = _RAIZ_KIT / "README.md"

# Cardinales en palabra que install.md podria usar junto a "detectores".
_PALABRAS = {2: "dos", 3: "tres", 4: "cuatro", 5: "cinco",
             6: "seis", 7: "siete", 8: "ocho", 9: "nueve", 10: "diez"}
_A_NUMERO = {v: k for k, v in _PALABRAS.items()}


def _leer_install():
    if not INSTALL.is_file():
        raise AssertionError("no existe %s" % INSTALL)
    return INSTALL.read_text(encoding="utf-8")


def _leer_readme():
    if not README.is_file():
        raise AssertionError("no existe %s" % README)
    return README.read_text(encoding="utf-8")


def _verificar_numero_detectores(texto, doc, letra):
    """Nucleo compartido de (c) y (f): el doc declara el numero REAL de detectores.

    La verdad es len(REGISTRO) (poblado importando run_gate, igual que el gate real).
    Exige: (1) al menos una declaracion 'N detectores' (cifra o cardinal en palabra),
    (2) NINGUNA declaracion con un numero distinto (una cifra vieja = drift)."""
    n = len(REGISTRO)
    if n not in _PALABRAS:
        raise AssertionError("(%s) len(REGISTRO)=%d fuera del mapa de cardinales del test "
                             "(ampliar _PALABRAS)." % (letra, n))
    correcto = _PALABRAS[n]

    patron = r"\b(%s|\d+)\s+detectores" % "|".join(_A_NUMERO)
    declarados = [m.lower() for m in re.findall(patron, texto, re.IGNORECASE)]
    assert declarados, (
        "(%s) %s no declara en ningun sitio cuantos detectores corre el kit "
        "(esperado: '%s detectores' o '%d detectores')." % (letra, doc, correcto, n))

    mal = [d for d in declarados
           if (_A_NUMERO.get(d) or int(d)) != n]
    assert not mal, (
        "(%s) %s declara un numero de detectores DISTINTO de los %d que "
        "registra run_gate.py: %s detectores" % (letra, doc, n, ", ".join(sorted(set(mal)))))
    assert any((_A_NUMERO.get(d) or int(d)) == n for d in declarados)
    return n, correcto, declarados


def _bloque_estructura(texto):
    """El bloque ``` de seccion 1.2 con el arbol del kit ('agent-governance-checks/')."""
    for bloque in re.findall(r"```[^\n]*\n(.*?)```", texto, re.DOTALL):
        if "agent-governance-checks/" in bloque:
            return bloque
    raise AssertionError(
        "install.md no tiene el bloque de estructura del kit (```...agent-governance-checks/...```)")


def test_a_config_requerida_en_estructura():
    """(a) Cada yaml de FICHEROS_REQUERIDOS aparece en el arbol de seccion 1.2."""
    texto = _leer_install()
    bloque = _bloque_estructura(texto)
    ausentes = [s + ".yaml" for s in FICHEROS_REQUERIDOS if (s + ".yaml") not in bloque]
    assert not ausentes, (
        "(a) la estructura de seccion 1.2 OMITE config REQUERIDA por config_loader "
        "(un tercero que construya su config desde el manual se estampa contra el "
        "fail-fast): %s" % ", ".join(ausentes))
    print("  [OK] (a) los %d yaml REQUERIDOS por config_loader estan en el arbol de seccion 1.2."
          % len(FICHEROS_REQUERIDOS))


def test_b_config_opcional_documentada():
    """(b) Cada yaml de FICHEROS_OPCIONALES esta documentado en algun punto del doc."""
    texto = _leer_install()
    ausentes = [s + ".yaml" for s in FICHEROS_OPCIONALES if (s + ".yaml") not in texto]
    assert not ausentes, (
        "(b) install.md no documenta config OPCIONAL del kit: %s" % ", ".join(ausentes))
    print("  [OK] (b) los %d yaml OPCIONALES estan documentados." % len(FICHEROS_OPCIONALES))


def test_c_numero_de_detectores():
    """(c) install.md declara el numero REAL de detectores registrados, sin cifras viejas."""
    n, correcto, _ = _verificar_numero_detectores(_leer_install(), "install.md", "c")
    print("  [OK] (c) install.md declara '%s detectores' y coincide con len(REGISTRO)=%d."
          % (correcto, n))


def test_d_nombres_de_detectores():
    """(d) Cada detector registrado se nombra en install.md."""
    texto = _leer_install()
    ausentes = sorted(nombre for nombre in REGISTRO.nombres() if nombre not in texto)
    assert not ausentes, (
        "(d) detectores registrados por el gate que install.md NO nombra: %s"
        % ", ".join(ausentes))
    print("  [OK] (d) los %d detectores registrados (%s) se nombran en el doc."
          % (len(REGISTRO), ", ".join(sorted(REGISTRO.nombres()))))


def test_e_audit_trail_mencionado():
    """(e) La feature audit trail no puede ser invisible para el tercero."""
    texto = _leer_install()
    assert re.search(r"audit[\s_-]*trail", texto, re.IGNORECASE), (
        "(e) install.md no menciona el audit trail en absoluto (grep -i audit = 0): "
        "la feature es invisible para quien instala con el manual.")
    print("  [OK] (e) el audit trail esta mencionado en install.md.")


def test_f_readme_numero_de_detectores():
    """(f) README.md declara el numero REAL de detectores registrados, sin cifras viejas.

    Mismo criterio que (c) pero sobre README.md: es la portada del kit y el hallazgo
    #2.4.1 de la auditoria del 07/07 lo encontro diciendo "motor + 3 detectores"
    cuando el gate registra cinco. Si README desincroniza, este test se pone ROJO."""
    n, correcto, _ = _verificar_numero_detectores(_leer_readme(), "README.md", "f")
    print("  [OK] (f) README.md declara el numero de detectores y coincide con "
          "len(REGISTRO)=%d ('%s')." % (n, correcto))


def main():
    fallos = 0
    for test in (test_a_config_requerida_en_estructura,
                 test_b_config_opcional_documentada,
                 test_c_numero_de_detectores,
                 test_d_nombres_de_detectores,
                 test_e_audit_trail_mencionado,
                 test_f_readme_numero_de_detectores):
        try:
            test()
        except AssertionError as e:
            fallos += 1
            print("  [FAIL] %s: %s" % (test.__name__, e))
    print("\n%s" % ("=" * 50))
    if fallos == 0:
        print("INSTALL SINCRONIZADO VERDE: 0 fallos.")
        return 0
    print("INSTALL SINCRONIZADO ROJO: %d fallo/s (install.md o README.md "
          "desincronizados del kit)." % fallos)
    return 1


if __name__ == "__main__":
    sys.exit(main())
