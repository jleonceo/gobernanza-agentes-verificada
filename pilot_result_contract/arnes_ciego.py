# -*- coding: utf-8 -*-
"""
arnes_ciego.py — ARNÉS CIEGO de no-regresión del esquema tipado del envelope.

QUÉ HACE: toma los bloques `## RESULTADO` en prosa del corpus (subdir casos_reales/),
los parsea con el MISMO parser de bloques que usa el validador determinista vigente
(evals/result_contract.py:parsear_bloque), y comprueba que el ESQUEMA TIPADO
(envelope_schema.EnvelopeResultContract) ACEPTA los válidos y RECHAZA los malformados.

CIEGO: el veredicto esperado NO se lee del fichero ni de su nombre; se declara aparte
en ESPERADO (abajo). El arnés compara esperado vs. obtenido y solo da VERDE si TODOS
coinciden Y hay al menos un válido aceptado y un malformado rechazado.

ANCLAJE DEL PARSER: se importa parsear_bloque del validador vigente para que el arnés
mida el MISMO texto que el tirante determinista vería. Si ese import falla (rutas),
cae a una copia local idéntica (documentada como fallback).

READ-ONLY. No modifica ninguna skill/hook/settings. Determinista.

USO:
    python arnes_ciego.py
Exit 0 = gate VERDE; exit 1 = gate ROJO.
"""

import importlib.util
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_CASOS = os.path.join(_AQUI, "casos_reales")

# El esquema tipado vive junto a este fichero.
sys.path.insert(0, _AQUI)
from envelope_schema import EnvelopeResultContract  # noqa: E402

from pydantic import ValidationError  # noqa: E402


# --- Parser de bloques: el MISMO del validador determinista vigente ---------

def _cargar_parser_vigente():
    """Importa parsear_bloque de evals/result_contract.py para medir el mismo
    texto que el tirante determinista. Devuelve la función o None."""
    ruta = os.path.join(
        _AQUI, "..", "..", "..", "..", "evals", "result_contract.py"
    )
    ruta = os.path.normpath(ruta)
    if not os.path.exists(ruta):
        return None
    try:
        spec = importlib.util.spec_from_file_location("_rc_vigente", ruta)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.parsear_bloque
    except Exception:
        return None


def _parsear_bloque_fallback(texto):
    """Copia IDÉNTICA de evals/result_contract.py:parsear_bloque (fallback si el
    import falla). Extrae el bloque `## RESULTADO` a dict, o None."""
    import re
    CAMPOS = ("status", "risk", "skill_applied", "summary", "artifacts", "next")
    m = re.search(r"##\s*RESULTADO\s*\n", texto, re.IGNORECASE)
    if not m:
        return None
    cuerpo = texto[m.end():]
    datos = {}
    for linea in cuerpo.splitlines():
        linea = linea.strip()
        if not linea:
            if datos:
                break
            continue
        if linea.startswith("#") or linea.startswith("```"):
            break
        mm = re.match(r"(\w+)\s*:\s*(.*)$", linea)
        if not mm:
            continue
        clave, valor = mm.group(1).lower(), mm.group(2).strip()
        if clave == "skill_applied":
            if valor.lower() in ("true", "false"):
                datos[clave] = (valor.lower() == "true")
            else:
                datos[clave] = valor
        elif clave in CAMPOS:
            datos[clave] = valor
    return datos or None


_parser = _cargar_parser_vigente()
_FUENTE_PARSER = "evals/result_contract.py (import vigente)"
if _parser is None:
    _parser = _parsear_bloque_fallback
    _FUENTE_PARSER = "fallback local idéntico"


# --- Veredicto esperado, declarado CIEGO (no leído del fichero) -------------
#   ACEPTA  = el esquema tipado debe validar el envelope
#   RECHAZA = el esquema tipado debe rechazarlo (o no haber bloque parseable)

ESPERADO = {
    # Válidos reales del proyecto (verbatim de sims / RAG golden).
    "real_01_audiencias_prevision_OK.md": "ACEPTA",
    "real_02_marketer_landing_BLOCKED.md": "ACEPTA",
    "real_03_marketer_hero_WARN.md": "ACEPTA",
    "real_04_audiencias_atribucion_WARN_HIGH.md": "ACEPTA",
    "real_05_extractor_factura_OK.md": "ACEPTA",
    # Malformados fabricados a propósito.
    "malformado_01_enum_inventado.md": "RECHAZA",          # status 'Bloqueado' no-enum
    "malformado_02_falta_next.md": "RECHAZA",              # falta campo obligatorio 'next'
    "malformado_03_blocked_summary_telegrafico.md": "RECHAZA",  # BLOCKED + summary 'no'
}


def _validar_con_esquema(datos):
    """Aplica el esquema tipado a un dict ya parseado. Devuelve (aceptado, motivo)."""
    if datos is None:
        return (False, "SIN_BLOQUE: no se encontró el bloque '## RESULTADO'")
    # Campos que faltan -> rechazo explícito (Pydantic ya lo haría, pero damos motivo).
    faltan = [c for c in ("status", "risk", "skill_applied", "summary", "artifacts", "next")
              if c not in datos]
    if faltan:
        return (False, "faltan campos: %s" % ", ".join(faltan))
    try:
        EnvelopeResultContract(**datos)
        return (True, "válido")
    except ValidationError as e:
        primer = e.errors()[0]
        campo = ".".join(str(p) for p in primer["loc"]) or "?"
        return (False, "%s: %s" % (campo, primer["msg"]))


def main():
    print("== ARNÉS CIEGO — esquema tipado del envelope (piloto Structured Outputs) ==")
    print("Parser de bloques: %s" % _FUENTE_PARSER)
    print("Corpus: %s\n" % _CASOS)

    fallos = 0
    aceptados_ok = 0        # válidos correctamente aceptados
    rechazados_ok = 0       # malformados correctamente rechazados

    for fichero, esperado in ESPERADO.items():
        ruta = os.path.join(_CASOS, fichero)
        with open(ruta, "r", encoding="utf-8") as f:
            texto = f.read()
        datos = _parser(texto)
        aceptado, motivo = _validar_con_esquema(datos)
        obtenido = "ACEPTA" if aceptado else "RECHAZA"
        coincide = (obtenido == esperado)
        marca = "OK" if coincide else "FAIL"
        print("  [%s] %-46s esperado=%s obtenido=%s" % (marca, fichero, esperado, obtenido))
        if not coincide:
            fallos += 1
            print("        motivo obtenido: %s" % motivo)
        else:
            if esperado == "ACEPTA":
                aceptados_ok += 1
            else:
                rechazados_ok += 1
                print("        (rechazo correcto) %s" % motivo)

    n_validos = sum(1 for v in ESPERADO.values() if v == "ACEPTA")
    n_malos = sum(1 for v in ESPERADO.values() if v == "RECHAZA")

    print("\n" + "=" * 60)
    print("Válidos aceptados:      %d/%d" % (aceptados_ok, n_validos))
    print("Malformados rechazados: %d/%d" % (rechazados_ok, n_malos))

    verde = (
        fallos == 0
        and aceptados_ok == n_validos and aceptados_ok >= 1
        and rechazados_ok == n_malos and rechazados_ok >= 1
    )
    if verde:
        print("GATE: VERDE — los válidos pasan Y los malformados se rechazan.")
        return 0
    print("GATE: ROJO — %d discrepancia(s) esperado/obtenido." % fallos)
    return 1


if __name__ == "__main__":
    sys.exit(main())
