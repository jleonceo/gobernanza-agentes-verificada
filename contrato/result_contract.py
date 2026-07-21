# -*- coding: utf-8 -*-
"""
result_contract.py — validador determinista del ENVELOPE de handoff.

QUÉ ES: la pieza de CÓDIGO (sin IA, inmune a model-drift) que re-comprueba que el
sobre (envelope) con el que un agente/skill cierra un handoff cumple el contrato:
    - status  in {OK, WARN, BLOCKED, ERROR}
    - risk    in {LOW, MEDIUM, HIGH, CRITICAL}
    - campos presentes: status, risk, skill_applied, summary, artifacts, next
    - REGLA DURA: status in {BLOCKED, ERROR}  =>  summary NO vacío (lo que el
      orquestador muestra al humano cuando el flujo se corta).

QUÉ NO HACE: no decide el status correcto. Garantiza la *gramática* del envelope
(que el status sea uno de los 4 enums, bien formado), NO su *verdad* (que el agente
elija BLOCKED cuando realmente debe). Esa segunda mitad sigue siendo lógica del agente.

POR QUÉ STDLIB PURO (sin pydantic): el kit se instala en una carpeta limpia de un
tercero. El origen TechAcces usaba pydantic; aquí se DES-ACOPLA a stdlib para que el
gate corra con solo Python base (era una deuda señalada en la refutación del SPEC).

FORMATOS DE ENTRADA que acepta:
    - un dict de Python (envelope ya parseado)
    - un fichero .json con el envelope
    - un texto/markdown con un bloque `## RESULTADO` de pares `clave: valor`
      (compatibilidad con el formato de handoff en prosa)

USO CLI:
    python result_contract.py --self-test          # banco de no-regresión
    python result_contract.py <envelope.json>      # valida un fichero JSON
    python result_contract.py <handoff.md>         # valida un bloque ## RESULTADO
    python result_contract.py -                     # valida desde stdin

READ-ONLY: no escribe nada. Determinista: misma entrada -> mismo veredicto.

agent-governance-checks · v1 · des-acoplado de evals/result_contract.py (TechAcces).
"""

import json
import re
import sys

# --- Enums del contrato (constantes stdlib, sin pydantic) -------------------

STATUS_VALIDOS = ("OK", "WARN", "BLOCKED", "ERROR")
RISK_VALIDOS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

# status que cortan el flujo: exigen un summary con sustancia.
STATUS_DE_CORTE = ("BLOCKED", "ERROR")

# Campos obligatorios del envelope.
CAMPOS = ("status", "risk", "skill_applied", "summary", "artifacts", "next")

# Longitud mínima del summary cuando el flujo se corta (ni vacío ni telegráfico).
MIN_SUMMARY_CORTE = 15


# --- Resultado de validación (dataclass ligera, sin dependencias) -----------

class ResultadoValidacion(object):
    """
    Resultado inmutable-por-convención de validar un envelope.

    estado: uno de
        'VALIDO'             -> cumple el contrato, sin avisos.
        'VALIDO_CON_AVISOS'  -> cumple el contrato pero hay incoherencias blandas.
        'INVALIDO'           -> rompe el contrato (enum/campo/regla dura): RECHAZO.
        'SIN_BLOQUE'         -> no se encontró un envelope parseable en la entrada.
    errores: lista de str (motivos del RECHAZO; vacía si es válido).
    avisos:  lista de str (incoherencias que NO rompen el contrato).
    """

    __slots__ = ("estado", "errores", "avisos")

    def __init__(self, estado, errores=None, avisos=None):
        self.estado = estado
        self.errores = list(errores or [])
        self.avisos = list(avisos or [])

    @property
    def rechazado(self):
        """True si el envelope NO cumple el contrato (INVALIDO o SIN_BLOQUE)."""
        return self.estado in ("INVALIDO", "SIN_BLOQUE")

    @property
    def ok(self):
        """True si el envelope cumple el contrato (con o sin avisos blandos)."""
        return self.estado in ("VALIDO", "VALIDO_CON_AVISOS")

    def __repr__(self):
        return "ResultadoValidacion(estado=%r, errores=%r, avisos=%r)" % (
            self.estado, self.errores, self.avisos
        )


