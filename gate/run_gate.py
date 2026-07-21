#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
run_gate.py — MÉTODO 1 del gate (camino feliz + camino negativo).

ESQUELETO (fase test-primero, 03/07/2026). Importa el motor y los detectores que
TODAVÍA NO EXISTEN: es CORRECTO que este fichero falle con ImportError hasta que el
CONSTRUCTOR implemente motor/ y detectores/. Ese rojo ES el objetivo: define qué
tiene que existir y cómo se ejecuta el gate.

Uso previsto:
    python gate/run_gate.py --fixtures limpias   # MÉTODO 1: todos SANO
    python gate/run_gate.py --fixtures rotas     # MÉTODO 1-NEGATIVO: cada rojo esperado
    python gate/run_gate.py --fixtures ambas     # corre las dos y exige convergencia

    # Correr sobre TU corpus (deuda GATE 2, 04/07/2026): apunta el gate a cualquier raíz
    # sin escribirte un runner a mano. La raíz se INYECTA (nunca expanduser), igual que
    # promete install.md §1.5; --config apunta a otra carpeta config/ (por defecto la del kit):
    python gate/run_gate.py --root /ruta/a/mi/corpus
    python gate/run_gate.py --root /ruta/a/mi/corpus --config /ruta/a/mi/config

Contrato de salida:
  - modo fixtures (por defecto): exit 0 si el gate pasa; exit != 0 (motivo por stderr) si falla.
  - modo --root: exit 0 si el corpus agrega SANO; exit != 0 si VIGILAR/ENFERMO (con el desglose).
