#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
generar_fixtures_audit.py — GENERADOR de las fixtures del audit trail (fase test-primero).

Escrito por VERIFICADOR-PROGRAMADOR el 06/07/2026, ANTES de que exista
`motor/audit_trail.py`. Este script implementa el algoritmo de huella del SPEC §2.1 por
un camino PROPIO E INDEPENDIENTE del que construirá el CONSTRUCTOR — es deliberadamente
mi "método 2" para el HASH: si el trail que yo genero da SANO contra el `audit_chain` del
constructor, es porque dos implementaciones distintas del mismo algoritmo convergen. Si
divergen, una de las dos está mal y el gate lo caza. NO importa nada de `motor/`.

Genera bajo `gate/`:
  fixtures/audit/integra/trail.jsonl            -> 3 entradas bien encadenadas (SANO)
  fixtures/audit_rotas/01_entrada_alterada/     -> snapshot intermedio alterado (INV-AUDIT-CADENA)
  fixtures/audit_rotas/02_enlace_roto/          -> prev[k] != huella real de k-1 (INV-AUDIT-ENLACE)
  fixtures/audit_rotas/03_reordenada/           -> dos entradas intercambiadas
  fixtures/audit_rotas/04_secuencia_hueco/      -> falta una entrada intermedia (INV-AUDIT-SECUENCIA)
  fixtures/audit_limite/05_cola_truncada/       -> se borra la cola (esperado SANO, LÍMITE §5.2)
cada fixture rota con su esperado.txt en el formato EXACTO de las existentes.

