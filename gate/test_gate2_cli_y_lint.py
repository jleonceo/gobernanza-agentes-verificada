#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_gate2_cli_y_lint.py — Suite de la deuda GATE 2 (CLI --root + lint reconciliado).
=====================================================================================

AÑADE a la suite del kit (no la reinventa: run_gate.py y verificador_minimo.py siguen
siendo los 2 métodos del gate). Aquí se cubre lo NUEVO de la deuda GATE 2:

  1. CLI `--root` de run_gate.py: apunta el gate a una raíz ARBITRARIA (no FIXTURES/limpias)
     y devuelve el semáforo de ESA raíz; comportamiento por defecto intacto.
  2. lint_corpus ampliado: cada chequeo nuevo (mdlink, abspath, sección RAG) detecta su
     defecto en su fixture rota y da limpio sobre fixtures/limpias.

Convención de test (estilo del kit, sin pytest): funciones test_*; cada una hace asserts;
main() las corre todas, imprime PASA/FALLA por test y sale 0 si todas pasan, 1 si alguna falla.
Determinista, READ-ONLY sobre el corpus. Se corre con:
    python gate/test_gate2_cli_y_lint.py
"""

import subprocess
import sys
import shutil
import tempfile
from pathlib import Path

# --- BOOTSTRAP de sys.path: la raíz del kit (padre de gate/) en el path para importar
#     motor/detectores/config, igual que run_gate.py. READ-ONLY.
_RAIZ_KIT = Path(__file__).resolve().parent.parent
if str(_RAIZ_KIT) not in sys.path:
    sys.path.insert(0, str(_RAIZ_KIT))

from motor.config_loader import cargar_config
from motor.runner import Runner, REGISTRO
import detectores.gate_routing      # noqa: F401
import detectores.lint_corpus       # noqa: F401
import detectores.panel_salud       # noqa: F401
import detectores.result_envelope   # noqa: F401

RAIZ_GATE = Path(__file__).resolve().parent
FIXTURES = RAIZ_GATE / "fixtures"
CONFIG = _RAIZ_KIT / "config"
PYTHON = sys.executable
RUN_GATE = RAIZ_GATE / "run_gate.py"


def _config():
    return cargar_config(CONFIG)


def _correr(root):
    """Corre el registro completo sobre `root` y devuelve el Resultado."""
    runner = Runner(REGISTRO)
    return runner.correr(root=root, config=_config())


def _ids_en_fallo(res):
    return {v.id for v in res.veredictos if not v.ok}


# ===========================================================================
# 1. CLI --root
# ===========================================================================
def test_cli_root_apunta_a_raiz_arbitraria():
    """`run_gate.py --root <limpias>` corre sobre esa raíz (no la cablea) y sale 0 (SANO)."""
    root = FIXTURES / "limpias"
    p = subprocess.run(
        [PYTHON, str(RUN_GATE), "--root", str(root)],
        capture_output=True, text=True, cwd=str(_RAIZ_KIT),
    )
    assert p.returncode == 0, (
        "run_gate.py --root sobre un corpus SANO debe salir 0; salió %d.\nstdout=%s\nstderr=%s"
        % (p.returncode, p.stdout, p.stderr)
    )
    assert "SANO" in (p.stdout + p.stderr), (
        "la salida debe reportar SANO para el corpus limpio; stdout=%s" % p.stdout
    )


def test_cli_root_detecta_corpus_roto():
    """`run_gate.py --root <fixture rota>` sobre un corpus con defecto sale != 0 (no SANO)."""
    root = FIXTURES / "rotas" / "03_wikilink_roto"
    p = subprocess.run(
        [PYTHON, str(RUN_GATE), "--root", str(root)],
        capture_output=True, text=True, cwd=str(_RAIZ_KIT),
    )
    assert p.returncode != 0, (
        "run_gate.py --root sobre un corpus ENFERMO debe salir != 0; salió 0.\nstdout=%s"
        % p.stdout
    )


def test_cli_default_intacto():
    """Sin --root, `run_gate.py --fixtures ambas` se comporta como hoy (gate VERDE, exit 0)."""
    p = subprocess.run(
        [PYTHON, str(RUN_GATE), "--fixtures", "ambas"],
        capture_output=True, text=True, cwd=str(_RAIZ_KIT),
    )
    assert p.returncode == 0, (
        "el modo por defecto (gate de fixtures) debe seguir VERDE; salió %d.\nstderr=%s"
        % (p.returncode, p.stderr)
    )
    # el sello de `ambas` ahora incluye la convergencia directa M1/M2 (cableada en D7)
    assert "VERDE" in p.stdout and "metodo 1" in p.stdout, (
        "falta el sello VERDE del gate método 1: %s" % p.stdout)


# ===========================================================================
# 2. lint_corpus ampliado — cada chequeo nuevo
# ===========================================================================
def test_lint_limpias_solo_wikilink():
    """Sobre fixtures/limpias, lint_corpus da SANO y su único id ejecutado es LINT-WIKILINK
    (cobertura-motor intacta: los nuevos ids son on-demand, no se emiten sin defecto)."""
    res = _correr(FIXTURES / "limpias")
    lint_ids = {v.id for v in res.veredictos if v.id.startswith("LINT-")}
    assert lint_ids == {"LINT-WIKILINK"}, (
        "sobre limpias lint_corpus solo debe emitir LINT-WIKILINK; emitió %s" % sorted(lint_ids)
    )
    assert res.por_detector["lint_corpus"] == "SANO", (
        "lint_corpus sobre limpias debe ser SANO; fue %s" % res.por_detector["lint_corpus"]
    )


def test_lint_mdlink_roto():
    """La fixture 06 dispara LINT-MDLINK en fallo y agregado ENFERMO."""
    res = _correr(FIXTURES / "rotas" / "06_mdlink_roto")
    assert "LINT-MDLINK" in _ids_en_fallo(res), (
        "la fixture de mdlink roto debe poner LINT-MDLINK en fallo; fallos=%s" % sorted(_ids_en_fallo(res))
    )
    assert res.agregado == "ENFERMO", "mdlink roto debe agregar ENFERMO; fue %s" % res.agregado


def test_lint_abspath():
    """La fixture 07 dispara LINT-ABSPATH en fallo y agregado VIGILAR (severidad media)."""
    res = _correr(FIXTURES / "rotas" / "07_abspath_portabilidad")
    assert "LINT-ABSPATH" in _ids_en_fallo(res), (
        "la fixture de ruta absoluta debe poner LINT-ABSPATH en fallo; fallos=%s" % sorted(_ids_en_fallo(res))
    )
    assert res.agregado == "VIGILAR", (
        "ruta absoluta (severidad media) debe agregar VIGILAR; fue %s" % res.agregado
    )


def test_lint_ragsec_rag_inexistente():
    """La fixture 08 dispara LINT-RAGSEC en fallo y agregado ENFERMO."""
    res = _correr(FIXTURES / "rotas" / "08_ragsec_rag_inexistente")
    assert "LINT-RAGSEC" in _ids_en_fallo(res), (
        "la fixture de RAG inexistente debe poner LINT-RAGSEC en fallo; fallos=%s" % sorted(_ids_en_fallo(res))
    )
    assert res.agregado == "ENFERMO", "RAG inexistente debe agregar ENFERMO; fue %s" % res.agregado


def test_lint_ningun_falso_positivo_en_limpias():
    """Ningún chequeo nuevo dispara sobre el corpus limpio (anti falso-positivo)."""
    res = _correr(FIXTURES / "limpias")
    fallos = _ids_en_fallo(res)
    for nuevo in ("LINT-MDLINK", "LINT-ABSPATH", "LINT-RAGSEC"):
        assert nuevo not in fallos, "%s NO debe dispararse sobre limpias; fallos=%s" % (nuevo, sorted(fallos))


def test_agregado_severidad_critica_no_diverge():
    """D6: el metodo 2 (verificador_minimo._agregar_propio) debe reconocer TODA la
    severidad alta que reconoce el motor (alta/critica/critical/high), no solo el
    literal 'alta'. Si diverge, una severidad legal para el motor da M1=ENFERMO y
    M2=VIGILAR -> el gate 'ambas' rompe espuriamente (defecto de arnes, no de corpus)."""
    sys.path.insert(0, str(RAIZ_GATE))
    from verificador_minimo import _agregar_propio
    from motor.veredicto import Veredicto, SEVERIDADES_ALTAS
    v_fallo = Veredicto(id="X", ok=False, esperado="SANO", obtenido="ROTO", detalle="")
    for sev in SEVERIDADES_ALTAS:  # los dos instrumentos deben coincidir para CADA una
        got = _agregar_propio([v_fallo], {"X": sev})
        assert got == "ENFERMO", "severidad alta %r -> M2 dio %r (esperado ENFERMO)" % (sev, got)
    # control: una severidad media NO agrega a ENFERMO (no sobre-reacciona)
    assert _agregar_propio([v_fallo], {"X": "media"}) == "VIGILAR", "media no debe ser ENFERMO"
    # control: mayusculas/espacios se normalizan igual que el motor (strip().lower())
    assert _agregar_propio([v_fallo], {"X": " CRITICAL "}) == "ENFERMO", "no normalizo como el motor"


def test_comparacion_directa_m1_m2_cableada():
    """Mecanismo #3 (cableado D7): `run_gate.correr_comparacion_directa` contrasta el mapa
    de M1 (runner) con el de M2 (codigo propio) por fixture y FALLA si divergen — cazando
    una discrepancia que el esperado.txt NO nombra. Antes de D7 esta comparacion era codigo
    muerto (comparar_metodos no se invocaba)."""
    sys.path.insert(0, str(RAIZ_GATE))
    import run_gate
    import verificador_minimo
    config = _config()
    # control: sobre las fixtures reales, M1 y M2 CONVERGEN -> no lanza
    run_gate.correr_comparacion_directa(config)
    # inyeccion: forzamos a M2 a discrepar de M1 (el agregador de M2 miente) -> debe FALLAR.
    # Es una divergencia que NINGUN esperado.txt nombra: solo la comparacion directa la caza.
    orig = verificador_minimo._agregar_propio
    verificador_minimo._agregar_propio = lambda vs, sev: "VIGILAR"
    try:
        salto = False
        try:
            run_gate.correr_comparacion_directa(config)
        except SystemExit as e:
            salto = (e.code not in (0, None))
        assert salto, "la comparacion directa NO cazo la divergencia M1/M2 inyectada"
    finally:
        verificador_minimo._agregar_propio = orig
    # tras restaurar, vuelve a converger (no dejo estado roto)
    run_gate.correr_comparacion_directa(config)


# ===========================================================================
# 2b. H1 (v1.0): el resumen --root SURFACEA el SANO-por-vacío (no lo colapsa)
# ===========================================================================
def _corpus_sin_skills():
    """Corpus temporal LIMPIO pero SIN `skills/` ni registro de routing: el caso
    realista de un tercero con `--root` mal apuntado o la config aún sin adaptar.
    gate_routing resuelve SANO por vacío (INV-R1 N/A-safe); el resto inerte."""
    raiz = Path(tempfile.mkdtemp(prefix="h1_sin_skills_"))
    (raiz / "nota.md").write_text("# nota\n\nUn documento limpio, sin enlaces.\n",
                                  encoding="utf-8")
    return raiz


def test_h1_root_surfacea_vacio_gate_routing():
    """H1: cuando gate_routing da SANO porque NO había skills que cubrir, el resumen
    de `--root` debe SURFACEARLO (`gate_routing=SANO (0 skills ...)`), no colapsarlo a
    un escueto `gate_routing=SANO` que induce falsa confianza (el propio README lo
    combate: 'todo verde necesita respaldo'). El agregado sigue SANO y el exit 0."""
    raiz = _corpus_sin_skills()
    try:
        p = subprocess.run(
            [PYTHON, str(RUN_GATE), "--root", str(raiz)],
            capture_output=True, text=True, cwd=str(_RAIZ_KIT),
        )
        assert p.returncode == 0, (
            "corpus limpio sin skills debe agregar SANO (exit 0); salió %d.\nstderr=%s"
            % (p.returncode, p.stderr))
        assert "gate_routing=SANO (0 skills" in p.stdout, (
            "el resumen debe surfacear que gate_routing dio SANO por vacío (0 skills), "
            "no colapsarlo a 'gate_routing=SANO' a secas; stdout=%s" % p.stdout)
    finally:
        shutil.rmtree(raiz, ignore_errors=True)


# ===========================================================================
# 3. lint_corpus: ACOTAR el escaneo a subárboles (include_subtrees)
# ===========================================================================
def _corpus_dos_subarboles():
    """Crea un corpus temporal con DOS subárboles: skills/ (una skill que enlaza a la nota
    del otro subárbol, un cross-ref LEGÍTIMO) y notas/ (una nota con un wikilink
    INTENCIONALMENTE colgante, como los forward-links de la memoria real). Devuelve la ruta
    raíz (el llamador la borra)."""
    raiz = Path(tempfile.mkdtemp(prefix="lint_scope_"))
    skill = raiz / "skills" / "s1"
    skill.mkdir(parents=True)
    # la skill enlaza [[n]] -> nota real en notas/ (subárbol que NO se auditará al acotar):
    # debe RESOLVER porque el universo de destinos es toda la raíz, no el ámbito acotado.
    (skill / "SKILL.md").write_text(
        "---\nname: s1\n---\n\n# s1\n\nApunta a [[n]] (nota real de otro subárbol).\n",
        encoding="utf-8")
    notas = raiz / "notas"
    notas.mkdir()
    # forward-link deliberado a una nota que aún no existe (patrón legítimo de la memoria)
    (notas / "n.md").write_text(
        "# nota\n\nApunta a [[destino-que-aun-no-existe]] a propósito.\n", encoding="utf-8")
    return raiz


def _lint_ids_fallo(root, include_subtrees=None):
    """Corre SOLO lint_corpus.run sobre `root` (sin arrastrar el resto del registro) y
    devuelve el set de ids en fallo. Si include_subtrees se pasa, se inyecta en la config
    de routing_paths — exactamente el canal que usa el perfil de dogfooding."""
    import copy
    config = copy.deepcopy(_config())
    if include_subtrees is not None:
        config.setdefault("routing_paths", {})["include_subtrees"] = include_subtrees
    ctx = Runner(REGISTRO).construir_ctx(root=root, config=config)
    veredictos = detectores.lint_corpus.run(ctx)
    return {v.id for v in veredictos if not v.ok}


def test_lint_include_subtrees_acota_scan():
    """include_subtrees ACOTA el escaneo de lint_corpus a los subárboles nombrados.

    Sin acotar, el wikilink colgante de notas/ dispara LINT-WIKILINK (el escaneo ve TODO
    el árbol). Acotando a skills/, notas/ queda FUERA del ESCANEO y no hay falso positivo
    — que es justo lo que el dogfooding necesita para lintar skills+rag sin arrastrar la
    memoria (cuyos forward-links colgantes son intencionales).

    Y CRÍTICO (universo != ámbito): al acotar a skills/, el enlace [[n]] de la skill al
    subárbol notas/ (no auditado) debe SEGUIR resolviendo — su destino existe en el
    universo. Si el fix acotara también el universo de destinos, [[n]] daría falso roto.
    Este test lo fija: la rama acotada NO debe reportar LINT-WIKILINK NI por el colgante de
    notas/ (fuera de escaneo) NI por el cross-ref [[n]] (destino válido del universo)."""
    raiz = _corpus_dos_subarboles()
    try:
        # sin acotar: el forward-link colgante de notas/ SÍ se audita -> LINT-WIKILINK en fallo
        sin_acotar = _lint_ids_fallo(raiz)
        assert "LINT-WIKILINK" in sin_acotar, (
            "sin acotar, el wikilink colgante de notas/ debe disparar LINT-WIKILINK; "
            "fallos=%s" % sorted(sin_acotar))
        # acotado a skills/: notas/ fuera del escaneo Y [[n]] resuelve por el universo
        acotado = _lint_ids_fallo(raiz, include_subtrees=["skills"])
        assert "LINT-WIKILINK" not in acotado, (
            "acotando a skills/: ni el colgante de notas/ (fuera de escaneo) ni el cross-ref "
            "[[n]] (destino válido del universo) deben disparar LINT-WIKILINK; fallos=%s"
            % sorted(acotado))
    finally:
        shutil.rmtree(raiz, ignore_errors=True)


# ===========================================================================
# runner de la suite
# ===========================================================================
def main():
    tests = [
        test_cli_root_apunta_a_raiz_arbitraria,
        test_cli_root_detecta_corpus_roto,
        test_cli_default_intacto,
        test_lint_limpias_solo_wikilink,
        test_lint_mdlink_roto,
        test_lint_abspath,
        test_lint_ragsec_rag_inexistente,
        test_lint_ningun_falso_positivo_en_limpias,
        test_h1_root_surfacea_vacio_gate_routing,
        test_agregado_severidad_critica_no_diverge,
        test_comparacion_directa_m1_m2_cableada,
        test_lint_include_subtrees_acota_scan,
    ]
    fallos = 0
    for t in tests:
        try:
            t()
            print("PASA  %s" % t.__name__)
        except AssertionError as e:
            fallos += 1
            print("FALLA %s: %s" % (t.__name__, e))
        except Exception as e:  # error inesperado (import, fixture ausente): también es fallo
            fallos += 1
            print("ERROR %s: %s: %s" % (t.__name__, type(e).__name__, e))
    print("-" * 60)
    if fallos:
        print("SUITE GATE2: %d FALLO(S) de %d" % (fallos, len(tests)))
        return 1
    print("SUITE GATE2 VERDE: %d/%d" % (len(tests), len(tests)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
