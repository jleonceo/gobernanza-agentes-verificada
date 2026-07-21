#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
gate_routing.py — Detector de routing (STANDALONE, des-acoplado).
=================================================================

EXTRAÍDO del inspector de routing original y DES-ACOPLADO del ecosistema:
NINGUNA ruta, nombre de fichero ni umbral vive en este módulo. Todo llega por `ctx`
(root inyectada + config compilada por el cargador de config). No se resuelve el HOME
del usuario, no hay rutas absolutas literales, no hay nombre de registro literal, ni
lista de skills exentas cableada. Cierra los huecos #1 y #5 del SPEC.

CONTRATO (CONTRATO_DETECTOR.md): `run(ctx) -> list[Veredicto]`.
- READ-ONLY absoluto. Nunca imprime. Nunca escribe. Devuelve SIEMPRE una lista.
- CERO patrón de parseo hardcodeado: todo regex llega de `ctx.conventions`.

INVARIANTES QUE EMITE
---------------------
· INV-R1 (cobertura, DURO): toda skill con descriptor está listada en el registro de
  routing (salvo las exentas). Es el fallo del 24/06: skill invisible al router.
· INV-R4 (colisiones, BLANDO->en el kit se reporta como defecto): pares de skills
  auto-invocables con similitud Jaccard de sus descripciones por encima del umbral
  (ctx.umbrales). El router no puede desambiguar descripciones casi idénticas.

INV-R1 es el invariante DECLARADO en invariantes.yaml para este detector (cobertura-motor).
INV-R4 se emite SOLO cuando hay colisión (fixtures rotas 02); sobre el corpus limpio no se
emite, de modo que el conjunto de ids ejecutados por el registro coincide con lo declarado.
"""

import re
from pathlib import Path

from motor.veredicto import Veredicto
from motor.runner import registrar


# --- Acceso resiliente a la config (dict o objeto), sin literales de parseo ---
def _get(obj, key, default=None):
    """Lee `key` de `obj` tanto si expone atributos como si es un dict."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _pat(value):
    """Devuelve un re.Pattern a partir de un valor de config.
    Si ya viene compilado (config_loader lo compiló), se usa tal cual; si viene como
    str (patrón declarado en YAML, NO un literal de este módulo), se compila. En ningún
    caso hay un patrón de parseo escrito en este fichero."""
    if value is None:
        return None
    if isinstance(value, re.Pattern):
        return value
    return re.compile(value)


def _conv(ctx):
    return _get(ctx, "conventions")


def _routing_paths(ctx):
    """routing_paths.yaml inyectado en ctx. Rutas RELATIVAS a ctx.root."""
    rp = _get(ctx, "routing_paths")
    if rp is None:
        # el loader puede exponer toda la config bajo ctx.config
        cfg = _get(ctx, "config")
        rp = _get(cfg, "routing_paths")
    return rp or {}


def _root(ctx):
    return Path(_get(ctx, "root"))


# --- Lectura de metadatos de un descriptor de skill (frontmatter por config) ---
def _leer_meta(ctx, path, name_re, delim):
    text = ctx.read_text(path)
    folder = Path(path).parent.name
    name = folder
    # aísla el bloque frontmatter delimitado (delim viene de config)
    lines = text.splitlines()
    block = ""
    if lines and lines[0].strip() == delim:
        buf = []
        for ln in lines[1:]:
            if ln.strip() == delim:
                break
            buf.append(ln)
        block = "\n".join(buf)
    if block and name_re is not None:
        m = name_re.search(block)
        if m:
            name = _grupo_nombre(m, folder)
    # descripción: primera línea 'description:' del bloque frontmatter.
    desc = ""
    for ln in block.splitlines():
        s = ln.strip()
        low = s.lower()
        if low.startswith("description:"):
            desc = s.split(":", 1)[1].strip().strip('"').strip("'")
            break
    return {"name": name or folder, "desc": desc}


def _grupo_nombre(m, fallback):
    """Extrae el nombre del match: grupo con nombre 'name' si existe, si no el grupo 1."""
    try:
        val = m.groupdict().get("name")
        if val:
            return val.strip()
    except (IndexError, TypeError):
        pass
    if m.groups():
        return (m.group(1) or fallback).strip()
    return fallback


def _skills(ctx):
    """Descriptores de skill del corpus, en orden canónico. Cada uno: (path, meta)."""
    rp = _routing_paths(ctx)
    skills_dir = _get(rp, "skills_dir")
    descriptor = _get(rp, "skill_descriptor")
    if skills_dir is None or descriptor is None:
        return []
    conv = _conv(ctx)
    fm = _get(conv, "frontmatter")
    delim = _get(fm, "delimiter")
    name_re = _pat(_get(fm, "name_regex"))
    glob = "*/" + descriptor
    out = []
    for p in ctx.iter_files(skills_dir, glob):
        out.append((p, _leer_meta(ctx, p, name_re, delim)))
    return out


def _nombres_en_registro(ctx):
    """Nombres de skill listados en el registro de routing (una fila = una skill)."""
    rp = _routing_paths(ctx)
    registro_rel = _get(rp, "registro_path")
    if registro_rel is None:
        return set(), False
    root = _root(ctx)
    registro = root / registro_rel
    if not registro.exists():
        return set(), False
    text = ctx.read_text(registro)
    conv = _conv(ctx)
    rr = _get(conv, "routing_registry")
    entry_re = _pat(_get(rr, "entry_regex"))
    names = set()
    for ln in text.splitlines():
        m = entry_re.search(ln) if entry_re else None
        if m:
            nombre = _grupo_nombre(m, "")
            if nombre:
                names.add(nombre)
    return names, True


