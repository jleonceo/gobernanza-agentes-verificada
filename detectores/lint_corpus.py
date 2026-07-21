#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
lint_corpus.py — Detector de fontanería del corpus (STANDALONE, des-acoplado).
==============================================================================

EXTRAÍDO del linter de corpus original y DES-ACOPLADO: ninguna ruta absoluta
(las de origen cableaban rutas del disco del usuario). Todo el corpus se resuelve
relativo a ctx.root, y TODO patrón de parseo (wikilink, mdlink, codespan, ruta
absoluta, sección RAG, fichero RAG, marca STALE) llega de ctx.conventions — CERO
literal de regex en este módulo.

CONTRATO (CONTRATO_DETECTOR.md): `run(ctx) -> list[Veredicto]`.
- READ-ONLY. No imprime. No escribe. Devuelve SIEMPRE una lista.

INVARIANTES QUE EMITE
--------------------
· LINT-WIKILINK (DURO, SIEMPRE): todo wikilink/puntero [[destino]] del corpus resuelve
  a un fichero existente dentro del corpus (una nota, una skill, un RAG o un fichero de
  infraestructura). Un [[destino]] sin fichero es un enlace roto -> FALLO. Es el
  invariante DECLARADO en invariantes.yaml para este detector (cobertura-motor): se
  emite SIEMPRE, también sobre el corpus limpio.

· LINT-MDLINK (DURO, ON-DEMAND): un enlace markdown [texto](destino.md) cuyo destino
  .md relativo no existe en el corpus es un enlace roto -> FALLO (severidad alta).
· LINT-ABSPATH (PORTABILIDAD, ON-DEMAND): una ruta absoluta (unidad Windows o raíz Unix)
  en el corpus es un defecto de portabilidad -> FALLO (severidad media -> VIGILAR).
· LINT-RAGSEC (DURO, ON-DEMAND): dentro de un SKILL.md, cada RAG (Fichero.md) nombrado
  bajo el heading canónico `## RAG QUE DEBES CARGAR` debe existir en el corpus -> si no,
  FALLO (severidad alta).

Los tres ON-DEMAND se emiten SOLO cuando detectan su defecto (idéntico patrón a INV-R4 en
gate_routing): sobre el corpus limpio el único id ejecutado por este detector sigue siendo
LINT-WIKILINK, de modo que la cobertura-motor ({ids declarados} == {ids ejecutados sobre
limpias}) NO se rompe. Su severidad se declara en invariantes.yaml -> severidades_on_demand.

