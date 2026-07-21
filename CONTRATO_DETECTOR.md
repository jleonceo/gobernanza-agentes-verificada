# CONTRATO_DETECTOR: la firma que TODO detector debe cumplir

> Entregable NUEVO de v1 (cierra hueco #6 del SPEC). Sin este contrato el enjambre
> programador NO puede construir ni un tercero extender. Este documento es la
> **definición de "hecho"**: describe la interfaz, no la implementa.
>
> Escrito por VERIFICADOR-PROGRAMADOR el 03/07/2026 (fase test-primero). El código de
> `motor/` y `detectores/` **todavía no existe**: es correcto que el gate falle en rojo
> hasta que el CONSTRUCTOR lo implemente respetando exactamente esta firma.

---

## 1. La firma (FIJA, no negociable)

```python
def run(ctx) -> list[Veredicto]:
    ...
```

- Un detector es **un callable registrable** con esta firma exacta.
- Recibe **un solo argumento** `ctx` (el contexto inyectado, ver §3).
- Devuelve **SIEMPRE** una `list[Veredicto]` (ver §2). Nunca `None`, nunca un dict,
  nunca un escalar. Lista vacía `[]` es válida (significa "nada que reportar"), pero
  un detector que declara un invariante DEBE emitir al menos un Veredicto por él.
- **NUNCA imprime** (`print`, logging a stdout): el runner es quien decide qué mostrar.
- **NUNCA escribe** en el filesystem del cliente. READ-ONLY absoluto.
- **NUNCA usa** `expanduser`, `Path.home()`, `os.environ['HOME']`, ni rutas absolutas
  literales. Toda ruta llega por `ctx` (root inyectada) o por config compilada en `ctx`.

## 2. El tipo de retorno: `Veredicto`

`Veredicto` es una dataclass definida en `motor/veredicto.py` (a construir):

```python
@dataclass(frozen=True)
class Veredicto:
    id: str          # id del invariante, p.ej. "INV-R1", "LINT-WIKILINK"
    ok: bool         # True = sano; False = defecto detectado
    esperado: str    # qué se esperaba (texto normalizado, comparable)
    obtenido: str    # qué se obtuvo (texto normalizado, comparable)
    detalle: str     # explicación humana (NO se usa para comparar veredictos)
```

Agregación (también en `motor/veredicto.py`), sobre la lista completa de un run:

- Todos `ok=True`  → **SANO**
- Algún `ok=False` de severidad baja/aviso → **VIGILAR**
- Algún `ok=False` de severidad alta → **ENFERMO**

La severidad NO vive en el detector: llega desde `config/invariantes.yaml` (por `id`).
El detector solo dice `ok=True/False`; el runner mapea `id -> severidad -> veredicto`.

## 3. Qué expone `ctx` (el contexto inyectado)

`ctx` es construido por el runner y `motor/config_loader.py` ANTES de llamar a `run`.
Contrato mínimo de lo que un detector puede leer de `ctx`:

| Atributo | Tipo | Qué es |
|---|---|---|
| `ctx.root` | `Path` | Raíz del corpus objetivo, **INYECTADA** (nunca `expanduser`). Todo se resuelve relativo a ella. |
| `ctx.conventions` | objeto | Patrones de parseo YA COMPILADOS desde `corpus_conventions.yaml` (regex compiladas, delimitadores, headings). Ver §4. |
| `ctx.invariantes` | dict | Los invariantes declarados en `invariantes.yaml` que apuntan a este detector (id, esperado, severidad). |
| `ctx.umbrales` | dict | Tolerancias de `umbrales.yaml` (Jaccard, antigüedad STALE, presupuestos). |
| `ctx.exentas` | set | Nombres exentos de `exentas.yaml` (p.ej. el orquestador raíz que no necesita entrada de routing). |
| `ctx.read_text(path)` | fn | Helper de lectura READ-ONLY, resuelve relativo a `ctx.root`, devuelve `str`. |
| `ctx.iter_files(subdir, glob)` | fn | Itera ficheros de forma **ordenada canónicamente** (`sorted`, nunca `os.listdir` crudo). |

**Regla dura**: un detector NUNCA compila un regex con un literal propio. Todo patrón de
parseo llega por `ctx.conventions`, cargado por `config_loader`. Un `re.compile("...")`
con literal dentro de `detectores/` es un fallo de contrato (lo caza el pre-check del gate).

## 4. Convenciones que `ctx.conventions` entrega (compiladas)

Cargadas por `config_loader` desde `config/corpus_conventions.yaml`. El detector las
consume ya compiladas; no las conoce como literales. Grupos:

- `frontmatter`: delimitador + `name_regex`.
- `routing_registry`: `filename` + `entry_regex`.
- `wikilinks`: `wikilink` + `mdlink` + `codespan` + `abspath` regex.
- `rag_section`: `heading_text` + `heading_regex`.
- `markup`: `heading` + `codespan` + `rag_file` regex.
- `tokenizer`: `word_regex` + `min_len` + `stopwords` + `ngrams`.
- `infra_files`: lista de ficheros de infraestructura (no cuentan como huérfanos).
- `stale_marker_regex`: patrón de marca STALE.

## 5. El registro de detectores

`motor/runner.py` mantiene un registro `dict[str, Callable]` nombre→callable.
Poblado por **decorador** o **registro explícito**:

```python
# opción decorador (a implementar en runner.py)
@registrar("gate_routing")
def run(ctx) -> list[Veredicto]: ...

# opción explícita
REGISTRO.register("lint_corpus", run)
```

El runner:
1. carga config (fail-fast),
2. construye `ctx`,
3. itera el registro en orden canónico,
4. concatena todas las listas de `Veredicto`,
5. agrega a SANO/VIGILAR/ENFERMO,
6. produce un snapshot normalizado (ver `motor/snapshot.py`).

## 6. Contrato de cobertura-motor (por qué importa el registro)

`invariantes.yaml` declara ≥3 invariantes, uno por detector. El gate ASSERT que
**{ids declarados} == {ids que el registro realmente ejecutó}** y `len >= 3`.
Esto prueba que el motor (runner + registro + snapshot) se EJERCITA de punta a punta: que el detector pasó por el registro, no que su lógica sea correcta (eso lo prueban las
fixtures rotas). Un invariante declarado que ningún detector registrado emite → ROJO
`MOTOR NO EJERCITADO`.

## 7. Qué NO define este contrato

- La LÓGICA interna de cada detector (eso vive en `detectores/*.py`, a construir).
- Las cifras/umbrales concretos (eso es VARIABLE, vive en `config/*.yaml`).
- El formato del corpus del cliente (eso se documenta en `install.md`, entregable aparte).