# --- Núcleo de validación: las reglas DURAS (rompen el contrato) ------------

def _validar_dict(datos):
    """
    Aplica el contrato a un dict ya parseado. Devuelve ResultadoValidacion.
    Las reglas DURAS producen 'INVALIDO'; las BLANDAS solo avisos.
    """
    errores = []

    # 1) campos presentes
    faltan = [c for c in CAMPOS if c not in datos]
    if faltan:
        errores.append("Faltan campos: %s" % ", ".join(faltan))
        # sin los campos base no tiene sentido seguir validando enums/reglas
        return ResultadoValidacion("INVALIDO", errores, [])

    status = _norm(datos.get("status"))
    risk = _norm(datos.get("risk"))
    summary = datos.get("summary")

    # 2) status ∈ enum
    if status not in STATUS_VALIDOS:
        errores.append(
            "status '%s' fuera del enum {%s}"
            % (datos.get("status"), ",".join(STATUS_VALIDOS))
        )

    # 3) risk ∈ enum
    if risk not in RISK_VALIDOS:
        errores.append(
            "risk '%s' fuera del enum {%s}"
            % (datos.get("risk"), ",".join(RISK_VALIDOS))
        )

    # 4) summary y next no vacíos (campos de texto obligatorios)
    if not _texto_no_vacio(summary):
        errores.append("'summary' no puede ir vacío")
    if not _texto_no_vacio(datos.get("next")):
        errores.append("'next' no puede ir vacío")

    # 5) REGLA DURA: status de corte => summary con sustancia
    #    (se muestra al humano cuando el flujo se detiene: ni vacío ni telegráfico)
    if status in STATUS_DE_CORTE:
        s = summary.strip() if isinstance(summary, str) else ""
        if len(s) < MIN_SUMMARY_CORTE:
            errores.append(
                "status=%s exige un summary que explique el motivo del corte "
                "(mínimo %d caracteres; se muestra al humano)"
                % (status, MIN_SUMMARY_CORTE)
            )

    if errores:
        return ResultadoValidacion("INVALIDO", errores, [])

    avisos = _avisos_coherencia(status, risk)
    return ResultadoValidacion(
        "VALIDO_CON_AVISOS" if avisos else "VALIDO", [], avisos
    )


# --- Avisos de coherencia: lo BLANDO (patrón recomendado, NO rompe) ---------

def _avisos_coherencia(status, risk):
    avisos = []
    if status == "BLOCKED" and risk != "CRITICAL":
        avisos.append("BLOCKED suele implicar risk=CRITICAL (definición de CRITICAL).")
    if status == "OK" and risk in ("HIGH", "CRITICAL"):
        avisos.append(
            "OK con HIGH/CRITICAL es incoherente: HIGH pide un WARN, CRITICAL un BLOCKED."
        )
    return avisos


# --- Helpers de normalización (stdlib) --------------------------------------

def _norm(v):
    """Normaliza un valor de enum a str mayúsculas sin espacios; None si no aplica."""
    if v is None:
        return None
    if not isinstance(v, str):
        return v
    return v.strip().upper()


def _texto_no_vacio(v):
    """True si v es un texto (o algo estringable) con contenido tras strip."""
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    # una lista vacía / dict vacío cuenta como vacío; lo demás con str() no vacío pasa
    if isinstance(v, (list, dict, tuple, set)):
        return len(v) > 0
    return bool(str(v).strip())


# --- Parseo del bloque markdown `## RESULTADO` (compatibilidad prosa) -------

def _parsear_bloque(texto):
    """Extrae el bloque `## RESULTADO` de un texto y devuelve un dict, o None."""
    m = re.search(r"##\s*RESULTADO\s*\n", texto, re.IGNORECASE)
    if not m:
        return None
    cuerpo = texto[m.end():]
    datos = {}
    for linea in cuerpo.splitlines():
        linea = linea.strip()
        if not linea:
            if datos:
                break  # línea en blanco tras los campos cierra el bloque
            continue
        if linea.startswith("#") or linea.startswith("```"):
            break
        mm = re.match(r"(\w+)\s*:\s*(.*)$", linea)
        if not mm:
            continue
        clave, valor = mm.group(1).lower(), mm.group(2).strip()
        if clave in CAMPOS:
            datos[clave] = valor
    return datos or None


