# install.md: instalar y ejecutar `agent-governance-checks`

> Verificadores **deterministas** (sin LLM) de *routing* y *corpus* para sistemas de
> agentes/skills. Todo es **READ-ONLY** sobre tu corpus y **reversible**: el kit no
> escribe nada en tu entorno.
>
> Este documento tiene tres partes:
> 1. **Instalación**: qué necesitas y cómo se ejecuta.
> 2. **Formato de corpus esperado**: qué estructura debe tener tu corpus para que
>    cada detector vea algo (sin esto el kit no detecta nada sobre un corpus ajeno).
> 3. **Criterio B**: la prueba de que la instalación es real: un humano externo la
>    completa **solo con este fichero**, sin ayuda del constructor.

---

## 1. Instalación

### 1.1 Requisitos

- **Python 3.8+** (probado en Anaconda base).
- **PyYAML**: única dependencia externa, solo para leer `config/*.yaml`.
  ```
  pip install pyyaml      # o: conda install pyyaml
  ```
- **Cero red, cero LLM, cero base de datos.** El camino de verificación es
  determinista puro. `contrato/result_contract.py` es además **stdlib puro** (ni
  siquiera PyYAML): valida un envelope con solo la librería estándar.

> **El kit NO se instala con `pip install .`: se ejecuta POR RUTA** (H2, v1.0). Su
> `pyproject.toml` declara `packages=[]`/`py-modules=[]` DE FORMA DELIBERADA: solo
> sirve para fijar la dependencia PyYAML y los metadatos. `pip install .` no deja
> ningún comando ni módulo importable: solo instalaría PyYAML. La forma de usarlo
> es clonar/copiar el árbol y ejecutar los scripts por su ruta (`python gate/run_gate.py …`,
> ver §1.3-§1.5). Instala **solo la dependencia** (`pip install pyyaml`) y ejecuta por ruta.

### 1.2 Estructura del kit

```
agent-governance-checks/
  README.md              # frase de valor + "qué puedes hacer el lunes"
  install.md             # este fichero
  CONTRATO_DETECTOR.md   # la firma run(ctx)->list[Veredicto] que todo detector cumple
  motor/                 # runner READ-ONLY + registro + veredicto + snapshot + config_loader
                         # + audit_trail (hash chain SHA-256; ver §2.5)
  detectores/            # los CINCO detectores que registra el gate: gate_routing,
                         # lint_corpus, panel_salud, result_contract (result_envelope.py)
                         # y audit_chain (standalone, sin literales)
  contrato/
    result_contract.py   # validador del envelope de handoff (stdlib puro, standalone)
  gobernanza/            # metricas de la GOBERNANZA misma (no del corpus): DIU/CDL sobre
                         # un log de deferencias VIA C. Standalone, stdlib puro (ver su README.md)
  config/                # TODO patrón/umbral vive aquí; NADA hardcodeado en el código
    corpus_conventions.yaml
    invariantes.yaml
    exentas.yaml
    umbrales.yaml
    routing_paths.yaml   # REQUERIDO: dónde vive cada parte del corpus (skills_dir, registro…)
    audit_trail.yaml     # OPCIONAL: pero OBLIGATORIO si `audit_chain` está registrado (§2.5)
  gate/                  # suite de aceptación (fixtures limpias + rotas + audit) y sus 2 métodos
    run_gate.py
    verificador_minimo.py
    fixtures/
```

Los **cinco primeros yaml de `config/`** son los que `config_loader` **exige** (fail-fast:
si falta uno, aborta nombrándolo: incluido `routing_paths.yaml`, fácil de olvidar al
construir una config desde cero). `audit_trail.yaml` es el único **condicional**: solo se
exige si el detector `audit_chain` está registrado (§2.5); sin la feature, su ausencia no
rompe nada.

### 1.3 Ejecutar el gate técnico (criterio A)