stdlib pura (hashlib, json). Rutas relativas al propio fichero; nunca expanduser.
Idempotente: reescribe los ficheros desde cero en cada pasada.
"""

import hashlib
import json
from pathlib import Path

# --- rutas: todo relativo a gate/ (padre de este fichero). NUNCA expanduser. -------------
RAIZ_GATE = Path(__file__).resolve().parent
DIR_INTEGRA = RAIZ_GATE / "fixtures" / "audit" / "integra"
DIR_ROTAS = RAIZ_GATE / "fixtures" / "audit_rotas"
DIR_LIMITE = RAIZ_GATE / "fixtures" / "audit_limite"
NOMBRE_TRAIL = "trail.jsonl"


# --- ALGORITMO DE HUELLA — implementación PROPIA del SPEC §2.1 (método 2) -----------------
def _cadena_canonica(seq, datado, snapshot, prev):
    """Serialización canónica JSON de los 4 campos que entran en la huella (SPEC §2.1).

    Orden por sort_keys, sin espacios, ensure_ascii=False. La `huella` NO entra en su
    propio cálculo. Es EXACTAMENTE la receta del SPEC, escrita aquí de forma independiente
    para no depender del código del constructor.
    """
    return json.dumps(
        {"seq": seq, "datado": datado, "snapshot": snapshot, "prev": prev},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )


def huella(seq, datado, snapshot, prev):
    """SHA-256 hex en MAYÚSCULAS de la cadena canónica (SPEC §2.1)."""
    cadena = _cadena_canonica(seq, datado, snapshot, prev)
    return hashlib.sha256(cadena.encode("utf-8")).hexdigest().upper()


def construir_entrada(seq, datado, snapshot, prev):
    """Compone una entrada completa del trail, con su huella ya calculada."""
    h = huella(seq, datado, snapshot, prev)
    return {"seq": seq, "datado": datado, "snapshot": snapshot, "prev": prev, "huella": h}


def construir_cadena(hechos):
    """Encadena una lista de (datado, snapshot) en un trail BIEN formado.

    seq contiguo desde 0; génesis con prev="". Cada prev = huella de la entrada anterior.
    Devuelve list[dict] lista para serializar a JSONL.
    """
    entradas = []
    prev = ""
    for i, (datado, snapshot) in enumerate(hechos):
        entrada = construir_entrada(i, datado, snapshot, prev)
        entradas.append(entrada)
        prev = entrada["huella"]
    return entradas


# --- serialización JSONL: una entrada por línea, claves ordenadas ------------------------
def _volcar_jsonl(entradas):
    """Serializa la lista de entradas a texto JSONL (una por línea, sin \\n final extra).

    sort_keys=True para que el fichero sea estable byte a byte entre pasadas. `ensure_ascii`
    False para no ensuciar acentos del snapshot. NOTA: el JSONL almacena las 5 claves
    (incluida `huella`); la canonicalización de la HUELLA solo usa 4 (§2.1) — son cosas
    distintas y deliberadas.
    """
    return "\n".join(
        json.dumps(e, sort_keys=True, ensure_ascii=False) for e in entradas
    ) + "\n"


def _escribir_trail(dir_fixture, entradas):
    dir_fixture.mkdir(parents=True, exist_ok=True)
    (dir_fixture / NOMBRE_TRAIL).write_text(_volcar_jsonl(entradas), encoding="utf-8")


def _escribir_esperado(dir_fixture, texto):
    (dir_fixture / "esperado.txt").write_text(texto, encoding="utf-8")


# --- los "hechos" a atestiguar: snapshots normalizados representativos --------------------
# El detector trata `snapshot` como un STRING OPACO (solo lo re-hashea; no lo re-parsea),
# así que basta con strings con la forma de snapshot_normalizado() (JSON canónico). Uso
# 3 estados de semáforo distintos para que las entradas no sean triviales ni idénticas.
def _snap(agregado, detectores):
    return json.dumps(
        {"agregado": agregado, "detectores": detectores, "veredictos": []},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )


HECHOS = [
    ("2026-07-06 09:00:00", _snap("SANO", {"gate_routing": "SANO", "lint_corpus": "SANO"})),
    ("2026-07-06 12:30:00", _snap("VIGILAR", {"gate_routing": "SANO", "lint_corpus": "VIGILAR"})),
    ("2026-07-06 18:15:00", _snap("SANO", {"gate_routing": "SANO", "lint_corpus": "SANO"})),
]


def _esperado(id_fallo, detalle):
    """Texto del esperado.txt en el formato EXACTO de las fixtures existentes."""
    return (
        "# Fixture ROTA audit — %s\n"
        "# Rojo esperado EXACTO (audit trail, SPEC §5.1 + §7):\n\n"
        "%s -> FALLO\n"
        "detector: audit_chain\n"
        "detalle_esperado: %s\n"
        "veredicto_detector: ENFERMO\n"
    ) % (id_fallo, id_fallo, detalle)


# ==========================================================================================
# GENERACIÓN
# ==========================================================================================
def generar():
    # -- ÍNTEGRA: cadena de 3 entradas bien encadenadas -> SANO ---------------------------
    integra = construir_cadena(HECHOS)
    _escribir_trail(DIR_INTEGRA, integra)

    # -- 01 ENTRADA ALTERADA: cambio el snapshot de la entrada intermedia (seq=1) SIN -----
    #    recalcular su huella. La huella almacenada ya no casa con el contenido -> CADENA.
    alterada = [dict(e) for e in construir_cadena(HECHOS)]
    alterada[1]["snapshot"] = _snap("ENFERMO", {"gate_routing": "ENFERMO", "lint_corpus": "SANO"})
    # (deliberadamente NO recalculo alterada[1]["huella"] ni las prev siguientes)
    _escribir_trail(DIR_ROTAS / "01_entrada_alterada", alterada)
    _escribir_esperado(
        DIR_ROTAS / "01_entrada_alterada",
        _esperado("INV-AUDIT-CADENA",
                  "snapshot de la entrada seq=1 alterado sin recalcular su huella"))

    # -- 02 ENLACE ROTO: la huella de cada entrada es CORRECTA para su propio contenido, --
    #    pero el prev de la entrada seq=2 no apunta a la huella real de seq=1. Recalculo la
    #    huella de la entrada tocada para que INV-AUDIT-CADENA NO se dispare y quede aislado
    #    el fallo de ENLACE (prev roto). Así la fixture prueba ENLACE, no CADENA.
    enlace = [dict(e) for e in construir_cadena(HECHOS)]
    prev_falso = "0" * 64  # 64 hex mayúsculas, forma válida pero no es la huella de seq=1
    enlace[2]["prev"] = prev_falso
    enlace[2]["huella"] = huella(enlace[2]["seq"], enlace[2]["datado"],
                                 enlace[2]["snapshot"], prev_falso)
    _escribir_trail(DIR_ROTAS / "02_enlace_roto", enlace)
    _escribir_esperado(
        DIR_ROTAS / "02_enlace_roto",
        _esperado("INV-AUDIT-ENLACE",
                  "prev de la entrada seq=2 no casa con la huella real de seq=1"))

    # -- 03 REORDENADA: intercambio físicamente las entradas seq=1 y seq=2 en el fichero. -
    #    Ambas conservan su seq/prev/huella originales; al leerlas en orden de fichero, la
    #    secuencia de seq va 0,2,1 (rompe SECUENCIA) y los prev dejan de encadenar (ENLACE).
    #    esperado ancla el id más robusto ante reordenación: INV-AUDIT-ENLACE.
    base = construir_cadena(HECHOS)
    reordenada = [base[0], base[2], base[1]]
    _escribir_trail(DIR_ROTAS / "03_reordenada", reordenada)
    _escribir_esperado(
        DIR_ROTAS / "03_reordenada",
        _esperado("INV-AUDIT-ENLACE",
                  "entradas seq=1 y seq=2 intercambiadas: el enlace prev deja de encadenar"))

    # -- 04 SECUENCIA HUECO: borro la entrada intermedia (seq=1). Quedan seq 0 y 2 -> salto.
    #    El prev de la que era seq=2 apunta a una huella que ya no está en el fichero (rompe
    #    también enlace), pero el defecto NOMBRADO y ancla del esperado es el hueco de seq.
    hueco = [base[0], base[2]]
    _escribir_trail(DIR_ROTAS / "04_secuencia_hueco", hueco)
    _escribir_esperado(
        DIR_ROTAS / "04_secuencia_hueco",
        _esperado("INV-AUDIT-SECUENCIA",
                  "falta la entrada seq=1: la secuencia salta de 0 a 2"))

    # -- 06 LÍNEA CORRUPTA (bug H1): parto de la cadena íntegra y CORROMPO físicamente la ---
    #    línea intermedia (seq=1) dejándola como texto NO-JSON. El resto de líneas quedan
    #    intactas. Antes esto reventaba `cargar` con un JSONDecodeError no capturado que subía
    #    como traceback hasta el gate; ahora debe degradar a INV-AUDIT-ILEGIBLE (ENFERMO) con
    #    forma de contrato. NO se salta la línea en silencio (sería un falso SANO, peor). La
    #    escribo a mano (no vía construir_entrada) porque el defecto es de PARSEO, no de hash.
    lineas_06 = _volcar_jsonl(construir_cadena(HECHOS)).splitlines()
    lineas_06[1] = '{"seq": 1, "datado": ROTO no-json, "snapshot":'   # línea 2 (1-based): ilegible
    (DIR_ROTAS / "06_linea_corrupta").mkdir(parents=True, exist_ok=True)
    (DIR_ROTAS / "06_linea_corrupta" / NOMBRE_TRAIL).write_text(
        "\n".join(lineas_06) + "\n", encoding="utf-8")
    _escribir_esperado(
        DIR_ROTAS / "06_linea_corrupta",
        _esperado("INV-AUDIT-ILEGIBLE",
                  "la linea 2 del trail no es JSON valido (trail ilegible: no se puede verificar)"))

    # -- 05 COLA TRUNCADA (LÍMITE, §5.2): borro las ÚLTIMAS entradas. La cadena restante --
    #    queda internamente VÁLIDA -> el hash chain lineal da SANO en FALSO. NO es un verde
    #    bueno: es el hueco conocido de fase 1 (lo cubre el checkpoint de fase 2). esperado
    #    = SANO, con NOTA explícita para no maquillarlo.
    truncada = construir_cadena(HECHOS)[:1]   # solo el génesis; se borró la cola
    _escribir_trail(DIR_LIMITE / "05_cola_truncada", truncada)
    _escribir_esperado_limite(DIR_LIMITE / "05_cola_truncada")

    return {
        "integra": DIR_INTEGRA / NOMBRE_TRAIL,
        "rotas": sorted((DIR_ROTAS).iterdir()),
        "limite": DIR_LIMITE / "05_cola_truncada" / NOMBRE_TRAIL,
    }


def _escribir_esperado_limite(dir_fixture):
    """esperado.txt del caso LÍMITE: SANO documentado (no rojo). Formato de línea
    `AGREGADO -> SANO` como el esperado.txt del corpus limpio, con NOTA del §5.2."""
    texto = (
        "# Fixture LÍMITE audit — 05_cola_truncada\n"
        "#\n"
        "# LÍMITE CONOCIDO (SPEC §5.2): se borraron las últimas entradas del trail. La\n"
        "# cadena que queda es internamente consistente, así que el hash chain lineal de\n"
        "# FASE 1 la da SANO. NO es un verde bueno: es el hueco que cubre el checkpoint\n"
        "# anclado de FASE 2 (§9). Cuando exista ese checkpoint, esta fixture pasará a ROJO.\n"
        "# Aquí sirve para DOCUMENTAR el límite sin maquillarlo, no para bendecir el truncamiento.\n"
        "#\n"
        "# Veredicto esperado del run (fase 1):\n"
        "AGREGADO -> SANO\n"
    )
    dir_fixture.mkdir(parents=True, exist_ok=True)
    (dir_fixture / "esperado.txt").write_text(texto, encoding="utf-8")


if __name__ == "__main__":
    resultado = generar()
    print("Fixtures de audit generadas (algoritmo §2.1 por camino propio, método 2):")
    print("  integra:", resultado["integra"])
    for r in resultado["rotas"]:
        print("  rota:   ", r)
    print("  limite: ", resultado["limite"])
