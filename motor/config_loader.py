#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
motor/config_loader.py — carga de config VARIABLE, FAIL-FAST, sin expanduser.

MECANISMO OBLIGATORIO #1 del SPEC (CERO formato hardcodeado): TODO patrón de parseo
vive en config/corpus_conventions.yaml; este módulo los CARGA y los COMPILA para
inyectarlos en ctx.conventions. Ningún `re.compile` con literal vive en detectores/.

FAIL-FAST (endurecimiento §1): si falta un fichero o una clave requerida, aborta con
un ConfigError que NOMBRA la clave ausente. NUNCA aplica un default silencioso: un
default reintroduce el hardcodeo por la puerta de atrás y anula el pre-check grep-cero.

NUNCA expanduser / Path.home / os.environ['HOME'] / rutas absolutas literales: la raíz
del corpus llega INYECTADA por el runner; la config llega por una ruta pasada por el
llamador (el gate pasa la carpeta config/). Este módulo no descubre rutas por su cuenta.

Dependencia: PyYAML (única fuera de stdlib, declarada en el SPEC). READ-ONLY.
"""

import re
from pathlib import Path

try:
    import yaml
except ImportError as e:  # pragma: no cover - entorno sin PyYAML
    raise ImportError(
        "config_loader necesita PyYAML (la única dependencia del kit). "
        "Instalar: `pip install pyyaml` o `conda install pyyaml`."
    ) from e


class ConfigError(Exception):
    """Error de configuración FAIL-FAST: fichero o clave requerida ausente/malformada."""


# Los ficheros de config que el kit espera. Su STEM es la clave con la que quedan en
# el dict de config (config["invariantes"], config["umbrales"], ...).
#   - corpus_conventions: patrones de parseo (compilados a ctx.conventions).
#   - invariantes: los ids declarados (cobertura-motor).
#   - umbrales: tolerancias (Jaccard, STALE, presupuestos).
#   - exentas: nombres exentos de routing.
#   - routing_paths: dónde vive cada pieza del corpus (skills_dir, registro_path, ...).
#     Externaliza lo que el origen cableaba como expanduser('~/.claude/...'); el detector
#     lo lee de ctx.routing_paths y lo resuelve relativo a ctx.root (nunca expanduser).
FICHEROS_REQUERIDOS = (
    "corpus_conventions",
    "invariantes",
    "umbrales",
    "exentas",
    "routing_paths",
)

# Ficheros de config OPCIONALES: se cargan si el .yaml existe, pero su ausencia NO
# aborta por sí sola (un tercero puede no usar la feature). El fail-fast asociado es
# CONDICIONAL: solo si el detector que la consume está registrado (ver _exigir_audit_trail).
#   - audit_trail: ruta del trail encadenado (la consume detectores/audit_chain.py).
FICHEROS_OPCIONALES = (
    "audit_trail",
)


# ---------------------------------------------------------------------------
# Helpers de acceso FAIL-FAST (nombran la clave ausente; sin default silencioso)
# ---------------------------------------------------------------------------
def _requerir(d, clave, contexto):
    if not isinstance(d, dict) or clave not in d:
        raise ConfigError(
            "clave requerida ausente: '%s' en %s (config FAIL-FAST, sin default)."
            % (clave, contexto)
        )
    return d[clave]


def _compilar(patron, contexto):
    """Compila una regex de config con re.MULTILINE. Malformada -> ABORTA nombrando dónde.

    Se compila con MULTILINE DELIBERADAMENTE: todos los patrones de corpus_conventions
    son line-oriented (`^name:`, `^\\|` de fila de tabla, `^##` de heading, `^#{1,6}` de
    markup) y se aplican sobre el texto COMPLETO del fichero, no línea a línea. Sin
    MULTILINE el ancla `^` solo casaría el inicio del fichero y el frontmatter/registro
    (que viven mitad de fichero) nunca resolverían. Es una elección de convención, no un
    dogma: los patrones del yaml se escriben asumiéndola.
    """
    try:
        return re.compile(patron, re.MULTILINE)
    except re.error as e:
        raise ConfigError(
            "regex inválida en %s: %r -> %s (config FAIL-FAST)." % (contexto, patron, e)
        )


# ---------------------------------------------------------------------------
# Convenciones compiladas — lo que ctx.conventions expone (CONTRATO §4)
# ---------------------------------------------------------------------------
def compilar_conventions(raw):
    """Compila corpus_conventions.yaml a la MISMA forma ANIDADA del yaml, con cada
    patrón ya como re.Pattern (re.MULTILINE) y los escalares copiados tal cual.

    CONTRATO DE LECTURA (§4): los detectores leen ctx.conventions con acceso ANIDADO por
    las claves del yaml — conv['frontmatter']['name_regex'], conv['routing_registry']
    ['entry_regex'], conv['wikilinks']['wikilink'], conv['tokenizer']['word_regex'], ...
    Devolver la forma anidada (y NO un objeto de atributos planos) es lo que casa con ese
    contrato: un objeto plano dejaba a gate_routing y a lint_corpus SIN poder leer la
    config — gate_routing daba un falso ROJO (no parseaba el registro → toda skill parecía
    invisible) y lint_corpus un falso VERDE (no encontraba el patrón → no linteaba nada).

    FAIL-FAST: cualquier clave ausente aborta con ConfigError que la NOMBRA (sin default
    silencioso). Los patrones se compilan aquí una sola vez; el detector nunca los conoce
    como literales. `_pat()` en los detectores acepta el re.Pattern tal cual.
    """
    c = "corpus_conventions.yaml"

    fm = _requerir(raw, "frontmatter", c)
    rr = _requerir(raw, "routing_registry", c)
    wl = _requerir(raw, "wikilinks", c)
    rs = _requerir(raw, "rag_section", c)
    mk = _requerir(raw, "markup", c)
    tk = _requerir(raw, "tokenizer", c)

    return {
        "frontmatter": {
            "delimiter": _requerir(fm, "delimiter", c + ":frontmatter"),
            "name_regex": _compilar(
                _requerir(fm, "name_regex", c + ":frontmatter"), c + ":frontmatter.name_regex"),
        },
        "routing_registry": {
            "filename": _requerir(rr, "filename", c + ":routing_registry"),
            "entry_regex": _compilar(
                _requerir(rr, "entry_regex", c + ":routing_registry"),
                c + ":routing_registry.entry_regex"),
        },
        "wikilinks": {
            "wikilink": _compilar(_requerir(wl, "wikilink", c + ":wikilinks"), c + ":wikilinks.wikilink"),
            "mdlink": _compilar(_requerir(wl, "mdlink", c + ":wikilinks"), c + ":wikilinks.mdlink"),
            "codespan": _compilar(_requerir(wl, "codespan", c + ":wikilinks"), c + ":wikilinks.codespan"),
            "abspath": _compilar(_requerir(wl, "abspath", c + ":wikilinks"), c + ":wikilinks.abspath"),
        },
        "rag_section": {
            "heading_text": _requerir(rs, "heading_text", c + ":rag_section"),
            "heading_regex": _compilar(
                _requerir(rs, "heading_regex", c + ":rag_section"), c + ":rag_section.heading_regex"),
        },
        "markup": {
            "heading": _compilar(_requerir(mk, "heading", c + ":markup"), c + ":markup.heading"),
            "codespan": _compilar(_requerir(mk, "codespan", c + ":markup"), c + ":markup.codespan"),
            "rag_file": _compilar(_requerir(mk, "rag_file", c + ":markup"), c + ":markup.rag_file"),
        },
        "tokenizer": {
            "word_regex": _compilar(_requerir(tk, "word_regex", c + ":tokenizer"), c + ":tokenizer.word_regex"),
            "min_len": int(_requerir(tk, "min_len", c + ":tokenizer")),
            "stopwords": frozenset(_requerir(tk, "stopwords", c + ":tokenizer")),
            "ngrams": int(_requerir(tk, "ngrams", c + ":tokenizer")),
        },
        "infra_files": frozenset(_requerir(raw, "infra_files", c)),
        "stale_marker_regex": _compilar(
            _requerir(raw, "stale_marker_regex", c), c + ":stale_marker_regex"),
    }


# ---------------------------------------------------------------------------
# Carga de todos los YAML de una carpeta config/
# ---------------------------------------------------------------------------
def _audit_chain_registrado():
    """True si el detector `audit_chain` está en el REGISTRO global del runner.

    Import PEREZOSO de motor.runner (aquí dentro, no arriba) para evitar la circularidad
    config_loader <-> runner: runner importa config_loader al cargarse, así que
    config_loader no puede importar runner a nivel de módulo. Si el registro aún no se ha
    poblado (audit_chain no importado), devuelve False -> la config del trail no se exige.
    """
    try:
        from motor.runner import REGISTRO
    except ImportError:
        return False
    return "audit_chain" in REGISTRO


def validar_umbrales_routing(config):
    """FAIL-FAST de la clave `routing.jaccard_warn` (DEFECTO 1, auditoria 06/07/2026).

    Sin esta validacion, un umbrales.yaml SIN `routing.jaccard_warn` cargaba limpio y
    `gate_routing._umbral_jaccard` caia a un default 1.0 -> INV-R4 (colision de routing)
    quedaba DESACTIVADO EN SILENCIO (solo colisionaban descripciones IDENTICAS), sin
    ningun rojo. Un config incompleto debe dar ROJO EXPLICITO, no castrar la comprobacion
    (mismo criterio FAIL-FAST que ya se aplica a `invariantes` y a las conventions).

    Exige: umbrales.routing.jaccard_warn presente y un numero REAL en (0, 1]. Fuera de rango,
    no-numerico o BOOLEANO -> ConfigError que NOMBRA la clave. El bool se rechaza explicito
    (barrido adversarial 06/07): float(True)=1.0 se colaria en rango y castraria el check. Se
    separa en su propia funcion para que el banco de pruebas la ejerza sobre un dict ya cargado."""
    um = _requerir(config, "umbrales", "config (umbrales.yaml no cargado)")
    routing = _requerir(um, "routing", "umbrales.yaml")
    valor = _requerir(routing, "jaccard_warn", "umbrales.yaml:routing")
    # RECHAZO EXPLICITO de bool ANTES del float(): en Python `bool` es subclase de `int`, asi
    # que float(True)=1.0 y float(False)=0.0 NO lanzan. Un `jaccard_warn: true` (bool YAML) se
    # colaria como 1.0 en (0,1] y dejaria INV-R4 MUDO para colisiones parciales CON la clave
    # PRESENTE (misma clase de agujero que el default silencioso). Un umbral es numerico, no bool.
    if isinstance(valor, bool):
        raise ConfigError(
            "umbrales.yaml:routing.jaccard_warn debe ser numerico, no booleano (%r) "
            "(config FAIL-FAST: un bool se castraria a 1.0/0.0 y desactivaria INV-R4 en silencio)."
            % (valor,)
        )
    try:
        jw = float(valor)
    except (TypeError, ValueError):
        raise ConfigError(
            "umbrales.yaml:routing.jaccard_warn debe ser numerico, no %r "
            "(config FAIL-FAST: un umbral castrado desactiva INV-R4 en silencio)." % (valor,)
        )
    if not (0.0 < jw <= 1.0):
        raise ConfigError(
            "umbrales.yaml:routing.jaccard_warn=%r fuera de rango (0, 1] "
            "(config FAIL-FAST: un umbral <=0 o >1 castra la deteccion de colision)." % (jw,)
        )


def _exigir_audit_trail(config, base):
    """FAIL-FAST CONDICIONAL (SPEC §6): si `audit_chain` está registrado, exige
    audit_trail.yaml con una clave `trail_path`. Si el detector NO está registrado, no
    se exige nada (un tercero sin la feature no se rompe)."""
    if not _audit_chain_registrado():
        return
    if "audit_trail" not in config:
        raise ConfigError(
            "el detector 'audit_chain' está registrado pero falta %s "
            "(config FAIL-FAST: la feature audit trail exige su config)."
            % (base / "audit_trail.yaml")
        )
    _requerir(config["audit_trail"], "trail_path", "audit_trail.yaml")


def cargar_config(config_dir):
    """Carga los *.yaml de `config_dir` en un dict keyed por STEM del fichero.

    Devuelve p.ej. {"corpus_conventions": {...}, "invariantes": {...}, ...} tal
    cual (crudo). El runner es quien compila las conventions y construye el ctx.
    El gate accede a config["invariantes"]["invariantes"] (lista de invariantes).

    FAIL-FAST:
      - config_dir inexistente            -> ConfigError
      - falta un fichero requerido        -> ConfigError nombrándolo
      - YAML malformado o vacío           -> ConfigError nombrándolo

    NUNCA expanduser: `config_dir` se usa tal cual lo pasa el llamador.
    """
    base = Path(config_dir)
    if not base.is_dir():
        raise ConfigError(
            "carpeta de config inexistente: %s (config FAIL-FAST, sin descubrimiento "
            "por HOME/expanduser)." % base
        )

    config = {}
    for stem in FICHEROS_REQUERIDOS:
        ruta = base / (stem + ".yaml")
        if not ruta.is_file():
            raise ConfigError(
                "falta el fichero de config requerido: %s (config FAIL-FAST)." % ruta
            )
        try:
            datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            raise ConfigError("YAML malformado en %s: %s (config FAIL-FAST)." % (ruta, e))
        if datos is None:
            raise ConfigError("fichero de config vacío: %s (config FAIL-FAST)." % ruta)
        config[stem] = datos

    # Ficheros OPCIONALES: cargar si existen (misma validación de YAML malformado/vacío).
    for stem in FICHEROS_OPCIONALES:
        ruta = base / (stem + ".yaml")
        if not ruta.is_file():
            continue
        try:
            datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            raise ConfigError("YAML malformado en %s: %s (config FAIL-FAST)." % (ruta, e))
        if datos is None:
            raise ConfigError("fichero de config vacío: %s (config FAIL-FAST)." % ruta)
        config[stem] = datos

    # FAIL-FAST CONDICIONAL del audit trail (SPEC §6): si el detector `audit_chain` está
    # registrado, su config (audit_trail.yaml con trail_path) es OBLIGATORIA. Se comprueba
    # aquí, no en FICHEROS_REQUERIDOS, para no romper a un tercero que no use la feature.
    _exigir_audit_trail(config, base)

    # FAIL-FAST del umbral de colision de routing (DEFECTO 1, auditoria 06/07/2026): sin
    # esto un umbrales.yaml sin routing.jaccard_warn desactivaba INV-R4 en silencio (default
    # 1.0 en el detector). Un config incompleto debe dar ROJO explicito, no castrar el check.
    validar_umbrales_routing(config)

    # Validación mínima de forma de los invariantes (cobertura-motor depende de esto).
    invs = _requerir(config["invariantes"], "invariantes", "invariantes.yaml")
    if not isinstance(invs, list) or len(invs) < 1:
        raise ConfigError(
            "invariantes.yaml debe declarar una lista NO vacía bajo 'invariantes' "
            "(config FAIL-FAST)."
        )
    for i, inv in enumerate(invs):
        for clave in ("id", "detector", "severidad"):
            _requerir(inv, clave, "invariantes.yaml:invariantes[%d]" % i)

    return config
