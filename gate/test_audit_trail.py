#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_audit_trail.py — SUITE DE ACEPTACIÓN (en ROJO) del audit trail encadenado por hash.
========================================================================================

Escrita por VERIFICADOR-PROGRAMADOR el 06/07/2026 en FASE TEST-PRIMERO. Es el GOLDEN del
software: deriva 1:1 del SPEC (§2.1, §4, §5.1, §7, §11). El CONSTRUCTOR NO la toca; solo
Juan la cambia.

HOY DEBE FALLAR EN ROJO porque `motor/audit_trail.py` y `detectores/audit_chain.py` NO
existen aún. Ese rojo por ImportError ES EL OBJETIVO de esta fase: define qué tiene que
existir y con qué comportamiento exacto. Cuando el constructor implemente ambos módulos
respetando el SPEC, esta suite debe pasar a VERDE sin tocarla.

Convención de test (estilo del kit, sin pytest): funciones test_*; cada una hace asserts;
main() las corre todas, imprime PASA/FALLA por test y sale 0 si todas pasan, 1 si alguna
falla. Determinista, READ-ONLY sobre las fixtures. Se corre con:
    python gate/test_audit_trail.py

Método de verificación del HASH (doctrina "dos métodos que coinciden"): las fixtures se
generaron con `gate/generar_fixtures_audit.py` — una implementación del algoritmo §2.1
INDEPENDIENTE de `motor/audit_trail.py`. Que `verificar_cadena` dé SANO sobre `integra`
confirma que las dos implementaciones convergen; que dé el rojo exacto sobre cada rota
confirma que localiza la manipulación. Aquí, además, re-hasheo con MI propio SHA-256
(no el del constructor) los asserts de huella, cerrando el segundo camino.
"""

import hashlib
import json
import sys
from pathlib import Path

# --- BOOTSTRAP de sys.path: la raíz del kit (padre de gate/) en el path, igual que
#     run_gate.py, para que `import motor.*` / `import detectores.*` resuelvan. READ-ONLY.
_RAIZ_KIT = Path(__file__).resolve().parent.parent
if str(_RAIZ_KIT) not in sys.path:
    sys.path.insert(0, str(_RAIZ_KIT))

RAIZ_GATE = Path(__file__).resolve().parent
FIXTURES = RAIZ_GATE / "fixtures"
DIR_INTEGRA = FIXTURES / "audit" / "integra"
DIR_ROTAS = FIXTURES / "audit_rotas"
DIR_LIMITE = FIXTURES / "audit_limite"
NOMBRE_TRAIL = "trail.jsonl"


# --- helpers de test (independientes del código del constructor) --------------------------
def _cargar_entradas_crudas(dir_fixture):
    """Lee el trail.jsonl de una fixture como lista de dicts, SIN pasar por motor/.
    Es la lectura de referencia del test; el constructor tendrá su propio `cargar`."""
    ruta = dir_fixture / NOMBRE_TRAIL
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    return [json.loads(l) for l in lineas if l.strip()]


def _huella_propia(seq, datado, snapshot, prev):
    """SHA-256 hex MAYÚSCULAS de la cadena canónica §2.1 — MI implementación (método 2)."""
    cadena = json.dumps(
        {"seq": seq, "datado": datado, "snapshot": snapshot, "prev": prev},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )
    return hashlib.sha256(cadena.encode("utf-8")).hexdigest().upper()


def _leer_esperado_rojo(dir_fixture):
    """Parsea el esperado.txt de una fixture rota -> (id_fallo, agregado). Mismo formato
    que _leer_esperado de run_gate.py. FAIL-FAST si falta el id o el agregado."""
    id_fallo = None
    agregado = None
    for linea in (dir_fixture / "esperado.txt").read_text(encoding="utf-8").splitlines():
        s = linea.strip()
        if not s or s.startswith("#"):
            continue
        if "->" in s:
            izq, der = s.split("->", 1)
            izq, der = izq.strip(), der.strip()
            if der.upper() in ("FALLO", "RECHAZO"):
                id_fallo = izq
            continue
        if ":" in s:
            clave, valor = s.split(":", 1)
            if clave.strip().lower() == "veredicto_detector":
                agregado = valor.strip().upper()
    assert id_fallo is not None, "esperado corrupto (sin id de fallo) en %s" % dir_fixture
    assert agregado is not None, "esperado corrupto (sin veredicto) en %s" % dir_fixture
    return id_fallo, agregado


def _verificar(dir_fixture):
    """Corre `motor.audit_trail.verificar_cadena` sobre el trail de la fixture.
    IMPORTA aquí dentro a propósito: hasta que exista el módulo, cada test que llame a
    esto falla con ImportError -> el ROJO buscado en esta fase."""
    from motor import audit_trail  # NO EXISTE aún -> ImportError esperado en fase test-primero
    entradas = audit_trail.cargar((dir_fixture / NOMBRE_TRAIL).read_text(encoding="utf-8"))
    return audit_trail.verificar_cadena(entradas)


def _ids_en_fallo(veredictos):
    return {v.id for v in veredictos if not v.ok}


# ==========================================================================================
# A. HUELLA — el algoritmo §2.1 del módulo debe COINCIDIR con mi implementación (método 2)
# ==========================================================================================
def test_huella_coincide_con_metodo_2():
    """`audit_trail.huella` (constructor) debe dar EXACTAMENTE la misma huella que mi
    recomputo independiente §2.1 para cada entrada del trail íntegro. Dos caminos que
    convergen = la huella está bien; divergen = ROJO."""
    from motor import audit_trail
    for e in _cargar_entradas_crudas(DIR_INTEGRA):
        esperada = _huella_propia(e["seq"], e["datado"], e["snapshot"], e["prev"])
        obtenida = audit_trail.huella(e["seq"], e["datado"], e["snapshot"], e["prev"])
        assert obtenida == esperada, (
            "huella §2.1 divergente en seq=%s: constructor=%s vs metodo2=%s"
            % (e["seq"], obtenida, esperada))
        assert obtenida == e["huella"], (
            "la huella almacenada en la fixture no casa con la recomputada en seq=%s" % e["seq"])


def test_huella_genesis_hex_mayusculas():
    """La huella es 64 hex en MAYÚSCULAS (SPEC §2.1) y el génesis lleva prev=''."""
    from motor import audit_trail
    entradas = _cargar_entradas_crudas(DIR_INTEGRA)
    genesis = entradas[0]
    assert genesis["seq"] == 0, "el génesis debe ser seq=0"
    assert genesis["prev"] == "", "el génesis debe llevar prev='' (huella vacía)"
    h = audit_trail.huella(genesis["seq"], genesis["datado"], genesis["snapshot"], genesis["prev"])
    assert len(h) == 64 and h == h.upper() and all(c in "0123456789ABCDEF" for c in h), (
        "la huella debe ser 64 hex MAYÚSCULAS; obtenido %r" % h)


# ==========================================================================================
# B. ÍNTEGRA -> SANO (criterio de aceptación: cadena bien encadenada no reporta nada)
# ==========================================================================================
def test_integra_sana():
    """Sobre la cadena íntegra, `verificar_cadena` NO debe emitir ningún veredicto en fallo.
    (SPEC §7: `audit/integra` -> SANO.)"""
    veredictos = _verificar(DIR_INTEGRA)
    fallos = _ids_en_fallo(veredictos)
    assert not fallos, "la cadena íntegra no debe reportar fallos; reportó %s" % sorted(fallos)


def test_trail_vacio_sin_veredictos():
    """SPEC §4: trail vacío -> [] (nada que reportar). Se comprueba con un trail vacío
    en memoria, sin escribir fixture (READ-ONLY)."""
    from motor import audit_trail
    entradas = audit_trail.cargar("")   # trail vacío
    veredictos = audit_trail.verificar_cadena(entradas)
    assert veredictos == [], "trail vacío debe dar [] (nada que reportar); dio %r" % veredictos


# ==========================================================================================
# C. FIXTURES ROTAS -> cada una su ROJO EXACTO (el id que nombra su esperado.txt)
# ==========================================================================================
def _asserta_rota(nombre):
    dir_fixture = DIR_ROTAS / nombre
    id_esperado, _agregado = _leer_esperado_rojo(dir_fixture)
    veredictos = _verificar(dir_fixture)
    fallos = _ids_en_fallo(veredictos)
    assert id_esperado in fallos, (
        "%s: se esperaba %s en fallo; fallos obtenidos=%s"
        % (nombre, id_esperado, sorted(fallos)))


def test_rota_01_entrada_alterada():
    """01: snapshot intermedio alterado sin recalcular su huella -> INV-AUDIT-CADENA."""
    _asserta_rota("01_entrada_alterada")


def test_rota_02_enlace_roto():
    """02: prev[k] no casa con la huella real de k-1 -> INV-AUDIT-ENLACE."""
    _asserta_rota("02_enlace_roto")


def test_rota_03_reordenada():
    """03: dos entradas intercambiadas -> rompe el enlace (INV-AUDIT-ENLACE)."""
    _asserta_rota("03_reordenada")


def test_rota_04_secuencia_hueco():
    """04: falta una entrada intermedia (seq salta) -> INV-AUDIT-SECUENCIA."""
    _asserta_rota("04_secuencia_hueco")


def test_rota_06_linea_corrupta():
    """06 (bug H1): una línea del JSONL no es JSON válido -> INV-AUDIT-ILEGIBLE.

    Un audit trail de compliance NO debe reventar con traceback ante un fichero
    ilegible (lo que HACÍA `cargar` con `json.loads` sin capturar), ni saltar la
    línea en silencio (eso escondería una manipulación = falso SANO, PEOR que
    reventar). Debe degradar a un Veredicto de defecto con forma de contrato."""
    _asserta_rota("06_linea_corrupta")


def test_rotas_localizan_primer_punto():
    """SPEC §4: el `detalle` del veredicto en fallo debe LOCALIZAR el problema (no solo
    decir 'roto'). Se exige que el detalle del id en fallo mencione la posición (seq/índice).
    Corner case: un detector que reporte 'roto' sin localización pasa los tests C pero no
    cumple el SPEC; este test lo caza."""
    import re
    for nombre in ("01_entrada_alterada", "02_enlace_roto", "04_secuencia_hueco",
                   "06_linea_corrupta"):
        dir_fixture = DIR_ROTAS / nombre
        id_esperado, _ = _leer_esperado_rojo(dir_fixture)
        veredictos = _verificar(dir_fixture)
        det = [v.detalle for v in veredictos if v.id == id_esperado and not v.ok]
        assert det, "%s: no hay veredicto en fallo para %s" % (nombre, id_esperado)
        assert any(re.search(r"\d", d) for d in det), (
            "%s: el detalle de %s debe localizar la posición (contener un índice); detalle=%r"
            % (nombre, id_esperado, det))


# ==========================================================================================
# D. LÍMITE -> SANO documentado (§5.2: la cola truncada NO se detecta en fase 1)
# ==========================================================================================
def test_limite_cola_truncada_da_sano():
    """05: cola truncada. La cadena restante es internamente válida -> `verificar_cadena`
    NO reporta fallos (SANO). Es el LÍMITE CONOCIDO §5.2, NO un verde bueno: este test
    DOCUMENTA que fase 1 no lo caza. Cuando exista el checkpoint (fase 2) este test cambiará."""
    veredictos = _verificar(DIR_LIMITE / "05_cola_truncada")
    fallos = _ids_en_fallo(veredictos)
    assert not fallos, (
        "LÍMITE §5.2: la cola truncada da SANO en fase 1 (hueco conocido); "
        "si reporta algo, revisar el SPEC. fallos=%s" % sorted(fallos))


# ==========================================================================================
# E. DETECTOR audit_chain -> contrato: inerte sin trail, cumple run(ctx)->list[Veredicto]
# ==========================================================================================
def test_detector_inerte_sin_trail(tmp_dir=None):
    """SPEC §5: `audit_chain.run(ctx)` devuelve [] cuando NO hay trail (no ensucia los runs
    de routing). Se ejercita con el registro real del kit sobre una fixture SIN trail."""
    from motor.config_loader import cargar_config
    from motor.runner import Runner, REGISTRO
    import detectores.audit_chain  # noqa: F401  -> NO EXISTE aún -> ImportError esperado
    config = cargar_config(_RAIZ_KIT / "config")
    runner = Runner(REGISTRO)
    ctx = runner.construir_ctx(root=FIXTURES / "limpias", config=config)
    veredictos = detectores.audit_chain.run(ctx)
    assert veredictos == [], (
        "audit_chain debe ser inerte (devolver []) donde no hay trail; devolvió %r" % veredictos)


def test_detector_reporta_forma_de_contrato():
    """SPEC §4 + CONTRATO §2: cada elemento devuelto por `verificar_cadena` es un Veredicto
    con los 5 campos (id, ok, esperado, obtenido, detalle). 'Se midió' exige forma de
    contrato, no solo que exista algo (barrido anti falso-verde de la skill)."""
    veredictos = _verificar(DIR_ROTAS / "01_entrada_alterada")
    assert veredictos, "sobre una fixture rota debe emitir al menos un veredicto"
    for v in veredictos:
        for campo in ("id", "ok", "esperado", "obtenido", "detalle"):
            assert hasattr(v, campo), "un veredicto no cumple el contrato: falta %r" % campo
        assert isinstance(v.ok, bool), "el campo ok debe ser bool; fue %r" % type(v.ok)


# ==========================================================================================
# runner de la suite
# ==========================================================================================
def main():
    tests = [
        test_huella_coincide_con_metodo_2,
        test_huella_genesis_hex_mayusculas,
        test_integra_sana,
        test_trail_vacio_sin_veredictos,
        test_rota_01_entrada_alterada,
        test_rota_02_enlace_roto,
        test_rota_03_reordenada,
        test_rota_04_secuencia_hueco,
        test_rota_06_linea_corrupta,
        test_rotas_localizan_primer_punto,
        test_limite_cola_truncada_da_sano,
        test_detector_inerte_sin_trail,
        test_detector_reporta_forma_de_contrato,
    ]
    fallos = 0
    for t in tests:
        try:
            t()
            print("PASA  %s" % t.__name__)
        except AssertionError as e:
            fallos += 1
            print("FALLA %s: %s" % (t.__name__, e))
        except Exception as e:  # ImportError / fixture ausente: en esta fase es lo ESPERADO
            fallos += 1
            print("ROJO  %s: %s: %s" % (t.__name__, type(e).__name__, e))
    print("-" * 70)
    if fallos:
        print("SUITE AUDIT-TRAIL: %d ROJO(S) de %d  <-- objetivo de la fase test-primero"
              % (fallos, len(tests)))
        return 1
    print("SUITE AUDIT-TRAIL VERDE: %d/%d" % (len(tests), len(tests)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