"""

import argparse
import sys
from pathlib import Path

# --- BOOTSTRAP de sys.path: la raíz del kit (padre de gate/) debe estar en el path
#     para que `import motor` / `import detectores` / `import contrato` resuelvan al
#     invocar `python gate/run_gate.py` desde la raíz (sys.path[0] sería gate/, no la
#     raíz). No hay __init__.py ni paquete instalado; se inyecta aquí, antes de importar
#     el motor. READ-ONLY, sin efectos fuera del proceso.
_RAIZ_KIT = Path(__file__).resolve().parent.parent
if str(_RAIZ_KIT) not in sys.path:
    sys.path.insert(0, str(_RAIZ_KIT))

# --- IMPORTS DEL MOTOR y DETECTORES -----------------------------------------
from motor.config_loader import cargar_config          # FAIL-FAST: clave ausente -> aborta
from motor.runner import Runner, REGISTRO              # registro inyectable de detectores
from motor.snapshot import snapshot_normalizado        # relativiza + sorted + excluye mtime

# Registrar los detectores (el import puebla el REGISTRO por el decorador @registrar):
import detectores.gate_routing      # noqa: F401  -> registra "gate_routing"
import detectores.lint_corpus       # noqa: F401  -> registra "lint_corpus"
import detectores.panel_salud       # noqa: F401  -> registra "panel_salud"
import detectores.result_envelope   # noqa: F401  -> registra "result_contract" (envelopes)
import detectores.audit_chain       # noqa: F401  -> registra "audit_chain" (audit trail)

RAIZ = Path(__file__).resolve().parent
FIXTURES = RAIZ / "fixtures"
CONFIG = RAIZ.parent / "config"


# ---------------------------------------------------------------------------
# COBERTURA-MOTOR (mecanismo obligatorio #2 del SPEC)
# ---------------------------------------------------------------------------
def assert_cobertura_motor(config, runner):
    """
    ASSERT: {ids declarados en invariantes.yaml} == {ids que el registro ejecuto} y len>=3.
    Prueba EJECUCIÓN por el registro, NO corrección de la lógica.
    Si no cuadra -> ROJO 'MOTOR NO EJERCITADO'.
    """
    ids_declarados = {inv["id"] for inv in config["invariantes"]["invariantes"]}
    ids_ejecutados = runner.ids_ejecutados()   # el runner reporta qué ids emitió el registro

    if len(ids_declarados) < 3:
        _fallar("MOTOR NO EJERCITADO: invariantes.yaml declara menos de 3 invariantes.")
    if ids_declarados != ids_ejecutados:
        _fallar(
            "MOTOR NO EJERCITADO: los ids declarados en invariantes.yaml no coinciden "
            f"con los que el registro ejecuto.\n"
            f"  declarados: {sorted(ids_declarados)}\n"
            f"  ejecutados: {sorted(ids_ejecutados)}"
        )


# ---------------------------------------------------------------------------
# MÉTODO 1: fixtures limpias -> todos SANO
# ---------------------------------------------------------------------------
def correr_limpias(config):
    runner = Runner(REGISTRO)
    resultado = runner.correr(root=FIXTURES / "limpias", config=config)
    assert_cobertura_motor(config, runner)

    if resultado.agregado != "SANO":
        _fallar(f"MÉTODO 1 FALLA: fixtures limpias deberian dar SANO, dieron {resultado.agregado}.")
    return resultado


# ---------------------------------------------------------------------------
# MÉTODO 1-NEGATIVO: cada fixture rota -> EXACTAMENTE su rojo esperado
# ---------------------------------------------------------------------------
def correr_rotas(config):
    """
    Cada subcarpeta de fixtures/rotas/ tiene un defecto sembrado y un esperado.txt
    con el rojo EXACTO. Un detector castrado que siempre devuelva OK NO produce el
    rojo esperado y FALLA aqui.
    """
    runner = Runner(REGISTRO)
    fallos = []
    for caso in sorted((FIXTURES / "rotas").iterdir()):
        if not caso.is_dir():
            continue
        esperado = _leer_esperado(caso / "esperado.txt")
        resultado = runner.correr(root=caso, config=config)
        if not _coincide_rojo(resultado, esperado):
            fallos.append(f"{caso.name}: esperado {esperado}, obtenido {resultado.resumen()}")
    if fallos:
        _fallar("MÉTODO 1-NEGATIVO FALLA:\n" + "\n".join(fallos))
    return True


# ---------------------------------------------------------------------------
# PASADA AUDIT: el audit trail encadenado (integra -> SANO; rotas -> su rojo exacto)
# ---------------------------------------------------------------------------
def correr_audit(config):
    """Corre el registro sobre las fixtures del AUDIT TRAIL y exige:
      - fixtures/audit/integra           -> SANO (cadena bien encadenada).
      - fixtures/audit_rotas/*           -> su rojo EXACTO (id + agregado del esperado.txt).
      - fixtures/audit_limite/05_*       -> SANO documentado (LÍMITE §5.2: la cola truncada
                                            no se caza en fase 1; es el hueco conocido).

    Reusa `_leer_esperado` / `_coincide_rojo` (mismo formato de esperado.txt que las rotas
    existentes). El resto de detectores (routing/lint/panel/result) son inertes sobre estas
    fixtures (sin skills, sin registro): solo audit_chain habla, así que el agregado es el
    del audit trail. NO toca las pasadas existentes."""
    runner = Runner(REGISTRO)
    fallos = []

    # Íntegra -> SANO.
    res_integra = runner.correr(root=FIXTURES / "audit" / "integra", config=config)
    if res_integra.agregado != "SANO":
        fallos.append("audit/integra: esperado SANO, obtenido %s" % res_integra.resumen())

    # Rotas -> cada una su rojo exacto.
    for caso in sorted((FIXTURES / "audit_rotas").iterdir()):
        if not caso.is_dir():
            continue
        esperado = _leer_esperado(caso / "esperado.txt")
        resultado = runner.correr(root=caso, config=config)
        if not _coincide_rojo(resultado, esperado):
            fallos.append("audit_rotas/%s: esperado %s, obtenido %s"
                          % (caso.name, esperado, resultado.resumen()))

    # Límite -> SANO documentado (la cola truncada queda internamente válida en fase 1).
    for caso in sorted((FIXTURES / "audit_limite").iterdir()):
        if not caso.is_dir():
            continue
        resultado = runner.correr(root=caso, config=config)
        if resultado.agregado != "SANO":
            fallos.append("audit_limite/%s: LÍMITE §5.2 esperado SANO (hueco conocido), "
                          "obtenido %s" % (caso.name, resultado.resumen()))

    if fallos:
        _fallar("PASADA AUDIT FALLA:\n" + "\n".join(fallos))
    return True


# ---------------------------------------------------------------------------
# MECANISMO OBLIGATORIO #3: comparación DIRECTA método 1 vs método 2 (cableado D7)
# ---------------------------------------------------------------------------
def correr_comparacion_directa(config):
    """Contrasta, fixture a fixture, el mapa detector->semáforo de MÉTODO 1 (runner)
    con el de MÉTODO 2 (verificador_minimo, código propio). Cierra el hueco de la
    convergencia indirecta (ambos vs esperado.txt): caza una divergencia M1/M2 en un
    detector que el `esperado.txt` NO nombra.

    Independencia (§3) preservada: M2 usa `verificar_fixture` (su propio ctx + agregación,
    SIN el runner del motor); este orquestador solo corre los dos métodos independientes y
    contrasta sus salidas. Diverge -> ROJO (falla el gate).

    ALCANCE (honesto): esta comparación caza divergencias de PLUMBING/agregación (bug del
    runner: ctx, cobertura, semáforo agregado) — M1 y M2 los calculan por caminos distintos.
    NO caza un bug en la LÓGICA de un detector: ambos métodos reusan el mismo `run(ctx)`, así
    que un detector con lógica errónea da igual en los dos. Eso lo cubre el camino
    fixtures-rotas vs `esperado.txt`. Los dos mecanismos son complementarios, no redundantes."""
    import sys as _sys
    if str(RAIZ) not in _sys.path:
        _sys.path.insert(0, str(RAIZ))     # gate/ en el path para importar el método 2
    import verificador_minimo as m2

    casos = [("limpias", FIXTURES / "limpias", True)]
    for caso in sorted((FIXTURES / "rotas").iterdir()):
        if caso.is_dir():
            casos.append((caso.name, caso, False))

    divergencias = []
    for nombre, ruta, es_limpia in casos:
        runner = Runner(REGISTRO)
        res_m1 = runner.correr(root=ruta, config=config)      # MÉTODO 1: mapa del runner
        mapa_m1 = dict(res_m1.por_detector)
        mapa_m2, _esp = m2.verificar_fixture(ruta, config, es_limpia=es_limpia)  # MÉTODO 2
        for linea in m2.comparar_metodos(mapa_m1, mapa_m2):
            divergencias.append("%s -> %s" % (nombre, linea))

    if divergencias:
        _fallar("MECANISMO #3 FALLA: método 1 y método 2 DIVERGEN por fixture:\n  "
                + "\n  ".join(divergencias))
    return True


# ---------------------------------------------------------------------------
# H1 (v1.0): SANO-por-vacío vs SANO-real. Un detector puede resolver SANO porque
# NO había nada que inspeccionar (corpus sin skills/registro) — con gracia, pero
# eso NO es "routing sano". El resumen --root debe SURFACEARLO para no dar falsa
# confianza (el propio README lo combate). Se reconoce por el `obtenido` que el
# detector deja al degradar con gracia. Explícito y ampliable (no adivina).
# ---------------------------------------------------------------------------
MARCADORES_VACIO = {
    # obtenido del Veredicto (ok=True por vacío)  ->  nota a surfacear en el resumen
    "sin_skills_que_cubrir": "0 skills en el corpus — ¿--root/config correctos?",
}


def _anotacion_vacio(veredictos):
    """Si un detector resolvió SANO porque no había nada que comprobar, devuelve la
    nota a surfacear; None si su SANO es real. Solo mira veredictos ok=True (un
    ok=False ya sale por el desglose de defectos)."""
    for v in veredictos:
        if v.ok and v.obtenido in MARCADORES_VACIO:
            return MARCADORES_VACIO[v.obtenido]
    return None


# ---------------------------------------------------------------------------
# MODO --root: correr TODOS los detectores sobre una raíz ARBITRARIA (deuda GATE 2)
# ---------------------------------------------------------------------------
def correr_corpus(root, config):
    """Corre el registro completo sobre `root` (raíz INYECTADA, no las fixtures) e imprime
    su semáforo agregado + desglose por detector. Devuelve el código de salida:
      - 0 si el corpus agrega SANO,
      - 1 si VIGILAR o ENFERMO (hay algo que revisar).

    NO reusa las fixtures del kit: es el runner apuntado a un corpus real. La raíz se pasa
    tal cual a Runner.correr(root=...) — el Ctx la absolutiza con Path(root).resolve()
    (resolver una ruta ya inyectada, nunca expanduser/HOME; install.md §1.5, CONTRATO §1).
    """
    ruta = Path(root)
    if not ruta.exists():
        _fallar("MODO --root: la raíz de corpus no existe: %s" % ruta)

    runner = Runner(REGISTRO)
    resultado = runner.correr(root=ruta, config=config)

    partes = []
    for k in sorted(resultado.por_detector):
        estado = resultado.por_detector[k]
        # solo un SANO puede ser "SANO por vacío"; un defecto ya sale por su cuenta
        nota = _anotacion_vacio(resultado.veredictos_de(k)) if estado == "SANO" else None
        partes.append("%s=%s%s" % (k, estado, " (%s)" % nota if nota else ""))
    desglose = "; ".join(partes)
    print("CORPUS %s -> %s  (%s)" % (ruta, resultado.agregado, desglose))
    if resultado.agregado != "SANO":
        fallos = sorted(v.id for v in resultado.veredictos if not v.ok)
        sys.stderr.write("DEFECTOS: " + ", ".join(fallos) + "\n")
        for v in resultado.veredictos:
            if not v.ok:
                sys.stderr.write("  - %s: %s\n" % (v.id, v.detalle))
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", choices=["limpias", "rotas", "ambas"], default="ambas",
                    help="modo gate sobre las fixtures del kit (por defecto).")
    ap.add_argument("--root", default=None,
                    help="raíz de TU corpus: corre los detectores sobre ella en vez de las "
                         "fixtures. La raíz se INYECTA (nunca expanduser).")
    ap.add_argument("--config", default=None,
                    help="carpeta config/ a usar (por defecto la del kit: <kit>/config).")
    args = ap.parse_args()

    config_dir = Path(args.config) if args.config else CONFIG
    config = cargar_config(config_dir)   # FAIL-FAST si falta una clave

    # MODO --root: corpus arbitrario. Mutuamente excluyente con el gate de fixtures
    # (si el usuario pasa --root, quiere correr SU corpus, no las fixtures del kit).
    if args.root is not None:
        return correr_corpus(args.root, config)

    if args.fixtures in ("limpias", "ambas"):
        correr_limpias(config)
    if args.fixtures in ("rotas", "ambas"):
        correr_rotas(config)
    if args.fixtures == "ambas":
        # Mecanismo #3 (cableado D7): además del contraste de cada método vs esperado.txt,
        # exigir que método 1 y método 2 den el MISMO mapa por fixture (convergencia directa).
        correr_comparacion_directa(config)
        # Pasada AUDIT: el audit trail encadenado (integra SANO + rotas su rojo + límite).
        correr_audit(config)

    print("GATE (metodo 1 + convergencia directa m1/m2 + audit) VERDE" if args.fixtures == "ambas"
          else "GATE (metodo 1) VERDE")
    return 0


# --- helpers (implementados por el CONSTRUCTOR) -----------------------------
def _leer_esperado(path):
    """Parsea el esperado.txt de una fixture rota -> dict con el rojo EXACTO.

    Formato de las fixtures (líneas sueltas, '#' = comentario):
        <ID> -> FALLO|RECHAZO           (el invariante que debe fallar)
        detector: <nombre>
        veredicto_detector: <SANO|VIGILAR|ENFERMO>
    Devuelve {"id_fallo": str, "detector": str, "agregado": str}. FAIL-FAST: si falta
    el id que debe fallar o el veredicto agregado esperado, aborta (esperado corrupto).
    """
    id_fallo = None
    detector = None
    agregado = None
    for linea in path.read_text(encoding="utf-8").splitlines():
        s = linea.strip()
        if not s or s.startswith("#"):
            continue
        if "->" in s:
            izq, der = s.split("->", 1)
            id_fallo = izq.strip()
            # der = 'FALLO' | 'RECHAZO' (ambos = defecto detectado); no se usa como valor,
            # basta con que exista para saber que ese id debe fallar.
            continue
        if ":" in s:
            clave, valor = s.split(":", 1)
            clave, valor = clave.strip().lower(), valor.strip()
            if clave == "detector":
                detector = valor
            elif clave == "veredicto_detector":
                agregado = valor.upper()
    if id_fallo is None or agregado is None:
        _fallar("esperado corrupto en %s: falta el id que debe fallar o el veredicto "
                "agregado esperado." % path)
    return {"id_fallo": id_fallo, "detector": detector, "agregado": agregado}


def _coincide_rojo(res, esp):
    """El resultado del run reproduce EXACTAMENTE el rojo esperado de la fixture.

    Se exige: (1) el agregado del run == el agregado esperado (p.ej. ENFERMO), y (2) el
    id declarado como fallo aparece EN FALLO (ok=False) entre los veredictos del run. Un
    detector castrado que devuelva OK NO produce ese id en fallo -> no coincide -> el
    MÉTODO 1-NEGATIVO caza el falso verde."""
    if res.agregado != esp["agregado"]:
        return False
    ids_en_fallo = {v.id for v in res.veredictos if not v.ok}
    return esp["id_fallo"] in ids_en_fallo


def _fallar(msg):
    sys.stderr.write("ROJO: " + msg + "\n")
    sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