# --- API pública ------------------------------------------------------------

def validar_envelope(envelope):
    """
    Valida un envelope YA parseado (dict). Punto de entrada canónico para el resto
    del kit (p.ej. un detector-wrapper o el verificador_minimo del gate).

    Devuelve ResultadoValidacion. RECHAZO (estado 'INVALIDO') = el envelope rompe
    el contrato; el detector que lo envuelva debe emitir un Veredicto ok=False.
    """
    if not isinstance(envelope, dict):
        return ResultadoValidacion(
            "INVALIDO",
            ["El envelope debe ser un objeto/dict; se recibió %s" % type(envelope).__name__],
            [],
        )
    return _validar_dict(envelope)


def validar(entrada):
    """
    Valida desde: dict (envelope), texto JSON, o texto con bloque `## RESULTADO`.
    Devuelve ResultadoValidacion.
    """
    if isinstance(entrada, dict):
        return _validar_dict(entrada)

    if isinstance(entrada, (bytes, bytearray)):
        entrada = entrada.decode("utf-8")

    if isinstance(entrada, str):
        texto = entrada.strip()
        # ¿es JSON?
        if texto[:1] in ("{", "["):
            try:
                datos = json.loads(texto)
            except (ValueError, TypeError):
                datos = None
            if isinstance(datos, dict):
                return _validar_dict(datos)
            if datos is not None:
                return ResultadoValidacion(
                    "INVALIDO", ["El JSON no es un objeto envelope."], []
                )
        # si no era JSON, probamos el bloque markdown
        datos = _parsear_bloque(entrada)
        if datos is None:
            return ResultadoValidacion(
                "SIN_BLOQUE",
                ["No se encontró un envelope: ni JSON de objeto ni bloque '## RESULTADO'."],
                [],
            )
        return _validar_dict(datos)

    return ResultadoValidacion(
        "INVALIDO", ["Tipo de entrada no soportado: %s" % type(entrada).__name__], []
    )


def validar_fichero(ruta):
    """Lee un fichero (.json o .md/.txt) o '-' (stdin) y lo valida. READ-ONLY."""
    if ruta == "-":
        texto = sys.stdin.read()
    else:
        with open(ruta, "r", encoding="utf-8") as f:
            texto = f.read()
    return validar(texto)


# --- Self-test (banco de no-regresión, stdlib) ------------------------------

# VÁLIDOS: envelopes que DEBEN validar.
_CASOS_VALIDOS = [
    {
        "status": "OK", "risk": "LOW", "skill_applied": "skill-alfa",
        "summary": "Conciliacion completada sin incidencias.",
        "artifacts": ["informe_alfa.md"], "next": "ninguno",
    },
    {
        "status": "BLOCKED", "risk": "CRITICAL", "skill_applied": True,
        "summary": "Descuadre de 12,50 en la linea 3. No insertar hasta revisar.",
        "artifacts": ["json_no_aprobado"], "next": "Revisar la linea 3 del asiento.",
    },
    {
        "status": "WARN", "risk": "MEDIUM", "skill_applied": "eda-analista",
        "summary": "EDA sobre 2.340 filas; 3 alertas de calidad.",
        "artifacts": ["distribuciones"], "next": "Limpiar duplicados antes de modelar.",
    },
]