# --- Tokenización + Jaccard para INV-R4 (todo de config, sin literales) -------
def _token_set(ctx, texto):
    conv = _conv(ctx)
    tk = _get(conv, "tokenizer")
    word_re = _pat(_get(tk, "word_regex"))
    min_len = int(_get(tk, "min_len", 1))
    stop = set(_get(tk, "stopwords", []) or [])
    ngrams = int(_get(tk, "ngrams", 1))
    if word_re is None:
        return set()
    pal = [w for w in word_re.findall((texto or "").lower())
           if len(w) >= min_len and w not in stop]
    toks = set(pal)
    if ngrams >= 2:
        toks |= set(zip(pal, pal[1:]))
    return toks


def _jaccard(a, b):
    return len(a & b) / len(a | b) if (a and b) else 0.0


def _umbral_jaccard(ctx):
    """Umbral Jaccard de colision (INV-R4), SIN default castrante.

    DEFECTO 1 (auditoria 06/07/2026): antes caia a `jaccard_warn=1.0` si la clave faltaba
    -> INV-R4 se desactivaba en silencio (solo colisionaban descripciones IDENTICAS). El
    default silencioso se ha ELIMINADO: la clave la GARANTIZA config_loader.validar_umbrales_routing
    (FAIL-FAST antes de que corra ningun detector). Si un caller construye el ctx saltandose
    el loader y la clave falta, es preferible un KeyError RUIDOSO (contrato roto) a un umbral
    castrado que finge que no hay colisiones."""
    um = _get(ctx, "umbrales") or {}
    routing = _get(um, "routing") or {}
    valor = _get(routing, "jaccard_warn")
    if valor is None:
        raise KeyError(
            "umbrales.routing.jaccard_warn ausente en ctx: config_loader.validar_umbrales_routing "
            "debe garantizarla (no se aplica default silencioso: castraria INV-R4)."
        )
    return float(valor)


# --- INV-R1: cobertura --------------------------------------------------------
def _inv_r1(ctx, skills):
    exentas = set(_get(ctx, "exentas") or [])
    vivas = {meta["name"] for _, meta in skills if meta["name"] not in exentas}

    # N/A-safe: si el corpus no tiene NINGUNA skill con descriptor, no hay nada que pueda
    # quedar invisible al routing -> INV-R1 no aplica y no inventa un fallo (mismo criterio
    # "degradar con gracia" del origen). El invariante solo puede FALLAR si hay skills que
    # cubrir. Esto evita falsos rojos en fixtures centradas en otro detector.
    if not vivas:
        return Veredicto("INV-R1", True, "sin_skills_invisibles", "sin_skills_que_cubrir",
                         "el corpus no declara ninguna skill: nada que pueda ser invisible")

    reg_names, hay_registro = _nombres_en_registro(ctx)
    if not hay_registro:
        return Veredicto("INV-R1", False, "sin_skills_invisibles", "registro_ausente",
                         "hay skills con descriptor pero no se encontró el registro de "
                         "routing: todas serían invisibles")
    faltan = sorted(vivas - reg_names)
    ok = not faltan
    esperado = "sin_skills_invisibles"
    obtenido = ("sin_skills_invisibles" if ok else "invisibles:" + ",".join(faltan))
    detalle = ("todas las skills con descriptor están en el registro de routing" if ok
               else "skills con descriptor y ausentes del registro de routing: "
                    + ", ".join(faltan))
    return Veredicto("INV-R1", ok, esperado, obtenido, detalle)


# --- INV-R4: colisiones -------------------------------------------------------
def _inv_r4(ctx, skills):
    umbral = _umbral_jaccard(ctx)
    auto = [(meta["name"], _token_set(ctx, meta["desc"] or meta["name"]))
            for _, meta in skills]
    pares = []
    for i in range(len(auto)):
        for j in range(i + 1, len(auto)):
            sc = _jaccard(auto[i][1], auto[j][1])
            if sc >= umbral:
                pares.append((round(sc, 3), auto[i][0], auto[j][0]))
    pares.sort(reverse=True)
    ok = not pares
    esperado = "sin_colisiones_routing"
    obtenido = ("sin_colisiones_routing" if ok
                else "; ".join("%s<->%s(%.3f)" % (a, b, sc) for sc, a, b in pares))
    detalle = ("ningún par de descripciones supera el umbral Jaccard %.2f" % umbral if ok
               else "colisión Jaccard (>= %.2f) entre: %s"
                    % (umbral, "; ".join("%s y %s" % (a, b) for _, a, b in pares)))
    return Veredicto("INV-R4", ok, esperado, obtenido, detalle)


# --- Contrato del detector ----------------------------------------------------
@registrar("gate_routing")
def run(ctx):
    """Detector de routing. Devuelve list[Veredicto]. READ-ONLY, no imprime.

    Emite SIEMPRE INV-R1 (declarado en invariantes.yaml -> cobertura-motor).
    Emite INV-R4 SOLO cuando detecta al menos una colisión, de modo que sobre el
    corpus limpio el conjunto de ids ejecutados = {INV-R1} (coincide con lo declarado
    para este detector) y sobre la fixture rota de colisión aparece INV-R4 en FALLO."""
    skills = _skills(ctx)
    veredictos = [_inv_r1(ctx, skills)]
    r4 = _inv_r4(ctx, skills)
    if not r4.ok:
        veredictos.append(r4)
    return veredictos
