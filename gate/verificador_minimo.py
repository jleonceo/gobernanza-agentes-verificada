#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
verificador_minimo.py — MÉTODO 2 del gate (verificador INDEPENDIENTE).

ESQUELETO (fase test-primero, 03/07/2026). Doctrina TechAcces: "cifra por instrumento =
dos métodos que coincidan". Este es el segundo instrumento. Falla en rojo hasta que el
CONSTRUCTOR implemente los detectores; ese rojo define el objetivo.

REGLA DE INDEPENDENCIA (mecanismo obligatorio #3 del SPEC) — este fichero NO importa:
    - motor.runner       (no reusa la agregación del runner: la RECOMPUTA)
    - motor.snapshot     (recomputa el snapshot con su propio código stdlib)
    - motor.veredicto    (recompone SANO/VIGILAR/ENFERMO por su cuenta)
Un bug común en el runner NO se propaga aquí, porque aquí NO se usa el runner.
Lo único COMPARTIDO con el método 1 es el CONTRATO del detector: run(ctx)->list[Veredicto].
Este verificador invoca cada detector directamente y agrega con SU PROPIO código.

Convergencia (estado real): DOBLE. (1) Indirecta: cada instrumento contrasta su mapa
contra el mismo `esperado.txt` de cada fixture (M1 en run_gate, M2 aquí en main()).
(2) DIRECTA (cableada desde D7): `run_gate.correr_comparacion_directa` —en modo
`--fixtures ambas`— compara mapa-a-mapa el `por_detector` de M1 (runner) con el `mapa`
de M2 (`verificar_fixture`, código propio SIN motor) vía `comparar_metodos`, y falla el
gate si divergen. Cierra el hueco: una discrepancia M1/M2 en un detector que el
`esperado.txt` no nombra ahora SÍ se caza. La independencia (§3) se mantiene: M2 no
ejecuta el motor; el orquestador corre los dos métodos independientes y contrasta.

Uso previsto:
    python gate/verificador_minimo.py                 # método 2 vs esperado.txt
    python gate/run_gate.py --fixtures ambas          # M1 + M2-indirecto + comparación directa
"""

import hashlib
import json
import sys
from pathlib import Path

# --- BOOTSTRAP de sys.path (idéntico al de run_gate): la raíz del kit (padre de gate/)
#     en el path para que `import detectores` / `import contrato` / `import
#     motor.config_loader` resuelvan al invocar desde la raíz. READ-ONLY.
_RAIZ_KIT = Path(__file__).resolve().parent.parent
if str(_RAIZ_KIT) not in sys.path:
    sys.path.insert(0, str(_RAIZ_KIT))

# --- SOLO se importa el CONTRATO compartido (los detectores) y config_loader.
#     NADA de motor.runner / motor.snapshot / motor.veredicto: la agregación y el
#     snapshot se RECOMPUTAN aquí con código propio (mecanismo obligatorio #3). -----
from motor.config_loader import cargar_config, compilar_conventions  # carga de config, NO agregación
import detectores.gate_routing as det_routing
import detectores.lint_corpus as det_lint
import detectores.panel_salud as det_panel
import detectores.result_envelope as det_envelope
import detectores.audit_chain as det_audit
# result_contract se valida aparte (envelopes de las fixtures rotas 04/05):
import contrato.result_contract as result_contract

RAIZ = Path(__file__).resolve().parent
FIXTURES = RAIZ / "fixtures"
CONFIG = RAIZ.parent / "config"

DETECTORES = {
    "gate_routing": det_routing.run,
    "lint_corpus": det_lint.run,
    "panel_salud": det_panel.run,
    "result_contract": det_envelope.run,
    "audit_chain": det_audit.run,
}


# ---------------------------------------------------------------------------
# Snapshot y agregación RECOMPUTADOS con código propio (stdlib), sin motor/.
# ---------------------------------------------------------------------------
# Réplica LOCAL del frozenset del motor (motor/veredicto.py:53). Se COPIA el valor a
# propósito: la independencia del 2º instrumento (mecanismo #3) prohíbe importar
# motor.veredicto, no duplicar una constante — igual que aquí ya se duplica el parser
# de esperado.txt. D6: antes se comparaba contra el literal único "alta", así que una
# severidad legal para el motor ("critica"/"critical"/"high") daba M1=ENFERMO y
# M2=VIGILAR y rompía el gate 'ambas' espuriamente. Si el motor amplía el conjunto,
# actualizar esta copia (los dos instrumentos deben partir del MISMO mapa de severidad).
_SEVERIDADES_ALTAS = frozenset({"alta", "critica", "critical", "high"})


def _agregar_propio(veredictos, severidades):
    """
    Recomputa SANO/VIGILAR/ENFERMO con lógica propia — NO llama a motor.veredicto.
    - todos ok=True -> SANO
    - algun ok=False severidad alta -> ENFERMO
    - algun ok=False severidad baja/media -> VIGILAR
    """
    if all(v.ok for v in veredictos):
        return "SANO"
    # Misma normalización que el motor (motor/veredicto.py:65: strip().lower()) para no
    # divergir por mayúsculas/espacios en la severidad declarada en invariantes.yaml.
    if any((not v.ok) and (severidades.get(v.id) or "").strip().lower() in _SEVERIDADES_ALTAS
           for v in veredictos):
        return "ENFERMO"
    return "VIGILAR"


class _CtxMinimo:
    """Contexto INDEPENDIENTE que cumple el CONTRATO §3, con código propio de este
    fichero — NO es motor.runner.Ctx (mecanismo #3: no reusa el runner). Expone lo que
    un detector lee: root inyectada, conventions compiladas, routing_paths, umbrales,
    exentas, y helpers de lectura READ-ONLY. Recompone la fontanería del ctx a mano
    para que un bug en el Ctx del runner NO se propague a este segundo instrumento.

    compilar_conventions() sí se reusa de config_loader: es COMPILACIÓN de config
    (permitida explícitamente), no la agregación de veredictos que debe ser independiente.
    """

    def __init__(self, root, config):
        # Mismo endurecimiento que motor.runner.Ctx: root ABSOLUTIZADA para que un
        # `root/rel` construido por un detector llegue absoluto a read_text() y no se
        # re-una a root (doble-join = falso-ROJO con root relativa). No es expanduser:
        # es resolver una ruta ya inyectada. Los dos instrumentos del gate deben tratar
        # la root igual para no divergir por este motivo.
        self.root = Path(root).resolve()
        self.conventions = compilar_conventions(config["corpus_conventions"])
        self.invariantes = {inv["id"]: inv for inv in config["invariantes"]["invariantes"]}
        self.umbrales = config.get("umbrales", {}) or {}
        self.exentas = set((config.get("exentas", {}) or {}).get("exentas_routing", []) or [])
        self.routing_paths = config.get("routing_paths", {}) or {}
        self.audit_trail = config.get("audit_trail", {}) or {}

    def read_text(self, path):
        p = Path(path)
        if not p.is_absolute():
            p = self.root / p
        return p.read_text(encoding="utf-8-sig")

    def iter_files(self, subdir=".", glob="*"):
        base = self.root / subdir
        if not base.exists():
            return []
        return sorted(base.glob(glob))

    def existe(self, path):
        p = Path(path)
        if not p.is_absolute():
            p = self.root / p
        return p.exists()


def _construir_ctx_minimo(root, config):
    """Construye un ctx INDEPENDIENTE (código propio, no motor.runner.Ctx) que cumple
    el CONTRATO §3. Segundo instrumento: recompone la fontanería a mano."""
    return _CtxMinimo(root, config)


def _cuenta_ok_crudos(veredictos):
    """Cuenta Veredicto.ok crudos — dato bruto que luego se contrasta contra el esperado."""
    return sum(1 for v in veredictos if v.ok)


# ---------------------------------------------------------------------------
# Contraste contra el ESPERADO del fixture (no re-agrega ciegamente).
# ---------------------------------------------------------------------------
def verificar_fixture(caso_dir, config, es_limpia):
    """
    Corre cada detector directamente sobre el caso, agrega con código propio y
    CONTRASTA contra la etiqueta esperada del fixture:
      - limpia -> se espera SANO
      - rota   -> se espera el rojo NOMBRADO en esperado.txt
    Al verificar contra el ESPERADO (no solo re-agregar la salida cruda), un detector
    castrado que emita OK sobre una fixture-rota DIVERGE del esperado y se caza.
    """
    # Severidades: la lista principal MÁS el bloque on-demand (INV-R4, RESULT-CONTRACT),
    # que solo se emiten ante un defecto pero cuya severidad 'alta' hace falta para agregar
    # a ENFERMO en vez de a un VIGILAR por defecto. Leer la MISMA config que el runner NO
    # viola la independencia (§3): lo independiente es _agregar_propio, no de dónde sale la
    # severidad — ambos instrumentos deben partir del mismo mapa de severidad para coincidir.
    inv_block = config["invariantes"]
    # `.get("severidad")` (no `inv["severidad"]`) para ser SIMÉTRICO con el runner de M1
    # (motor/runner usa .get y tolera ausencia -> None -> VIGILAR). Hoy `cargar_config` exige
    # severidad (FAIL-FAST), asi que no se alcanza; pero si esa validacion se relajara, M2 no
    # debe romper con KeyError donde M1 degrada -> los dos instrumentos convergen igual.
    severidades = {inv["id"]: inv.get("severidad") for inv in inv_block["invariantes"]}
    for _id, _sev in (inv_block.get("severidades_on_demand") or {}).items():
        severidades.setdefault(_id, _sev)
    ctx = _construir_ctx_minimo(caso_dir, config)

    mapa = {}
    for nombre, run in DETECTORES.items():
        veredictos = run(ctx)                      # CONTRATO compartido: list[Veredicto]
        mapa[nombre] = _agregar_propio(veredictos, severidades)

    if es_limpia:
        esperado = {n: "SANO" for n in DETECTORES}
    else:
        esperado = _leer_esperado_rojo(caso_dir / "esperado.txt")   # detector -> veredicto rojo

    return mapa, esperado


def comparar_metodos(mapa_m1, mapa_m2):
    """
    MÉTODO 1 (runner, viene de run_gate) vs MÉTODO 2 (este). Deben COINCIDIR.

    Función PURA: devuelve la LISTA de divergencias `detector -> (M1, M2)` (vacía si
    convergen). No hace sys.exit -> el llamador (run_gate.correr_comparacion_directa)
    decide fallar el gate. Compara sobre la UNIÓN de claves para cazar también que un
    método reporte un detector que el otro no (get() -> None cuenta como divergencia).

    CABLEADA desde D7: `run_gate.correr_comparacion_directa` la invoca por fixture con
    el `por_detector` de M1 (runner) y el `mapa` de M2 (código propio, sin motor). Cierra
    el hueco de la convergencia indirecta: caza una divergencia M1/M2 en un detector que
    el `esperado.txt` NO nombra.
    """
    divergencias = []
    for det in sorted(set(mapa_m1) | set(mapa_m2)):
        v1, v2 = mapa_m1.get(det), mapa_m2.get(det)
        if v1 != v2:
            divergencias.append("%s: M1=%s M2=%s" % (det, v1, v2))
    return divergencias


# ---------------------------------------------------------------------------
# AUDIT TRAIL — MÉTODO 2 del hash: recomputo INDEPENDIENTE de la cadena.
# ---------------------------------------------------------------------------
# NO llama a motor.audit_trail.verificar_cadena ni a su .huella: relee el JSONL y
# recomputa la huella §2.1 con SHA-256 PROPIO. Segundo instrumento del hash: si su
# veredicto (SANO/roto y qué id) coincide con el del detector (método 1) fixture a
# fixture, dos implementaciones distintas de §2.1 convergen. Divergen -> ROJO.
def _huella_propia_audit(seq, datado, snapshot, prev):
    """SHA-256 hex MAYÚSCULAS de la cadena canónica §2.1 — recompute PROPIO (método 2)."""
    cadena = json.dumps(
        {"seq": seq, "datado": datado, "snapshot": snapshot, "prev": prev},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )
    return hashlib.sha256(cadena.encode("utf-8")).hexdigest().upper()


def _ids_rotos_audit(trail_jsonl_texto):
    """Recorre el trail (texto JSONL) con código PROPIO y devuelve el conjunto de ids
    INV-AUDIT-* rotos (vacío = cadena íntegra en fase 1). Camino independiente del
    detector: relee y re-hashea aquí, sin motor.audit_trail.

    ROBUSTEZ (bug H1): una línea que no es JSON válido -> INV-AUDIT-ILEGIBLE, por SU PROPIO
    camino (captura del JSONDecodeError aquí, no reusa `cargar`). Debe converger con M1: si
    el trail es ilegible, ambos instrumentos reportan SOLO INV-AUDIT-ILEGIBLE (no se puede
    verificar el resto de forma fiable). Ni traceback ni falso SANO en el segundo camino."""
    entradas = []
    for l in trail_jsonl_texto.splitlines():
        if not l.strip():
            continue
        try:
            entradas.append(json.loads(l))
        except (json.JSONDecodeError, ValueError):
            # Trail ilegible: reporta SOLO INV-AUDIT-ILEGIBLE (mismo criterio que M1: un
            # fichero que no se parsea no permite verificar la cadena).
            return {"INV-AUDIT-ILEGIBLE"}
    rotos = set()
    if not entradas:
        return rotos
    prev_esperado = ""
    for i, e in enumerate(entradas):
        seq, datado = e.get("seq"), e.get("datado")
        snapshot, prev = e.get("snapshot"), e.get("prev")
        huella_real = _huella_propia_audit(seq, datado, snapshot, prev)
        if seq != i:
            rotos.add("INV-AUDIT-SECUENCIA")
        if huella_real != e.get("huella"):
            rotos.add("INV-AUDIT-CADENA")
        if prev != prev_esperado:
            rotos.add("INV-AUDIT-ENLACE")
        prev_esperado = huella_real
    return rotos


def verificar_audit_convergencia(config):
    """Contrasta, fixture a fixture del audit trail, el veredicto del MÉTODO 1 (el
    detector audit_chain vía el ctx mínimo, código de este fichero) contra el MÉTODO 2
    (recompute PROPIO `_ids_rotos_audit`). Deben coincidir en el CONJUNTO de ids rotos.

    integra + límite -> conjunto vacío (SANO); cada rota -> su id nombrado presente.
    Divergen -> ROJO. Cierra el segundo camino del hash del audit trail (§8, método 2)."""
    trail_rel = (config.get("audit_trail") or {}).get("trail_path")
    if not trail_rel:
        _fallar("audit: falta trail_path en audit_trail.yaml (método 2 no puede recomputar).")

    casos = [("audit/integra", FIXTURES / "audit" / "integra", set())]
    for caso in sorted((FIXTURES / "audit_rotas").iterdir()):
        if caso.is_dir():
            id_esp = _leer_esperado_rojo_id(caso / "esperado.txt")
            casos.append((caso.name, caso, {id_esp}))
    for caso in sorted((FIXTURES / "audit_limite").iterdir()):
        if caso.is_dir():
            casos.append((caso.name, caso, set()))   # límite: SANO en fase 1

    for nombre, ruta, ids_min in casos:
        ctx = _construir_ctx_minimo(ruta, config)
        # MÉTODO 1: el detector (audit_chain.run) sobre el ctx mínimo -> ids rotos.
        v_m1 = {v.id for v in det_audit.run(ctx) if not v.ok}
        # MÉTODO 2: recompute propio releyendo el trail.
        texto = (ruta / trail_rel).read_text(encoding="utf-8")
        v_m2 = _ids_rotos_audit(texto)
        if v_m1 != v_m2:
            _fallar("audit/%s: método 1 (detector) y método 2 (recompute propio) DIVERGEN: "
                    "M1=%s M2=%s" % (nombre, sorted(v_m1), sorted(v_m2)))
        # el id nombrado por el esperado debe estar en ambos (no basta con que converjan a vacío).
        if ids_min and not ids_min <= v_m2:
            _fallar("audit/%s: el id esperado %s no aparece en el recompute (M2=%s)"
                    % (nombre, sorted(ids_min), sorted(v_m2)))
    return True


def _leer_esperado_rojo_id(path):
    """Extrae SOLO el id del `<ID> -> FALLO` del esperado.txt de una rota audit. Código
    propio (no reusa el parser de M1). FAIL-FAST si falta."""
    for linea in path.read_text(encoding="utf-8").splitlines():
        s = linea.strip()
        if not s or s.startswith("#"):
            continue
        if "->" in s:
            return s.split("->", 1)[0].strip()
    _fallar("esperado audit corrupto en %s: sin id de fallo." % path)


def main():
    config = cargar_config(CONFIG)   # FAIL-FAST

    # Limpias -> todos SANO por camino independiente:
    mapa_limpias, esp_limpias = verificar_fixture(FIXTURES / "limpias", config, es_limpia=True)
    if mapa_limpias != esp_limpias:
        _fallar(f"LIMPIAS divergen del esperado SANO: {mapa_limpias}")

    # Rotas -> cada una su rojo nombrado:
    for caso in sorted((FIXTURES / "rotas").iterdir()):
        if not caso.is_dir():
            continue
        mapa, esperado = verificar_fixture(caso, config, es_limpia=False)
        if not _rojo_coincide(mapa, esperado):
            _fallar(f"{caso.name}: metodo2 no reproduce el rojo esperado {esperado}, dio {mapa}")

    # Audit trail -> método 1 (detector) vs método 2 (recompute propio) convergen:
    verificar_audit_convergencia(config)

    print("VERIFICADOR MINIMO (metodo 2 + audit convergencia) VERDE")
    return 0


# --- helpers (todo stdlib, código PROPIO — no se importa el parser de run_gate) ---
def _leer_esperado_rojo(path):
    """Parsea el esperado.txt de una fixture rota -> {"detector", "veredicto"}.

    Formato (líneas sueltas, '#' = comentario; la línea '<ID> -> FALLO|RECHAZO' se ignora
    aquí, basta el par detector/veredicto_detector):
        detector: <nombre>
        veredicto_detector: <SANO|VIGILAR|ENFERMO>
    Segundo instrumento: se re-parsea con código propio, NO se reutiliza el parser del
    método 1. FAIL-FAST: si falta el detector o su veredicto, aborta (esperado corrupto)."""
    detector = None
    veredicto = None
    for linea in path.read_text(encoding="utf-8").splitlines():
        s = linea.strip()
        if not s or s.startswith("#") or "->" in s:
            continue
        if ":" in s:
            clave, valor = s.split(":", 1)
            clave, valor = clave.strip().lower(), valor.strip()
            if clave == "detector":
                detector = valor
            elif clave == "veredicto_detector":
                veredicto = valor.upper()
    if detector is None or veredicto is None:
        _fallar("esperado corrupto en %s: falta 'detector' o 'veredicto_detector'." % path)
    return {"detector": detector, "veredicto": veredicto}


def _rojo_coincide(mapa, esp):
    """El mapa {detector -> veredicto} del método 2 reproduce el rojo esperado del fixture.

    Exige DOS cosas (independiente y estricto, para cazar tanto un detector castrado como
    uno que dispara de más): (1) el detector NOMBRADO muestra EXACTAMENTE su veredicto
    esperado; y (2) TODO otro detector queda SANO — la fixture siembra UN defecto, así que
    un segundo rojo espurio es regresión, no coincidencia. Un detector que devuelve OK
    sobre su propia fixture rota falla (1); uno que dispara sobre una fixture ajena falla (2)."""
    det = esp["detector"]
    if mapa.get(det) != esp["veredicto"]:
        return False
    return all(v == "SANO" for n, v in mapa.items() if n != det)


def _fallar(msg):
    sys.stderr.write("ROJO: " + msg + "\n")
    sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
