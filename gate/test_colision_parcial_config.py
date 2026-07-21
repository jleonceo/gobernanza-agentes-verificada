#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_colision_parcial_config.py — RED->GREEN de los DOS defectos de la auditoria
sobre el detector de routing y su config (bugfix 06/07/2026).

DEFECTO 1 (importante): INV-R4 (colision de routing) se DESACTIVA EN SILENCIO si la
clave `routing.jaccard_warn` falta en umbrales.yaml, porque `gate_routing._umbral_jaccard`
cae a un default 1.0 (solo colisionan descripciones IDENTICAS) y `config_loader` NO valida
esa clave. Este test lo demuestra con una fixture de colision PARCIAL (Jaccard ~0.33, ENTRE
0.22 y 1.0):
  (a) con umbrales.yaml correcto (jaccard_warn=0.22) el gate CAZA la colision parcial (rojo);
  (b) ANTES DEL FIX, con jaccard_warn AUSENTE, el gate la dejaba pasar en SILENCIO (bug).
Tras el fix, (b) ya no puede pasar en silencio: `config_loader` es FAIL-FAST sobre esa clave,
asi que una config sin ella ABORTA con ConfigError (no hay umbral castrado posible).

Este fichero NO edita ningun detector: prueba comportamiento observable (Iron Law TDD).
Se ejecuta directo con `python gate/test_colision_parcial_config.py`.
"""

import copy
import sys
from pathlib import Path

_RAIZ_KIT = Path(__file__).resolve().parent.parent
if str(_RAIZ_KIT) not in sys.path:
    sys.path.insert(0, str(_RAIZ_KIT))

from motor.config_loader import cargar_config, ConfigError
from motor.runner import Runner, REGISTRO
import detectores.gate_routing  # noqa: F401  registra "gate_routing"

RAIZ = Path(__file__).resolve().parent
FIXTURES = RAIZ / "fixtures"
CONFIG = RAIZ.parent / "config"
FIXTURE_PARCIAL = FIXTURES / "rotas" / "06_colision_routing_parcial"


def _correr(config, root):
    """Corre el registro completo sobre `root` con `config` y devuelve el resultado."""
    runner = Runner(REGISTRO)
    return runner.correr(root=root, config=config)


def _inv_r4_en_fallo(resultado):
    return any((not v.ok) and v.id == "INV-R4" for v in resultado.veredictos)


def test_a_umbral_operativo_caza_colision_parcial():
    """(a) Con jaccard_warn=0.22 (config real), INV-R4 debe FALLAR sobre la fixture parcial."""
    config = cargar_config(CONFIG)
    # sanity: la config real trae el umbral operativo
    assert config["umbrales"]["routing"]["jaccard_warn"] == 0.22, "config base cambio"
    resultado = _correr(config, FIXTURE_PARCIAL)
    assert _inv_r4_en_fallo(resultado), (
        "(a) el umbral operativo 0.22 NO cazo la colision parcial: %s"
        % resultado.resumen())
    print("  [OK] (a) umbral operativo 0.22 CAZA la colision parcial (INV-R4 en fallo).")


def test_b_config_sin_jaccard_warn_no_desactiva_en_silencio():
    """(b) Con jaccard_warn AUSENTE, el gate NO puede desactivar INV-R4 en silencio.

    ANTES DEL FIX: cargar_config aceptaba la config incompleta y gate_routing caia a
    default 1.0 -> INV-R4 pasaba en SILENCIO (la fixture parcial daba VERDE). Ese era el bug.
    TRAS EL FIX: config_loader valida routing.jaccard_warn -> ConfigError (FAIL-FAST). El
    test exige exactamente eso: o bien la carga aborta (fix aplicado), o —si aun cargara—
    la fixture parcial NO puede quedar en verde en silencio."""
    config = cargar_config(CONFIG)
    # Simula un umbrales.yaml SIN la clave jaccard_warn (config incompleta de un tercero).
    config_sin = copy.deepcopy(config)
    config_sin["umbrales"]["routing"].pop("jaccard_warn", None)

    # El comportamiento CORRECTO tras el fix: config_loader rechaza esa forma de config.
    # Como aqui ya tenemos el dict, re-validamos con el guardarrail del loader.
    from motor.config_loader import validar_umbrales_routing
    try:
        validar_umbrales_routing(config_sin)
    except ConfigError:
        print("  [OK] (b) config sin jaccard_warn -> ConfigError (FAIL-FAST): "
              "no hay umbral castrado posible.")
        return

    # Si NO aborto (fix ausente o relajado), entonces AL MENOS la fixture parcial no puede
    # quedar en verde en silencio -> esto es lo que fallaba antes del fix.
    resultado = _correr(config_sin, FIXTURE_PARCIAL)
    assert _inv_r4_en_fallo(resultado), (
        "(b) BUG: con jaccard_warn ausente el gate dejo pasar la colision parcial EN "
        "SILENCIO (umbral castrado a 1.0). resultado=%s" % resultado.resumen())
    print("  [OK] (b) con jaccard_warn ausente la colision parcial NO pasa en silencio.")


def test_c_jaccard_warn_bool_es_rechazado():
    """(c) Valor-trampa: `jaccard_warn: true` (bool YAML) debe dar ConfigError.

    Barrido adversarial (06/07): en Python `bool` es subclase de `int`, asi que float(True)=1.0
    pasaria un rango (0,1] ingenuo y dejaria INV-R4 MUDO para colisiones parciales CON la clave
    PRESENTE. `validar_umbrales_routing` intercepta el bool ANTES del float(). Ademas confirma que
    `false` (float(False)=0.0, fuera de rango) SIGUE rechazandose por la via de rango."""
    from motor.config_loader import validar_umbrales_routing
    base = cargar_config(CONFIG)

    for trampa in (True, False):
        cfg = copy.deepcopy(base)
        cfg["umbrales"]["routing"]["jaccard_warn"] = trampa
        try:
            validar_umbrales_routing(cfg)
        except ConfigError:
            print("  [OK] (c) jaccard_warn=%r -> ConfigError (rechazado)." % trampa)
        else:
            raise AssertionError(
                "(c) jaccard_warn=%r NO fue rechazado: el bool se cuela como umbral y castra INV-R4"
                % trampa)

    # Sanity: un numero real valido SIGUE pasando (no hemos roto el camino feliz).
    cfg_ok = copy.deepcopy(base)
    cfg_ok["umbrales"]["routing"]["jaccard_warn"] = 0.22
    validar_umbrales_routing(cfg_ok)  # no debe lanzar
    print("  [OK] (c) jaccard_warn=0.22 (numero real) sigue validando.")


def main():
    fallos = 0
    for test in (test_a_umbral_operativo_caza_colision_parcial,
                 test_b_config_sin_jaccard_warn_no_desactiva_en_silencio,
                 test_c_jaccard_warn_bool_es_rechazado):
        try:
            test()
        except AssertionError as e:
            fallos += 1
            print("  [FAIL] %s: %s" % (test.__name__, e))
    print("\n%s" % ("=" * 50))
    if fallos == 0:
        print("TEST COLISION PARCIAL VERDE: 0 fallos.")
        return 0
    print("TEST COLISION PARCIAL ROJO: %d fallo/s." % fallos)
    return 1


if __name__ == "__main__":
    sys.exit(main())
