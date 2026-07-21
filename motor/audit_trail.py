#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
motor/audit_trail.py — audit trail encadenado por hash (tamper-evident), FASE 1.

Implementa el mecanismo del SPEC (SPEC_Audit_Trail_Encadenado_DRAFT_06072026.md):
un log APPEND-ONLY donde cada entrada incorpora la huella (SHA-256) de la anterior
(hash chain). Cualquier alteración, reordenación, inserción o hueco de secuencia
rompe la recomputación desde ese punto y se LOCALIZA de forma determinista, sin LLM.

STDLIB PURA: `hashlib`, `json`. Cero red, cero BD, cero PyYAML en este módulo.

Partición READ-ONLY (SPEC §1): este módulo tiene UNA sola función que escribe
(`anexar`, OPT-IN, append-only, jamás en el corpus del cliente ni con expanduser);
`huella`, `cargar` y `verificar_cadena` son READ-ONLY. El detector `audit_chain`
solo llama a las tres READ-ONLY, así que el invariante de venta (read-only sobre el
corpus del cliente) queda intacto.

NO es "firmado": un hash chain prueba integridad y orden, no identidad ni cubre el
truncamiento de la cola (límite conocido §5.2; lo cubre el checkpoint de fase 2).
"""

import hashlib
import json
from pathlib import Path

from motor.veredicto import Veredicto


# ===========================================================================
# HUELLA — algoritmo canónico y determinista (SPEC §2.1)
# ===========================================================================
def _cadena_canonica(seq, datado, snapshot, prev):
    """Serialización canónica JSON de los 4 campos que entran en la huella (§2.1).

    sort_keys=True, sin espacios, ensure_ascii=False. La `huella` NO entra en su
    propio cálculo. DEBE coincidir byte a byte con la del generador de fixtures
    (gate/generar_fixtures_audit.py) — es el "método 2" del hash: dos
    implementaciones independientes de la MISMA receta que convergen.
    """
    return json.dumps(
        {"seq": seq, "datado": datado, "snapshot": snapshot, "prev": prev},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )


def huella(seq, datado, snapshot, prev):
    """SHA-256 hex en MAYÚSCULAS de la cadena canónica §2.1 (64 hex)."""
    cadena = _cadena_canonica(seq, datado, snapshot, prev)
    return hashlib.sha256(cadena.encode("utf-8")).hexdigest().upper()


# ===========================================================================
# ANEXAR — la ÚNICA función que ESCRIBE (opt-in, append-only, almacén del kit)
# ===========================================================================
def anexar(trail_path, snapshot_normalizado, datado):
    """OPT-IN, ESCRIBE. Añade una entrada al trail y devuelve la entrada creada.

    - Lee la última entrada del trail: `prev` := su huella ("" si el trail no existe
      o está vacío -> génesis); `seq` := ultima.seq + 1 (0 en génesis).
    - Compone la entrada, calcula su huella (§2.1) y AÑADE una línea JSONL.
    - APPEND-ONLY: nunca reescribe líneas previas.

    `trail_path` se usa TAL CUAL lo pasa el llamador (almacén propio del kit, ruta
    inyectada por config): NUNCA expanduser, nunca ruta del corpus del cliente.
    """
    ruta = Path(trail_path)
    entradas = []
    if ruta.exists():
        entradas = cargar(ruta.read_text(encoding="utf-8"))

    if entradas:
        ultima = entradas[-1]
        seq = int(ultima["seq"]) + 1
        prev = ultima["huella"]
    else:
        seq = 0
        prev = ""

    h = huella(seq, datado, snapshot_normalizado, prev)
    entrada = {
        "seq": seq,
        "datado": datado,
        "snapshot": snapshot_normalizado,
        "prev": prev,
        "huella": h,
    }

    # Append-only: una línea JSONL nueva, sin tocar las previas. Claves ordenadas
    # para que el fichero sea estable byte a byte (mismo criterio que el generador).
    linea = json.dumps(entrada, sort_keys=True, ensure_ascii=False)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("a", encoding="utf-8") as f:
        f.write(linea + "\n")
    return entrada


# Clave centinela: marca una línea del trail que NO es JSON válido. `cargar` NO revienta
# ante una línea ilegible (eso subía como traceback no capturado hasta el gate — bug H1 del
# barrido 06/07); tampoco la SALTA en silencio (saltarla escondería una manipulación = falso
# SANO, PEOR que reventar). La marca con esta entrada centinela y `verificar_cadena` la
# convierte en un Veredicto INV-AUDIT-ILEGIBLE con forma de contrato. La clave lleva doble
# guion bajo para no colisionar con ningún campo real de una entrada (§2 son seq/datado/
# snapshot/prev/huella), así una entrada legítima nunca se confunde con el centinela.
_CLAVE_ILEGIBLE = "__ilegible__"


# ===========================================================================
# CARGAR — READ-ONLY, recibe el TEXTO del trail (resuelve AMB-2)
# ===========================================================================
def cargar(texto_jsonl):
    """READ-ONLY. Recibe el CONTENIDO del trail (no una ruta) y devuelve las entradas
    en orden. AMB-2: el detector lee el fichero con `ctx.read_text(...)` y pasa el
    TEXTO ya leído — así la lectura queda centralizada en los helpers read-only del
    ctx (§5). Texto vacío / solo blancos -> [] (trail vacío).

    ROBUSTEZ (bug H1): una línea que NO es JSON válido NO revienta aquí. Se captura el
    `JSONDecodeError` y se emite una entrada CENTINELA (`{_CLAVE_ILEGIBLE: True, ...}`)
    con el número de línea (1-based) y un extracto del texto. `verificar_cadena` la
    traduce a un Veredicto INV-AUDIT-ILEGIBLE (ENFERMO). Ni traceback ni salto silencioso:
    un trail que no se puede leer debe dar ENFERMO con forma de contrato, no petar ni colar
    un falso SANO."""
    entradas = []
    for numero, linea in enumerate(("" + (texto_jsonl or "")).splitlines(), start=1):
        if not linea.strip():
            continue
        try:
            entradas.append(json.loads(linea))
        except (json.JSONDecodeError, ValueError) as exc:
            # No se puede parsear -> centinela con la localización (nº de línea 1-based) y un
            # extracto acotado del texto ofensivo (sin volcar líneas enormes al detalle).
            entradas.append({
                _CLAVE_ILEGIBLE: True,
                "linea": numero,
                "texto": linea.strip()[:80],
                "error": str(exc),
            })
    return entradas


# ===========================================================================
# VERIFICAR_CADENA — READ-ONLY, determinista, O(n): génesis -> cola
# ===========================================================================
def verificar_cadena(entradas):
    """Recorre el trail génesis -> cola y devuelve list[Veredicto]. READ-ONLY, O(n).

    Comprueba, por cada entrada en su posición i:
      · INV-AUDIT-SECUENCIA : seq contiguo desde 0 (la posición i debe declarar seq=i).
      · INV-AUDIT-CADENA    : huella(entrada) recomputada == la almacenada.
      · INV-AUDIT-ENLACE    : entrada[k].prev == huella real de entrada[k-1]
                              (génesis: prev == "").

    Una sola manipulación suele romper MÁS de un invariante a la vez (AMB-1 de la suite
    roja: alterar un snapshot rompe CADENA y de rebote ENLACE; reordenar rompe SECUENCIA
    y ENLACE). Por eso se ACUMULA el PRIMER punto de rotura de CADA invariante (no se
    detiene al primer defecto global): así el detector reporta el defecto que su
    `esperado.txt` ancla aunque no sea el primero en el recorrido, y el `detalle` de cada
    uno LOCALIZA su posición (índice/seq) — la localización exacta que pide el SPEC §4.

    Se reporta como MUCHO un Veredicto por invariante (el de su primer punto de rotura),
    en orden canónico CADENA, ENLACE, SECUENCIA. Trail vacío -> [] (nada que reportar).
    No decide severidad (la inyecta el runner desde invariantes.yaml).

    ILEGIBLE (bug H1): si `cargar` marcó alguna línea como no-JSON (entrada centinela), el
    trail NO se puede verificar de forma fiable -> se emite SOLO INV-AUDIT-ILEGIBLE (ENFERMO),
    localizando la PRIMERA línea ilegible, y se devuelve sin intentar hashear el resto (una
    huella sobre datos que no se pudieron parsear sería basura). Ni traceback ni salto
    silencioso: un fichero ilegible da ENFERMO con forma de contrato.
    """
    if not entradas:
        return []

    # ILEGIBLE primero: si hay una línea que `cargar` no pudo parsear, el trail es ilegible.
    for e in entradas:
        if isinstance(e, dict) and e.get(_CLAVE_ILEGIBLE):
            numero = e.get("linea")
            extracto = e.get("texto", "")
            detalle = ("la línea %r del trail no es JSON válido (%s): trail ILEGIBLE, no se "
                       "puede verificar la cadena. Extracto: %r. Un audit trail no debe "
                       "reventar ni saltar en silencio ante un fichero corrupto"
                       % (numero, e.get("error", "parseo"), extracto))
            return [Veredicto(
                "INV-AUDIT-ILEGIBLE", False, "trail_legible_como_JSONL",
                "linea_%s_ilegible" % numero, detalle)]

    fallo_cadena = None
    fallo_enlace = None
    fallo_secuencia = None
    prev_esperado = ""          # el génesis debe llevar prev=""

    for i, e in enumerate(entradas):
        seq = e.get("seq")
        datado = e.get("datado")
        snapshot = e.get("snapshot")
        prev = e.get("prev")
        huella_guardada = e.get("huella")

        huella_real = huella(seq, datado, snapshot, prev)

        # CADENA — la huella recomputada debe casar con la almacenada.
        if fallo_cadena is None and huella_real != huella_guardada:
            detalle = ("cadena rota en la posición %d (seq declarado=%r): la huella "
                       "recomputada no casa con la almacenada -> contenido alterado "
                       "sin recalcular la huella" % (i, seq))
            fallo_cadena = Veredicto(
                "INV-AUDIT-CADENA", False, "huella_recomputada==almacenada",
                "huella_divergente_en_posicion_%d" % i, detalle)

        # ENLACE — el prev debe apuntar a la huella real de la entrada anterior.
        if fallo_enlace is None and prev != prev_esperado:
            detalle = ("enlace roto en la posición %d (seq declarado=%r): su prev no "
                       "casa con la huella real de la entrada anterior (reordenación o "
                       "enlace manipulado)" % (i, seq))
            fallo_enlace = Veredicto(
                "INV-AUDIT-ENLACE", False, "prev==huella_de_la_anterior",
                "enlace_divergente_en_posicion_%d" % i, detalle)

        # SECUENCIA — la posición i del fichero debe declarar seq == i.
        if fallo_secuencia is None and seq != i:
            detalle = ("secuencia rota en la posición %d: se esperaba seq=%d y la "
                       "entrada declara seq=%r (hueco, salto o reordenación)"
                       % (i, i, seq))
            fallo_secuencia = Veredicto(
                "INV-AUDIT-SECUENCIA", False, "seq_contiguo_desde_0",
                "seq=%r_en_posicion_%d" % (seq, i), detalle)

        # avanza: la siguiente entrada debe encadenar con la huella REAL de esta.
        prev_esperado = huella_real

    # Orden canónico de emisión (CADENA, ENLACE, SECUENCIA). Cadena íntegra -> [].
    return [v for v in (fallo_cadena, fallo_enlace, fallo_secuencia) if v is not None]
