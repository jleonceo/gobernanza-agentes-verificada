#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
motor/runner.py — el motor READ-ONLY: registro inyectable + ejecución + agregación.

EXTRAÍDO de verificacion_determinista.py (el `VERIFICADORES` dict nombre->guardián y
su bucle de auditoría/agregación de Veredictos), DES-ACOPLADO del dominio contable:
aquí NO hay `from controles_fraude import ...`, ni cuadre ΣDebe/ΣHaber, ni MySQL, ni
tolerancias de céntimo. Solo queda la pieza UNIVERSAL (SPEC FIJO #1):

    registro inyectable de detectores  +  ejecución READ-ONLY  +  agregación.

CONTRATO (ver CONTRATO_DETECTOR.md):
  - Un detector es un callable `run(ctx) -> list[Veredicto]`, registrado por decorador
    `@registrar("nombre")` o explícito `REGISTRO.register("nombre", fn)`.
  - El runner: carga config (fail-fast, hecho por el gate) -> construye ctx ->
    itera el registro en ORDEN CANÓNICO -> concatena veredictos -> agrega semáforo ->
    produce snapshot normalizado.
  - `ids_ejecutados()` reporta el conjunto de ids que el registro realmente emitió
    (cobertura-motor: el gate compara ese conjunto contra invariantes.yaml).

Todo READ-ONLY sobre el corpus del cliente: los helpers de ctx solo LEEN. Determinista.
Stdlib puro salvo la compilación de conventions (config_loader, que usa PyYAML).
"""

from pathlib import Path

from motor.config_loader import compilar_conventions
from motor.snapshot import snapshot_normalizado
from motor.veredicto import Veredicto, agregar, veredicto_de_uno, SANO, VIGILAR, ENFERMO


# ===========================================================================
# REGISTRO INYECTABLE de detectores
# ===========================================================================
class Registro:
    """Registro nombre -> callable de detectores. Inyectable y ordenado canónicamente.

    Poblado por decorador `@registrar("nombre")` o explícito `.register("nombre", fn)`.
    El runner itera SIEMPRE en orden canónico (`sorted` por nombre) para que el snapshot
    no dependa del orden de import de los módulos de detectores.
    """

    def __init__(self):
        self._detectores = {}

    def register(self, nombre, fn):
        """Registra un detector. Nombre duplicado -> error (dos detectores tapándose)."""
        if nombre in self._detectores:
            raise ValueError("detector duplicado en el registro: %r" % nombre)
        if not callable(fn):
            raise TypeError("el detector %r no es callable" % nombre)
        self._detectores[nombre] = fn
        return fn

    def nombres(self):
        """Nombres de detectores en ORDEN CANÓNICO (sorted, nunca orden de inserción)."""
        return sorted(self._detectores)

    def get(self, nombre):
        return self._detectores[nombre]

    def items(self):
        """(nombre, fn) en orden canónico."""
        return [(n, self._detectores[n]) for n in self.nombres()]

    def __len__(self):
        return len(self._detectores)

    def __contains__(self, nombre):
        return nombre in self._detectores


# Registro global del kit. Los módulos de detectores lo pueblan al importarse
# (run_gate hace `import detectores.gate_routing` -> se registra "gate_routing").
REGISTRO = Registro()


def registrar(nombre, registro=None):
    """Decorador de registro: `@registrar("gate_routing")` sobre `def run(ctx): ...`.

    Registra la función en el REGISTRO global (o en uno inyectado, para tests). Devuelve
    la función intacta, así el módulo puede seguir llamándola con normalidad.
    """
    destino = registro if registro is not None else REGISTRO

    def _deco(fn):
        destino.register(nombre, fn)
        return fn

    return _deco


# ===========================================================================
# CONTEXTO inyectado que reciben los detectores (CONTRATO §3)
# ===========================================================================
class Ctx:
    """Contexto READ-ONLY inyectado a cada detector. Ver CONTRATO_DETECTOR.md §3.

    Expone: root (INYECTADA, nunca expanduser), conventions (compiladas),
    invariantes, umbrales, exentas, y helpers de lectura READ-ONLY. Un detector
    NUNCA compila un regex propio ni descubre rutas por su cuenta: todo llega aquí.
    """

    def __init__(self, root, conventions, invariantes, umbrales, exentas,
                 routing_paths=None, audit_trail=None):
        # root se ABSOLUTIZA al construir el ctx (nunca expanduser: es resolución de una
        # ruta ya inyectada por el llamador, no descubrimiento por HOME). Absolutizar aquí
        # cierra la fragilidad de "root relativa": un detector que construye `root/rel` y
        # se lo pasa a read_text() obtiene entonces una ruta ABSOLUTA, que read_text() usa
        # tal cual sin re-unirla a root (evita el doble-join que daba un falso-ROJO
        # "registro ausente" -> toda skill invisible cuando un tercero corría con root
        # relativa; el gate siempre pasaba root absoluta y no lo destapaba).
        self.root = Path(root).resolve()     # raíz del corpus objetivo, INYECTADA y absoluta
        self.conventions = conventions       # objeto Conventions (regex ya compiladas)
        self.invariantes = invariantes       # dict {id -> {detector, severidad, esperado, ...}}
        self.umbrales = umbrales             # dict de umbrales.yaml
        self.exentas = exentas               # set de nombres exentos
        self.routing_paths = routing_paths or {}  # dict de routing_paths.yaml (rutas RELATIVAS)
        self.audit_trail = audit_trail or {}      # dict de audit_trail.yaml (trail_path RELATIVO)

    # --- helpers de lectura READ-ONLY (resuelven relativo a root) --------------
    def read_text(self, path):
        """Lee un fichero de texto resolviendo relativo a root. READ-ONLY.

        Acepta ruta relativa (bajo root) o absoluta (dentro de root). utf-8-sig para
        tolerar BOM (los SKILL.md del ecosistema a veces lo llevan). Nunca escribe.
        """
        p = Path(path)
        if not p.is_absolute():
            p = self.root / p
        return p.read_text(encoding="utf-8-sig")

    def iter_files(self, subdir=".", glob="*"):
        """Itera ficheros bajo root/subdir que casen `glob`, ORDENADOS canónicamente.

        `sorted`, NUNCA `os.listdir`/`glob` crudo: el orden del filesystem varía entre
        entornos y rompería la reproducibilidad bit-a-bit del snapshot. READ-ONLY.
        """
        base = self.root / subdir
        if not base.exists():
            return []
        return sorted(base.glob(glob))

    def existe(self, path):
        """True si el fichero/carpeta existe relativo a root. READ-ONLY."""
        p = Path(path)
        if not p.is_absolute():
            p = self.root / p
        return p.exists()


# ===========================================================================
# RESULTADO de un run
# ===========================================================================
class Resultado:
    """Salida de un run: semáforo agregado + desglose por detector + snapshot.

    El gate usa `.agregado` (SANO/VIGILAR/ENFERMO) y `.resumen()`. El desglose
    `por_detector` (nombre -> semáforo) alimenta la comparación método1 vs método2.
    """

    def __init__(self, root, veredictos, severidades, por_detector):
        self.root = Path(root)
        self.veredictos = veredictos
        self.severidades = severidades
        self.por_detector = por_detector
        self.agregado = agregar(veredictos, severidades)

    def resumen(self):
        """Resumen compacto y estable del run (para logs y comparación de fixtures)."""
        return {
            "agregado": self.agregado,
            "detectores": {k: self.por_detector[k] for k in sorted(self.por_detector)},
            "fallos": sorted(v.id for v in self.veredictos if not v.ok),
        }

    def snapshot(self):
        """JSON normalizado (bit-a-bit) del run — delega en motor.snapshot."""
        return snapshot_normalizado(self.root, self.veredictos, self.agregado,
                                    self.por_detector)

    def veredictos_de(self, detector):
        return list(self._por_nombre.get(detector, []))


# ===========================================================================
# EL RUNNER
# ===========================================================================
class Runner:
    """Motor de ejecución READ-ONLY sobre un registro inyectable de detectores."""

    def __init__(self, registro):
        self.registro = registro
        self._ids_ejecutados = set()          # cobertura-motor: ids que el registro emitió
        self._ultimo_por_detector = {}        # nombre -> list[Veredicto] del último run

    # --- construcción del ctx (config -> conventions compiladas + mapas) -------
    def construir_ctx(self, root, config):
        """Construye el Ctx inyectado desde la config cruda (config_loader la cargó).

        Compila corpus_conventions aquí (no en el detector). Indexa los invariantes por
        id para acceso O(1) desde el detector. NUNCA expanduser: root llega inyectada.
        """
        conventions = compilar_conventions(config["corpus_conventions"])
        invariantes = {inv["id"]: inv for inv in config["invariantes"]["invariantes"]}
        umbrales = config.get("umbrales", {}) or {}
        exentas = set((config.get("exentas", {}) or {}).get("exentas_routing", []) or [])
        routing_paths = config.get("routing_paths", {}) or {}
        audit_trail = config.get("audit_trail", {}) or {}
        return Ctx(root, conventions, invariantes, umbrales, exentas, routing_paths,
                   audit_trail)

    def _severidades(self, config):
        """Mapa {id -> severidad} desde invariantes.yaml (la severidad no la pone el detector).

        Fusiona dos fuentes:
          · la lista `invariantes` (los ids DECLARADOS, contados por la cobertura-motor);
          · el bloque `severidades_on_demand` (ids que solo se emiten ante un defecto
            concreto — INV-R4, RESULT-CONTRACT — y por eso NO viven en la lista ni cuentan
            para la cobertura, pero SÍ necesitan severidad para agregar a ENFERMO en vez
            de a un VIGILAR por defecto).
        La severidad NO la decide el detector: la inyecta el runner desde config.
        """
        inv_block = config["invariantes"]
        sev = {inv["id"]: inv.get("severidad") for inv in inv_block["invariantes"]}
        on_demand = inv_block.get("severidades_on_demand") or {}
        for _id, _sev in on_demand.items():
            sev.setdefault(_id, _sev)
        return sev

    # --- el bucle central: itera el registro, concatena, agrega ---------------
    def correr(self, root, config):
        """Corre TODOS los detectores del registro sobre `root` y agrega el semáforo.

        READ-ONLY: los detectores solo leen (contrato); el runner no escribe nada en el
        corpus del cliente. Registra los ids emitidos para la cobertura-motor.

        Devuelve un Resultado con .agregado / .resumen() / .snapshot().
        """
        ctx = self.construir_ctx(root, config)
        severidades = self._severidades(config)

        todos = []
        por_detector = {}
        por_nombre = {}
        self._ids_ejecutados = set()

        for nombre, run in self.registro.items():          # orden canónico
            veredictos = run(ctx)                           # CONTRATO: list[Veredicto]
            veredictos = self._validar_salida(nombre, veredictos)
            por_nombre[nombre] = veredictos
            todos.extend(veredictos)
            for v in veredictos:
                self._ids_ejecutados.add(v.id)
            # semáforo POR detector (peor caso de sus propios veredictos)
            por_detector[nombre] = self._semaforo_detector(veredictos, severidades)

        self._ultimo_por_detector = por_nombre
        res = Resultado(root, todos, severidades, por_detector)
        res._por_nombre = por_nombre
        return res

    def _semaforo_detector(self, veredictos, severidades):
        """Semáforo de UN detector: peor caso de sus veredictos (SANO/VIGILAR/ENFERMO)."""
        peor = SANO
        for v in veredictos:
            estado = veredicto_de_uno(v, severidades.get(v.id))
            if estado == ENFERMO:
                return ENFERMO
            if estado == VIGILAR:
                peor = VIGILAR
        return peor

    def _validar_salida(self, nombre, veredictos):
        """Verifica que el detector respeta el CONTRATO: list[Veredicto], nunca None.

        Un detector que devuelve None o algo que no es lista de Veredicto es un fallo de
        contrato y se ABORTA (no se silencia): el motor no puede agregar basura.
        """
        if veredictos is None:
            raise TypeError(
                "el detector %r devolvió None; el contrato exige list[Veredicto] "
                "(lista vacía [] es válida, None no)." % nombre
            )
        if not isinstance(veredictos, list):
            raise TypeError(
                "el detector %r devolvió %s; el contrato exige list[Veredicto]."
                % (nombre, type(veredictos).__name__)
            )
        for v in veredictos:
            if not isinstance(v, Veredicto):
                raise TypeError(
                    "el detector %r emitió un elemento %s; se esperaba Veredicto."
                    % (nombre, type(v).__name__)
                )
        return veredictos

    # --- cobertura-motor: qué ids ejecutó el registro (el gate lo compara) -----
    def ids_ejecutados(self):
        """Conjunto de ids de invariante que el registro emitió en el último run.

        El gate ASSERT que {ids declarados en invariantes.yaml} == este conjunto y
        len>=3 (prueba EJECUCIÓN por el registro, no corrección de la lógica).
        """
        return set(self._ids_ejecutados)