El gate se comprueba por **dos métodos que deben coincidir** (doctrina "cifra por
instrumento = dos métodos"):

```bash
# MÉTODO 1: camino feliz + camino negativo:
python gate/run_gate.py --fixtures limpias   # todos los detectores en SANO
python gate/run_gate.py --fixtures rotas     # cada fixture rota da su rojo EXACTO
python gate/run_gate.py --fixtures ambas     # las dos, y exige convergencia

# MÉTODO 2: verificador independiente (no reusa la agregación del runner):
python gate/verificador_minimo.py
```

El gate pasa **solo si** `limpias` = todo SANO **Y** `rotas` = el rojo esperado exacto
de cada caso, comprobado por los **dos** métodos: método 1 (`run_gate.py`, vía el runner)
y método 2 (`verificador_minimo.py`, con código propio) contrastan cada uno su mapa
`detector -> veredicto` contra el mismo `esperado.txt`. Y además, en modo `--fixtures ambas`,
`run_gate.correr_comparacion_directa` compara **mapa-a-mapa** el `por_detector` de M1 con el
`mapa` de M2 (`comparar_metodos`) fixture a fixture, y falla si divergen: así se caza también
una discrepancia M1/M2 en un detector que el `esperado.txt` no nombre. La **independencia**
(§3) se mantiene: M2 no ejecuta el motor; el orquestador ejecuta los dos métodos y contrasta.

El modo `ambas` ejecuta además la **pasada audit** (`correr_audit`): verifica el audit trail
encadenado (§2.5) sobre `gate/fixtures/audit*/`: la cadena íntegra debe dar SANO y cada
trail roto su rojo exacto (`INV-AUDIT-*`).

### 1.4 Validar un envelope de handoff suelto (result_contract)

`contrato/result_contract.py` es standalone: no necesita el resto del kit.

```bash
python contrato/result_contract.py --self-test        # banco de no-regresión
python contrato/result_contract.py mi_envelope.json   # valida un envelope JSON
python contrato/result_contract.py mi_handoff.md      # valida un bloque ## RESULTADO
cat mi_envelope.json | python contrato/result_contract.py -   # desde stdin
```

Exit `0` si el envelope cumple el contrato; exit `1` si lo rompe (con el motivo por
stdout). Un `status` fuera del enum, o un `BLOCKED`/`ERROR` sin `summary`, dan RECHAZO.

### 1.5 Ejecutar sobre TU corpus

El kit no fija rutas absolutas. La **raíz del corpus se inyecta** (nunca `expanduser`)
y toda ruta se resuelve relativa a ella. Ajusta `config/*.yaml` a tu ecosistema
(ver §2) y apunta el runner a la raíz de tu corpus con el flag `--root`:

```bash
# Ejecuta TODOS los detectores sobre tu corpus (no sobre las fixtures del kit).
# La raíz se INYECTA tal cual (se absolutiza con Path(root).resolve(); NUNCA expanduser).
python gate/run_gate.py --root /ruta/a/mi/corpus

# Si tu config vive en otra carpeta (por defecto usa <kit>/config):
python gate/run_gate.py --root /ruta/a/mi/corpus --config /ruta/a/mi/config
```

Contrato de salida en modo `--root`: imprime el semáforo agregado y el desglose por
detector; **exit 0 si el corpus agrega `SANO`**, exit `!= 0` si `VIGILAR`/`ENFERMO`
(con la lista de defectos por stderr). `--root` es de conveniencia: internamente hace lo
mismo que `Runner.ejecutar(root=..., config=...)`, así que no tienes que escribirte un
runner a mano. `--root` y `--fixtures` son excluyentes: con `--root` se ejecuta TU corpus;
sin él, el gate ejecuta sobre las fixtures del kit (comportamiento por defecto, §1.3).

**Empieza siempre por copiar tus fixtures a `gate/fixtures/` y ejecutar el gate** (o apunta
`--root` a un corpus limpio de prueba): si tu corpus limpio no da SANO, la config aún no
describe tu formato.

> **`config_loader` es FAIL-FAST.** Si falta una clave en cualquier `config/*.yaml`,
> aborta nombrándola y **nunca** aplica un default silencioso. Un default reintroduciría
> el hardcodeo por la puerta de atrás y anularía la garantía de "cero literales".

---

## 2. Formato de corpus esperado (por detector)

Los detectores **parsean convenciones** de tu ecosistema. Todos los patrones viven en
`config/corpus_conventions.yaml` (regex, delimitadores, headings) y los umbrales en
`config/umbrales.yaml`. **Aquí se documenta el formato que cada patrón espera**: porque
externalizar el patrón no basta: si tu corpus no tiene esta forma, adapta tu corpus **o**
ajusta el regex de la convención. Los ejemplos son los del mini-corpus de `gate/fixtures/limpias/`.

### 2.1 Detector `gate_routing`: invisibilidad y colisiones de routing

**Qué verifica.** Que ninguna skill con descriptor quede **invisible** al router
(INV-R1), y que dos skills no tengan descripciones tan parecidas que el router no pueda
distinguirlas (INV-R4, similitud Jaccard sobre umbral).

**Formato esperado del corpus:**

- **Descriptores de skill.** Un fichero por skill (por defecto `SKILL.md`) bajo un
  directorio de skills, con **frontmatter YAML** delimitado. `corpus_conventions.yaml`
  fija el delimitador y el `name_regex`:
  ```
  ---
  name: skill-alfa
  description: Detecta duplicados en un listado de facturas y propone conciliacion.
  ---
  ```
  - `frontmatter.delimiter` (por defecto `---`) abre y cierra el bloque.
  - `frontmatter.name_regex` extrae el `name` declarado.
  - La `description` es lo que se compara por Jaccard entre skills (colisión de routing).

- **Registro de routing.** Un fichero (por defecto `Registro_Enjambres.md`) con una
  **tabla markdown**, una fila por skill enrutada:
  ```
  | skill | descripcion |
  |---|---|
  | skill-alfa | Detecta duplicados en un listado de facturas. |
  | skill-beta | Proyecta el calendario de vencimientos futuros. |
  ```
  - `routing_registry.filename` fija el nombre del fichero (relativo a la raíz).
  - `routing_registry.entry_regex` extrae el nombre de skill de cada fila.
  - **Nota conocida:** el `entry_regex` también casa la fila de cabecera (`skill`) y el
    separador (`---`). El detector **descarta** las filas que no correspondan a un
    directorio de skill real (ruido estándar de tabla markdown; inofensivo porque nunca
    coinciden con el nombre de una skill existente).

- **Convención de nombres de skill (elección deliberada, no dogma).** El `entry_regex`
  por defecto (`^\|\s*(?P<name>[a-z0-9-]+)\s*\|`) solo reconoce nombres en
  **minúsculas-kebab** (`orquestador-maestro`, `contable-experto`). Es una **convención
  deliberada** del sistema del que procede este kit, verificada sobre sus skills reales sin
  excepción: , no una limitación accidental: mantiene un único nombre canónico por skill y
  evita colisiones por diferencias de mayúsculas entre el frontmatter y el registro. En
  consecuencia, una skill cuyo `name` lleve mayúsculas (`Skill-Alfa`) se reportará como
  **invisible** al router aunque figure en el registro: es el comportamiento buscado: un
  nombre fuera de convención: , no un falso positivo. Si tu ecosistema admite mayúsculas
  como algo legítimo, amplía la clase del `entry_regex` a `[A-Za-z0-9-]+` (y refleja el
  cambio en `frontmatter.name_regex` y en una fixture nueva para no romper el gate).

- **Exentas.** Las skills que NO necesitan entrada de routing (p.ej. el orquestador raíz,
  que ES el router) se listan en `config/exentas.yaml` bajo `exentas_routing`.
  **Nunca** en código.

- **Umbral.** `config/umbrales.yaml → routing.jaccard_warn` (por defecto `0.22`): por
  encima de esa similitud entre dos descripciones, colisión.

**Defecto que detecta:** una skill con `SKILL.md` y descriptor que **no** figura en el
registro → INV-R1 FALLO (skill invisible). Dos descripciones casi idénticas → INV-R4 FALLO.

### 2.2 Detector `lint_corpus`: enlaces y punteros rotos

**Qué verifica.** Que todo enlace/puntero del corpus (wikilink y enlace markdown) apunte
a un fichero que existe, que la sección RAG de una skill no nombre RAGs inexistentes, y
que no haya rutas absolutas (defecto de portabilidad). Emite cuatro invariantes:

| Invariante | Cuándo | Severidad | Qué comprueba |
|---|---|---|---|
| `LINT-WIKILINK` | **siempre** (declarado) | alta → ENFERMO | Cada `[[destino]]` resuelve a un fichero del corpus. |
| `LINT-MDLINK` | on-demand (solo si falla) | alta → ENFERMO | Cada `[texto](destino.md)` local resuelve a un `.md` del corpus. |
| `LINT-ABSPATH` | on-demand (solo si falla) | media → VIGILAR | No hay rutas absolutas (portabilidad). |
| `LINT-RAGSEC` | on-demand (solo si falla) | alta → ENFERMO | Cada RAG nombrado en `## RAG QUE DEBES CARGAR` existe. |

Los tres `on-demand` se emiten SOLO cuando detectan su defecto (mismo patrón que `INV-R4`
en `gate_routing`): sobre el corpus limpio el único id que `lint_corpus` ejecuta es
`LINT-WIKILINK`, de modo que la **cobertura-motor** (`{ids declarados} == {ids ejecutados
sobre limpias}`) no se rompe. Su severidad vive en `invariantes.yaml → severidades_on_demand`.

**Formato esperado del corpus:**

- **Wikilinks.** `[[destino]]` o `[[destino|alias]]`: cada `destino` debe resolver a un
  fichero del corpus. Patrón en `corpus_conventions.wikilinks.wikilink`. → `LINT-WIKILINK`.
- **Enlaces markdown.** `[texto](destino.md)`: el destino `.md` **local** debe existir.
  Se ignoran URLs (`http(s)://`, `mailto:`), anclas puras (`#seccion`) y destinos que no
  terminan en `.md`. Patrón `wikilinks.mdlink`. → `LINT-MDLINK`.
- **Code spans.** Lo que va entre `` `backticks` `` se **ignora** en wikilinks/mdlinks/
  abspath (no es un enlace real). Patrón `wikilinks.codespan`. (Excepción: la lista de RAGs
  de la sección RAG sí se lee entre backticks: ahí es una lista de dependencias, no prosa.)
- **Rutas absolutas.** Una ruta absoluta real (unidad Windows `X:\`/`X:/` o raíz Unix `/seg`)
  se marca como defecto de portabilidad. Patrón `wikilinks.abspath` (exige un carácter de
  ruta tras el ancla, para no marcar prosa que empiece por `/ `). → `LINT-ABSPATH` (VIGILAR).
- **Sección RAG.** Dentro de un `SKILL.md`, el heading canónico
  `## RAG QUE DEBES CARGAR` lista los RAGs que la skill carga; cada RAG nombrado (`Fichero.md`)
  debe existir en el corpus. Texto y regex en `corpus_conventions.rag_section` + el patrón de
  fichero `markup.rag_file`; la carpeta de skills sale de `routing_paths.yaml`. → `LINT-RAGSEC`.
- **Ficheros de infraestructura.** `corpus_conventions.infra_files` (p.ej. `README.md`,
  `install.md`, `MEMORY.md`) lista los que un futuro chequeo de **huérfanas** exceptuaría.
  > **Chequeo de huérfanas. NO implementado (D8).** El 5º check del SPEC (marcar ficheros del
  > corpus que nadie enlaza) no llegó a construirse. `infra_files` se **carga** en
  > `config_loader` pero hoy **ningún** detector lo consume: queda **reservado** para cuando
  > exista ese chequeo (mismo patrón que la nota STALE de §2.2). No hay, por tanto, detección
  > de huérfanas en el kit; esta clave no cuenta ni descuenta nada todavía.

> **Marcas STALE. NO implementado (fuera de alcance determinista).** Una versión previa de
> este manual prometía detectar marcas STALE **caducadas** (ligadas a
> `umbrales.corpus.stale_max_dias`). Se **recorta**: decidir "caducada" exige una FECHA junto
> a la marca, y el corpus no tiene una convención que asocie una marca STALE a una fecha. Sin
> esa convención, "caducada" no es computable de forma determinista; detectar solo la
> *presencia* de la marca sobre-reportaría (toda doc legítimamente marcada STALE y aún vigente
> dispararía) y contradiría la palabra "caducada". `stale_marker_regex` y `stale_max_dias`
> quedan en la config **reservados** para cuando exista esa convención fecha↔marca; hoy ningún
> invariante los consume. (Reconciliación de la deuda GATE 2, 04/07/2026.)

**Defecto que detecta:** un `[[skill-inexistente]]` sin fichero destino → `LINT-WIKILINK`
FALLO / lint ENFERMO. Un `[texto](guia.md)` a un `.md` inexistente → `LINT-MDLINK` ENFERMO.
Un RAG inexistente en la sección RAG → `LINT-RAGSEC` ENFERMO. Una ruta absoluta →
`LINT-ABSPATH` VIGILAR.

### 2.3 Detector `panel_salud`: agregador anti-falso-verde

**Qué verifica.** Que el panel que agrega los checks no cuele un "verde por defecto":
agrega **funciones puras** por inyección de dependencias y comprueba coherencia interna.

**Formato esperado del corpus:**

- No parsea un formato nuevo: consume la **salida de los otros checks** por inyección de
  dependencias (no lee ficheros). No consume `config/umbrales.yaml`: `panel.presupuesto_listado`
  queda **reservado / no consumido hoy** (D8) para cuando el panel imponga un tope de líneas al
  listado auto-invocable; hoy ningún código lo lee.

**Defecto que detecta:** una incoherencia de agregación (un verde que no debería serlo)
→ INV-PANEL FALLO (severidad media → VIGILAR).

### 2.4 `result_contract`: el envelope de handoff

**Qué verifica.** Que el sobre con el que un agente cierra un handoff cumpla la gramática:

- `status` ∈ `{OK, WARN, BLOCKED, ERROR}`.
- `risk` ∈ `{LOW, MEDIUM, HIGH, CRITICAL}`.
- Campos presentes: `status, risk, skill_applied, summary, artifacts, next`.
- **Regla dura:** `status ∈ {BLOCKED, ERROR}` ⇒ `summary` NO vacío (≥ 15 caracteres);
  es lo que el orquestador muestra al humano cuando el flujo se corta.

**Formato esperado:** un objeto JSON (o un bloque markdown `## RESULTADO` de pares
`clave: valor`). Ejemplo válido:
```json
{
  "status": "OK",
  "risk": "LOW",
  "skill_applied": "skill-alfa",
  "summary": "Conciliacion completada sin incidencias.",
  "artifacts": ["informe_alfa.md"],
  "next": "ninguno"
}
```

**Qué NO hace:** no decide si el `status` es el *correcto* (eso es lógica del agente).
Garantiza la *gramática* del status, no su *verdad*.

### 2.5 Detector `audit_chain`: el audit trail encadenado (tamper-evident)

**Qué verifica.** La integridad y el orden de un **audit trail encadenado** (hash chain
SHA-256): recomputa la cadena génesis → cola y, **solo si el trail está roto**, emite
`INV-AUDIT-CADENA` (la huella recomputada de una entrada no casa con la almacenada),
`INV-AUDIT-ENLACE` (el `prev` de una entrada no casa con la huella real de la anterior),
`INV-AUDIT-SECUENCIA` (`seq` no contiguo desde 0: hueco, salto o reordenación) e
`INV-AUDIT-ILEGIBLE` (línea JSON corrupta: no se salta en silencio: saltarla escondería
una manipulación). Severidad alta → ENFERMO, declarados en
`invariantes.yaml → severidades_on_demand` (mismo patrón on-demand que `INV-R4`).

**Formato esperado:**

- **El trail es un artefacto del kit, no de tu corpus.** Lo escribe únicamente
  `motor/audit_trail.anexar` (opt-in, append-only, `prev=""` en la génesis); el detector
  solo lo **lee**. El invariante READ-ONLY sobre tu corpus queda intacto. El fichero es
  JSON-lines: una entrada por línea, cada una enlazada a la anterior por hash.
- **La ruta vive en `config/audit_trail.yaml → trail_path`**, relativa a la raíz
  inyectada (nunca `expanduser`, nunca ruta absoluta). Config **condicional**: si el
  detector `audit_chain` está registrado, `config_loader` exige `audit_trail.yaml`
  (fail-fast que nombra el fichero); si no usas la feature, su ausencia no aborta.
- **Inerte sin trail.** Sin `trail_path` declarado o sin fichero de trail, el detector
  devuelve `[]`: tus runs de routing/lint no se ensucian y la cobertura-motor no se rompe.

**Límite honesto (fase 1).** Tamper-evident ≠ firmado: el hash chain caza la manipulación
*interna* (entrada editada, saltada o reordenada), pero **no** caza el truncamiento de la
cola ni la regeneración completa del trail: eso exige checkpoint anclado + firma (fase 2).
Refuerzo recomendado a nivel de SO: permisos WORM / carpeta sin borrado sobre el trail.

**Defecto que detecta:** una entrada editada a posteriori → `INV-AUDIT-CADENA`/`ENLACE`
ENFERMO; una entrada saltada o reordenada → `INV-AUDIT-SECUENCIA` ENFERMO; una línea
ilegible → `INV-AUDIT-ILEGIBLE` ENFERMO.

---

## 3. Criterio B: la prueba de que install.md especifica de verdad

El gate técnico (criterio A) prueba **fontanería**: que los detectores ejecutan y detectan
sobre las fixtures del propio equipo. **No prueba valor para un tercero.** Por eso v1 exige
también:

**CRITERIO B (humano externo).** Un segundo humano, **ajeno al equipo constructor**, que:

1. Instala el kit siguiendo **solo este `install.md`**, sin ayuda del constructor.
2. Prepara un **corpus propio** (aunque sea sintético): al menos 2 skills con su
   `SKILL.md` (frontmatter + `## RAG QUE DEBES CARGAR`), un `Registro_Enjambres.md`
   que las liste, un `MEMORY.md` con wikilinks, y un `envelope.json`.
3. Ajusta `config/*.yaml` a las rutas/convenciones de su corpus.
4. Ejecuta los cinco detectores (`python gate/run_gate.py`; el quinto, `audit_chain`,
   queda inerte si su corpus no tiene trail. §2.5) y `result_contract.py` sobre su
   corpus y **obtiene veredictos coherentes**: SANO cuando el corpus está bien; el rojo
   correcto cuando siembra un defecto (borra una entrada del registro → INV-R1; rompe un
   wikilink → lint ENFERMO; vacía el summary de un `BLOCKED` → result_contract RECHAZO).

**Se considera superado** si ese humano llega a veredictos coherentes **sin preguntar nada
al constructor**. Si necesita ayuda, este `install.md` no especifica el formato de corpus
de verdad y hay que ampliarlo. Sin criterio B, v1 **no** cierra (solo pasa el criterio A).

> **Nota de plataforma.** `agentes_base/` y `gobernanza/` son material de proceso del
> ecosistema Claude Code; un tercero sin ese runtime no obtiene *enforcement* de ellos.
> El **núcleo verificable** (motor + detectores + contrato + gate) es independiente de la
> plataforma y es lo que el criterio B ejercita.