No juzga si el CONTENIDO es verdad: solo la fontanería (que el enlace/destino exista).
"""

import re
from pathlib import Path

# BOOTSTRAP de sys.path (solo para el uso STANDALONE `python detectores/lint_corpus.py`):
# al invocar el módulo directamente, sys.path[0] es detectores/ y `import motor` no
# resuelve. Se inyecta la raíz del kit (padre de detectores/) ANTES de importar el motor.
# Cuando el módulo se importa por el runner del kit (`import detectores.lint_corpus`) la
# raíz YA está en sys.path (run_gate la inyecta): el `if not in` lo hace idempotente y sin
# efecto. READ-ONLY, sin efectos fuera del proceso.
import sys as _sys
_RAIZ_KIT = Path(__file__).resolve().parent.parent
if str(_RAIZ_KIT) not in _sys.path:
    _sys.path.insert(0, str(_RAIZ_KIT))

from motor.veredicto import Veredicto
from motor.runner import registrar


def _get(obj, key, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _pat(value):
    """Compila un valor de config a re.Pattern. No hay patrones literales en el módulo."""
    if value is None:
        return None
    if isinstance(value, re.Pattern):
        return value
    return re.compile(value)


def _conv(ctx):
    return _get(ctx, "conventions")


def _root(ctx):
    return Path(_get(ctx, "root"))


def _routing_paths(ctx):
    """routing_paths.yaml inyectado en ctx. Rutas RELATIVAS a ctx.root."""
    rp = _get(ctx, "routing_paths")
    if rp is None:
        cfg = _get(ctx, "config")
        rp = _get(cfg, "routing_paths")
    return rp or {}


def _strip_code(text, codespan_re):
    """Quita el código inline `...` para no confundir un enlace real con uno citado
    como ejemplo entre backticks. El patrón codespan llega de config."""
    if codespan_re is None:
        return text
    return codespan_re.sub(" ", text)


def _incluidos(ctx):
    """Conjunto de subárboles (nombres de carpeta de primer nivel, relativos a root) a los
    que se ACOTA el escaneo. Ausente o vacío -> None (se escanea TODO el corpus: el
    comportamiento por defecto, sin regresión). Clave OPCIONAL en routing_paths.

    Motivación (dogfooding 05/07): correr el gate sobre un corpus real cuyo root contiene
    subárboles VECINOS al de routing (memoria con forward-links colgantes intencionales,
    backups, plugins de terceros) producía falsos LINT-WIKILINK/MDLINK. Acotar a
    skills+rag lo resuelve. Se elige whitelist (incluir) sobre blacklist (excluir): es a
    prueba de ruido futuro — un subárbol nuevo bajo root no se cuela sin nombrarlo."""
    inc = _get(_routing_paths(ctx), "include_subtrees")
    if not inc:
        return None
    return {str(x).strip().strip("/").lower() for x in inc if str(x).strip()}


def _universo_md(ctx):
    """TODOS los .md bajo root (rglob + sorted), SIN acotar. Es el UNIVERSO de destinos
    resolubles — lo que un enlace puede apuntar legítimamente. Se mantiene amplio A
    PROPÓSITO aunque el escaneo de ficheros-a-auditar se acote (include_subtrees): un
    enlace de una skill a una nota de memoria (`[[setup-python-techacces]]`) es legítimo y
    su destino existe, aunque la memoria NO se audite. Acotar también el universo
    convertiría esos cross-refs válidos en falsos rotos (defecto detectado en el
    dogfooding del 05/07)."""
    return sorted(_root(ctx).rglob("*.md"))


def _iter_md(ctx):
    """Ficheros .md A AUDITAR, en orden canónico, ACOTADOS a include_subtrees si se declara.
    Distinto de _universo_md: aquí decidimos QUÉ ficheros revisamos (para no auditar los
    colgantes intencionales de la memoria); el universo de destinos válidos sigue siendo
    toda la raíz. Un fichero entra si el PRIMER componente de su ruta relativa a root está
    en el whitelist. Sin include_subtrees -> se auditan todos (== _universo_md)."""
    inc = _incluidos(ctx)
    if inc is None:
        return _universo_md(ctx)
    root = _root(ctx)
    out = []
    for p in _universo_md(ctx):
        partes = p.relative_to(root).parts
        if partes and partes[0].lower() in inc:
            out.append(p)
    return out


def _slugs_validos(ctx):
    """Conjunto de destinos que un wikilink puede resolver, construido del UNIVERSO del
    corpus (toda la raíz, sin acotar): stems de ficheros .md, más nombres de carpeta de
    skill. Todo en minúscula para comparar sin sensibilidad a mayúsculas. El universo NO se
    acota aunque el escaneo sí: un enlace a un subárbol no auditado (memoria) debe resolver."""
    descriptor = _get(_routing_paths(ctx), "skill_descriptor")   # p.ej. "SKILL.md"
    valid = set()
    for p in _universo_md(ctx):
        valid.add(p.stem.lower())
        # D-3: el nombre de la carpeta SOLO resuelve como destino cuando el fichero es el
        # DESCRIPTOR de una skill (SKILL.md). Antes se anadia por CADA .md -> el nombre de
        # cualquier carpeta con un .md valia como destino de wikilink (falso negativo).
        if descriptor and p.name == descriptor:
            valid.add(p.parent.name.lower())
    return valid


def _nombres_md(ctx):
    """Conjunto de nombres de fichero .md del UNIVERSO del corpus (basename, en minúscula)
    — para resolver mdlinks y RAGs nombrados por su fichero, no por su stem. Universo, no
    ámbito acotado: un destino en un subárbol no auditado sigue siendo un destino válido."""
    return {p.name.lower() for p in _universo_md(ctx)}


def _ficheros_con_wikilinks(ctx):
    """Ficheros .md A AUDITAR por wikilinks (orden canónico, ACOTADOS a include_subtrees si
    se declara). Aquí SÍ se acota: no queremos auditar los colgantes intencionales de la
    memoria, pero sus notas siguen siendo destinos válidos (ver _slugs_validos)."""
    return _iter_md(ctx)


# ===========================================================================
# LINT-WIKILINK (DURO, SIEMPRE) — el invariante declarado del detector
# ===========================================================================
def _lint_wikilink(ctx):
    conv = _conv(ctx)
    wl = _get(conv, "wikilinks")
    wikilink_re = _pat(_get(wl, "wikilink"))
    codespan_re = _pat(_get(wl, "codespan"))
    if wikilink_re is None:
        return Veredicto("LINT-WIKILINK", True, "sin_enlaces_rotos",
                         "sin_patron_wikilink",
                         "no hay patrón de wikilink en la config; nada que comprobar")

    valid = _slugs_validos(ctx)
    root = _root(ctx)
    rotos = []
    for p in _ficheros_con_wikilinks(ctx):
        texto = _strip_code(ctx.read_text(p), codespan_re)
        for m in wikilink_re.finditer(texto):
            target = _grupo_target(m).strip()
            if not target:
                continue
            if target.lower() not in valid:
                rel = p.relative_to(root).as_posix()
                rotos.append((rel, target))
    rotos = sorted(set(rotos))
    ok = not rotos
    esperado = "sin_enlaces_rotos"
    obtenido = ("sin_enlaces_rotos" if ok
                else "; ".join("%s->[[%s]]" % (f, t) for f, t in rotos))
    detalle = ("todos los wikilinks resuelven a un fichero del corpus" if ok
               else "wikilinks sin fichero destino en el corpus: "
                    + "; ".join("[[%s]] (en %s)" % (t, f) for f, t in rotos))
    return Veredicto("LINT-WIKILINK", ok, esperado, obtenido, detalle)


# ===========================================================================
# LINT-MDLINK (DURO, ON-DEMAND) — enlaces markdown [texto](destino.md) rotos
# ===========================================================================
def _es_destino_local_md(destino):
    """True si `destino` es un enlace markdown a un .md LOCAL que debe resolver.

    Se comprueban SOLO los enlaces a un fichero .md relativo del propio corpus. Se
    EXCLUYEN (no son fontanería del corpus): URLs (http/https/mailto), anclas puras
    (#seccion) y destinos que no terminan en .md (imágenes, otros recursos). Un ancla
    de fichero (`fichero.md#seccion`) se resuelve por su parte de fichero.
    """
    d = (destino or "").strip()
    if not d:
        return False, ""
    low = d.lower()
    if low.startswith(("http://", "https://", "mailto:", "ftp://")):
        return False, ""
    if d.startswith("#"):
        return False, ""
    # separa un posible ancla #seccion
    fichero = d.split("#", 1)[0].strip()
    if not fichero.lower().endswith(".md"):
        return False, ""
    return True, fichero


def _resuelve_md(destino_rel, contenedor, root_abs):
    """True si `destino_rel` (ruta de un mdlink) resuelve a un fichero real DENTRO de
    root, relativo al fichero contenedor o a root. Evita validar por basename global:
    un basename que existe en otra carpeta NO valida una ruta erronea (D-2)."""
    for base in (contenedor.parent, root_abs):
        try:
            cand = (base / destino_rel).resolve()
        except (OSError, RuntimeError, ValueError):
            continue
        if cand.is_file() and (cand == root_abs or root_abs in cand.parents):
            return True
    return False


def _lint_mdlink(ctx):
    """Comprueba que todo [texto](destino.md) local resuelva a un fichero .md del corpus.
    ON-DEMAND: devuelve Veredicto SOLO si hay al menos un mdlink roto (None si todo sano)."""
    conv = _conv(ctx)
    wl = _get(conv, "wikilinks")
    mdlink_re = _pat(_get(wl, "mdlink"))
    codespan_re = _pat(_get(wl, "codespan"))
    if mdlink_re is None:
        return None

    root = _root(ctx)
    root_abs = root.resolve()
    rotos = []
    for p in _ficheros_con_wikilinks(ctx):
        texto = _strip_code(ctx.read_text(p), codespan_re)
        for m in mdlink_re.finditer(texto):
            destino = _grupo_target(m).strip()
            es_local, fichero = _es_destino_local_md(destino)
            if not es_local:
                continue
            # D-2: el destino se resuelve RELATIVO al fichero que lo contiene (o a root
            # como respaldo), NO por basename global: un basename que existe en otra
            # carpeta no valida una ruta erronea. Debe ser fichero real DENTRO de root.
            if not _resuelve_md(fichero, p, root_abs):
                rel = p.relative_to(root).as_posix()
                rotos.append((rel, fichero))
    rotos = sorted(set(rotos))
    if not rotos:
        return None
    obtenido = "; ".join("%s->(%s)" % (f, t) for f, t in rotos)
    detalle = ("mdlinks sin fichero destino en el corpus: "
               + "; ".join("[texto](%s) (en %s)" % (t, f) for f, t in rotos))
    return Veredicto("LINT-MDLINK", False, "sin_mdlinks_rotos", obtenido, detalle)


# ===========================================================================
# LINT-ABSPATH (PORTABILIDAD, ON-DEMAND) — rutas absolutas en el corpus
# ===========================================================================
def _lint_abspath(ctx):
    """Marca rutas absolutas (C:\\... o /...) como defecto de portabilidad.
    ON-DEMAND: devuelve Veredicto SOLO si encuentra al menos una (None si ninguna).

    Se aplica LÍNEA A LÍNEA con el patrón `abspath` (anclado a `^`), tras quitar el
    código inline: una ruta absoluta citada entre backticks es un ejemplo, no un enlace."""
    conv = _conv(ctx)
    wl = _get(conv, "wikilinks")
    abspath_re = _pat(_get(wl, "abspath"))
    codespan_re = _pat(_get(wl, "codespan"))
    if abspath_re is None:
        return None

    root = _root(ctx)
    hallazgos = []
    for p in _ficheros_con_wikilinks(ctx):
        texto = _strip_code(ctx.read_text(p), codespan_re)
        for linea in texto.splitlines():
            s = linea.strip()
            if abspath_re.search(s):
                rel = p.relative_to(root).as_posix()
                hallazgos.append((rel, s[:80]))
    hallazgos = sorted(set(hallazgos))
    if not hallazgos:
        return None
    obtenido = "; ".join("%s: %s" % (f, s) for f, s in hallazgos)
    detalle = ("rutas absolutas detectadas (defecto de portabilidad): "
               + "; ".join("%r (en %s)" % (s, f) for f, s in hallazgos))
    return Veredicto("LINT-ABSPATH", False, "sin_rutas_absolutas", obtenido, detalle)


# ===========================================================================
# LINT-RAGSEC (DURO, ON-DEMAND) — RAGs nombrados en la sección RAG que no existen
# ===========================================================================
def _skill_descriptors(ctx):
    """Ficheros descriptores de skill (SKILL.md) del corpus, en orden canónico.

    Se localizan por la convención de routing_paths (skills_dir + skill_descriptor). Si el
    corpus no declara esas rutas, se degrada con gracia (lista vacía: nada que comprobar)."""
    rp = _routing_paths(ctx)
    skills_dir = _get(rp, "skills_dir")
    descriptor = _get(rp, "skill_descriptor")
    if not skills_dir or not descriptor:
        return []
    glob = "*/" + descriptor
    return list(ctx.iter_files(skills_dir, glob))


def _rags_declarados(ctx, texto):
    """Extrae los ficheros RAG (Fichero.md) nombrados bajo el heading `## RAG QUE DEBES
    CARGAR`. El heading y el patrón de fichero RAG llegan de ctx.conventions (sin literal).

    La sección va desde su heading hasta el siguiente heading de igual o menor nivel (o EOF).
    Dentro de ella, `markup.rag_file` extrae cada `Nombre.md`. Los code spans NO se quitan:
    en el corpus real los RAGs de la sección van entre backticks (`Guia.md`) y aun así deben
    resolver — es una lista de dependencias, no prosa donde un backtick signifique 'ejemplo'."""
    conv = _conv(ctx)
    rs = _get(conv, "rag_section")
    heading_re = _pat(_get(rs, "heading_regex"))
    mk = _get(conv, "markup")
    heading_generic_re = _pat(_get(mk, "heading"))
    rag_file_re = _pat(_get(mk, "rag_file"))
    if heading_re is None or heading_generic_re is None or rag_file_re is None:
        return []

    lineas = texto.splitlines()
    # localizar la línea del heading canónico
    idx_ini = None
    nivel_ini = None
    for i, ln in enumerate(lineas):
        if heading_re.search(ln):
            idx_ini = i
            hm = heading_generic_re.search(ln)
            nivel_ini = len(hm.group("hashes")) if hm else 2
            break
    if idx_ini is None:
        return []
    # recolectar hasta el próximo heading de nivel <= nivel_ini
    cuerpo = []
    for ln in lineas[idx_ini + 1:]:
        hm = heading_generic_re.search(ln)
        if hm and len(hm.group("hashes")) <= nivel_ini:
            break
        cuerpo.append(ln)
    rags = []
    for ln in cuerpo:
        for m in rag_file_re.finditer(ln):
            rags.append(m.group("rag"))
    # ordenar y de-duplicar preservando determinismo
    return sorted(set(rags))


def _lint_ragsec(ctx):
    """Comprueba que cada RAG nombrado en `## RAG QUE DEBES CARGAR` exista en el corpus.
    ON-DEMAND: devuelve Veredicto SOLO si hay al menos un RAG inexistente (None si todo sano)."""
    descriptores = _skill_descriptors(ctx)
    if not descriptores:
        return None
    nombres = _nombres_md(ctx)
    root = _root(ctx)
    rotos = []
    for p in descriptores:
        texto = ctx.read_text(p)
        for rag in _rags_declarados(ctx, texto):
            if rag.lower() not in nombres:
                rel = p.relative_to(root).as_posix()
                rotos.append((rel, rag))
    rotos = sorted(set(rotos))
    if not rotos:
        return None
    obtenido = "; ".join("%s->%s" % (f, r) for f, r in rotos)
    detalle = ("RAGs nombrados en la sección RAG sin fichero en el corpus: "
               + "; ".join("%s (en %s)" % (r, f) for f, r in rotos))
    return Veredicto("LINT-RAGSEC", False, "sin_rag_inexistente", obtenido, detalle)


def _grupo_target(m):
    try:
        val = m.groupdict().get("target")
        if val is not None:
            return val
    except (IndexError, TypeError):
        pass
    return m.group(1) if m.groups() else ""


@registrar("lint_corpus")
def run(ctx):
    """Detector de fontanería del corpus. Devuelve list[Veredicto]. READ-ONLY.

    Emite SIEMPRE LINT-WIKILINK (declarado en invariantes.yaml -> cobertura-motor).
    Emite LINT-MDLINK / LINT-ABSPATH / LINT-RAGSEC SOLO cuando detectan su defecto, de
    modo que sobre el corpus limpio el conjunto de ids ejecutados por este detector =
    {LINT-WIKILINK} y la cobertura-motor no se rompe."""
    veredictos = [_lint_wikilink(ctx)]
    for on_demand in (_lint_mdlink(ctx), _lint_abspath(ctx), _lint_ragsec(ctx)):
        if on_demand is not None:
            veredictos.append(on_demand)
    return veredictos


# ===========================================================================
# CLI STANDALONE: `python detectores/lint_corpus.py --root <ruta>`
# ===========================================================================
# Corre SOLO este detector (la fontanería del corpus: wikilinks/mdlinks/abspath/RAGsec)
# sobre una raíz ARBITRARIA, sin arrastrar el resto del gate. Es la interfaz de
# dogfooding "lintar un corpus a mano": misma raíz INYECTADA que promete install.md §1.5
# (Path(root).resolve(), NUNCA expanduser), mismo Ctx que el runner construye (config →
# conventions compiladas: CERO regex literal se añade aquí). READ-ONLY: solo imprime.
#
# NO altera el contrato del detector: run(ctx) queda intacto y es lo que el runner del
# kit ejecuta. Este bloque es un ENVOLTORIO de conveniencia, aislado bajo __main__.
def _main(argv=None):
    import argparse

    # BOOTSTRAP de sys.path: al invocar `python detectores/lint_corpus.py` directamente,
    # sys.path[0] es detectores/, no la raíz del kit, y `import motor` no resolvería.
    # Se inyecta la raíz del kit (padre de detectores/) igual que hace run_gate.py.
    import sys as _sys
    _raiz_kit = Path(__file__).resolve().parent.parent
    if str(_raiz_kit) not in _sys.path:
        _sys.path.insert(0, str(_raiz_kit))

    from motor.config_loader import cargar_config
    from motor.runner import Runner, REGISTRO
    from motor.veredicto import agregar

    ap = argparse.ArgumentParser(
        description="Linta la fontanería (wikilinks/mdlinks/rutas/RAGsec) de una raíz "
                    "de corpus arbitraria. READ-ONLY.")
    ap.add_argument("--root", required=True,
                    help="raíz del corpus a lintar. Se INYECTA (nunca expanduser).")
    ap.add_argument("--config", default=None,
                    help="carpeta config/ a usar (por defecto la del kit: <kit>/config).")
    args = ap.parse_args(argv)

    ruta = Path(args.root)
    if not ruta.exists():
        _sys.stderr.write("ROJO: la raíz de corpus no existe: %s\n" % ruta)
        return 2

    config_dir = Path(args.config) if args.config else (_raiz_kit / "config")
    config = cargar_config(config_dir)                 # FAIL-FAST si falta una clave

    # Construir el Ctx exactamente como el runner (conventions compiladas, sin literales)
    # y ejecutar SOLO este detector — no todo el registro.
    ctx = Runner(REGISTRO).construir_ctx(root=ruta, config=config)
    veredictos = run(ctx)

    severidades = {inv["id"]: inv.get("severidad")
                   for inv in config["invariantes"]["invariantes"]}
    on_demand = config["invariantes"].get("severidades_on_demand") or {}
    for _id, _sev in on_demand.items():
        severidades.setdefault(_id, _sev)
    agregado = agregar(veredictos, severidades)

    print("LINT_CORPUS %s -> %s" % (ctx.root, agregado))
    for v in veredictos:
        estado = "OK  " if v.ok else "FALLO"
        print("  [%s] %-14s %s" % (estado, v.id, v.detalle))

    # Exit 0 si SANO; != 0 si hay algún defecto (VIGILAR/ENFERMO), con los defectos a stderr.
    if agregado != "SANO":
        fallos = sorted(v.id for v in veredictos if not v.ok)
        _sys.stderr.write("DEFECTOS: " + ", ".join(fallos) + "\n")
        return 1
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main())