# INVÁLIDOS: envelopes que DEBEN dar RECHAZO ('INVALIDO'). (nombre, envelope)
_CASOS_INVALIDOS = [
    ("status fuera de enum",
     {"status": "TERMINADO_OK", "risk": "LOW", "skill_applied": "x",
      "summary": "Todo bien y suficiente.", "artifacts": [], "next": "ninguno"}),
    ("BLOCKED con summary vacio",
     {"status": "BLOCKED", "risk": "HIGH", "skill_applied": "x",
      "summary": "", "artifacts": [], "next": "escalar"}),
    ("ERROR con summary telegrafico",
     {"status": "ERROR", "risk": "CRITICAL", "skill_applied": "x",
      "summary": "no", "artifacts": [], "next": "y"}),
    ("risk fuera de enum",
     {"status": "OK", "risk": "BAJO", "skill_applied": "x",
      "summary": "Todo correcto y suficiente.", "artifacts": [], "next": "ninguno"}),
    ("falta el campo next",
     {"status": "OK", "risk": "LOW", "skill_applied": "x",
      "summary": "Todo correcto y suficiente.", "artifacts": []}),
    ("next vacio",
     {"status": "OK", "risk": "LOW", "skill_applied": "x",
      "summary": "Todo correcto y suficiente.", "artifacts": [], "next": "  "}),
]

# CON AVISO: validan pero avisan de incoherencia blanda. (nombre, envelope)
_CASOS_CON_AVISO = [
    ("OK con risk HIGH",
     {"status": "OK", "risk": "HIGH", "skill_applied": "x",
      "summary": "El paso completo y hay base para seguir.", "artifacts": [], "next": "y"}),
    ("BLOCKED con risk LOW",
     {"status": "BLOCKED", "risk": "LOW", "skill_applied": "x",
      "summary": "Hay un problema que impide avanzar con seguridad ahora.",
      "artifacts": [], "next": "y"}),
]


def _self_test():
    fallos = 0

    print("== CASOS VALIDOS (deben VALIDAR) ==")
    for i, env in enumerate(_CASOS_VALIDOS, 1):
        r = validar_envelope(env)
        ok = r.ok and not r.errores
        print("  [%s] caso %d -> %s" % ("OK" if ok else "FAIL", i, r.estado))
        if not ok:
            fallos += 1
            for e in r.errores:
                print("        %s" % e)

    print("\n== CASOS INVALIDOS (deben dar RECHAZO/INVALIDO) ==")
    for nombre, env in _CASOS_INVALIDOS:
        r = validar_envelope(env)
        ok = r.estado == "INVALIDO"
        print("  [%s] %s -> %s" % ("OK" if ok else "FAIL", nombre, r.estado))
        if not ok:
            fallos += 1

    print("\n== CASOS CON AVISO (validan pero avisan) ==")
    for nombre, env in _CASOS_CON_AVISO:
        r = validar_envelope(env)
        ok = r.estado == "VALIDO_CON_AVISOS" and len(r.avisos) >= 1
        print("  [%s] %s -> %s (%d aviso/s)" % ("OK" if ok else "FAIL", nombre, r.estado, len(r.avisos)))
        if not ok:
            fallos += 1

    # Cobertura del parseo desde texto JSON y desde bloque markdown:
    print("\n== PARSEO desde texto ==")
    r_json = validar('{"status":"OK","risk":"LOW","skill_applied":"x",'
                     '"summary":"Todo correcto y suficiente.","artifacts":[],"next":"y"}')
    ok = r_json.ok
    print("  [%s] JSON string -> %s" % ("OK" if ok else "FAIL", r_json.estado))
    if not ok:
        fallos += 1
    r_md = validar("## RESULTADO\nstatus: OK\nrisk: LOW\nskill_applied: true\n"
                   "summary: Todo correcto y suficiente.\nartifacts: x\nnext: y")
    ok = r_md.ok
    print("  [%s] bloque markdown -> %s" % ("OK" if ok else "FAIL", r_md.estado))
    if not ok:
        fallos += 1

    print("\n%s" % ("=" * 50))
    if fallos == 0:
        print("SELF-TEST VERDE: 0 fallos.")
        return 0
    print("SELF-TEST ROJO: %d fallo/s." % fallos)
    return 1


def _informe_fichero(ruta):
    r = validar_fichero(ruta)
    print("ESTADO: %s" % r.estado)
    for e in r.errores:
        print("  ERROR: %s" % e)
    for a in r.avisos:
        print("  AVISO: %s" % a)
    return 0 if r.ok else 1


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 0
    if argv[1] == "--self-test":
        return _self_test()
    return _informe_fichero(argv[1])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
