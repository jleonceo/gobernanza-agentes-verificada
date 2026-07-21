# UPGRADE.md — actualizar versiones de `agent-governance-checks` sin romper el gate

> **Qué es esto.** El protocolo seguro para subir la versión de Python o de PyYAML (la
> única dependencia externa) sin degradar el gate. El kit es determinista, `READ-ONLY` y
> stdlib-puro salvo PyYAML; por eso "actualizar" aquí significa casi siempre **cambiar el
> intérprete o PyYAML** y **volver a pasar el gate por dos métodos**.
>
> **Regla base.** Ninguna subida de versión se da por buena hasta que el gate sigue
> **VERDE por los dos métodos** (§2). Si degrada, se revierte (§2, paso 5). Movimiento de
> versión ≠ mejora: solo cuenta si pasa la puerta de no-regresión.

---

## 1. Matriz de versiones

Estados posibles: **PROBADO** (verificado en vivo, gate verde) · **DECLARADO** (soportado
según README/install/SPEC, sin verificación en vivo registrada aquí) · **NO VERIFICADO**
(no consta ni una cosa ni otra — no se afirma) · **EXCLUIDO** (fuera del rango por diseño).

### 1.1 Python

| Versión Python | Estado | Fuente / nota |
|---|---|---|
| 3.8 | **DECLARADO** (mínimo soportado) | `install.md §1.1` fija "Python 3.8+". No consta run en vivo sobre 3.8 en este repo → soporte declarado, no verificado. |
| 3.9 | NO VERIFICADO | No consta. Dentro del rango declarado 3.8+, pero sin run registrado. |
| 3.10 | **PROBADO** | Registrado como probado en la nota del ladrillo `requirements.txt` / historial del kit (Anaconda base). |
| 3.11 | NO VERIFICADO | No consta. |
| 3.12 | NO VERIFICADO | No consta. |
| 3.13 | **PROBADO** | Registrado como probado (soporte declarado 3.8+, extremo alto verificado). |
| 3.14 | **PROBADO** (este ladrillo) | Verificado en vivo el 06/07/2026 en la máquina de build: `Python 3.14.6`, gate VERDE por 2 métodos (ver §3). No estaba en la matriz previa; se añade porque se ejecutó de verdad. |
| ≥ 3.15 | NO VERIFICADO | Fuera de lo probado. No se afirma compatibilidad hasta correr el gate. |

> **Base del soporte 3.8+.** El núcleo es stdlib estable (`pathlib`, `re`, `json`,
> `argparse`, `unittest`). No usa sintaxis por encima de 3.8 conocida como load-bearing.
> Aun así, "declarado" no es "probado": 3.9, 3.11 y 3.12 quedan **NO VERIFICADO** hasta
> que alguien corra el gate en ellas y lo anote aquí. No inventar un ✅ sin run.

### 1.2 PyYAML (única dependencia externa)

Pin vigente en `requirements.txt`: **`PyYAML>=5.4,<7.0`**.

| Versión PyYAML | Estado | Nota |
|---|---|---|
| < 5.4 | **EXCLUIDO** (suelo) | Por debajo del mínimo del pin. 5.4 es donde se estabiliza el patrón de carga segura que el kit asume; versiones anteriores quedan fuera. |
| 5.4.x | **DECLARADO** (mínimo del pin) | Extremo bajo del rango soportado. No consta run en vivo en este repo sobre 5.4 exacto → declarado por el pin, no verificado aquí. |
| 6.0.x | **PROBADO** | Verificado en vivo el 06/07/2026: `PyYAML 6.0.3`, gate VERDE por 2 métodos (§3). |
| 6.x (resto) | **DECLARADO** | Dentro del pin `<7.0`. El kit usa `yaml.safe_load`, estable en toda la serie 6.x. |
| ≥ 7.0 | **EXCLUIDO** (techo del pin) | Fuera del rango a propósito. Motivo en §4. No subir sin validar. |

> **Qué usa el kit de PyYAML.** Solo la carga de `config/*.yaml` en
> `motor/config_loader.py`, y por el camino **seguro** (`safe_load`, sin construir objetos
> arbitrarios). `contrato/result_contract.py` no toca PyYAML (es **stdlib puro**): valida el
> envelope de handoff sin ninguna dependencia externa. Por eso el radio de impacto de una
> subida de PyYAML se limita al `config_loader` y a los detectores que dependen de la config.

---

## 2. Protocolo de actualización seguro

Cinco pasos. No saltarse el 2 ni el 3: el gate se mide **por dos métodos que deben coincidir**
(doctrina "cifra por instrumento = dos métodos"). Correr todo **desde la carpeta del kit**
(`agent-governance-checks/`).

**Paso 1 — Subir la versión.**
Cambiar el intérprete de Python **o** la versión de PyYAML (respetando el pin
`>=5.4,<7.0`; si la subida es a 7.x, leer §4 antes de tocar el pin). Anotar de qué versión
se parte y a cuál se va.

**Paso 2 — Método 1: gate con fixtures limpias Y rotas.**
```bash
python gate/run_gate.py --fixtures limpias   # las LIMPIAS deben dar todo SANO
python gate/run_gate.py --fixtures rotas      # cada fixture ROTA da su rojo EXACTO
python gate/run_gate.py --fixtures ambas      # las dos + convergencia directa M1/M2
```
El gate es un camino feliz **y** un camino negativo: las fixtures **limpias** tienen que
seguir dando **SANO**, y las **rotas** tienen que seguir detectando su defecto exacto (§2, criterio 4).

**Paso 3 — Método 2: verificador independiente (segundo método).**
```bash
python gate/verificador_minimo.py
```
No reutiliza la agregación del runner: recomputa el veredicto por un camino propio y lo
contrasta contra el mismo `esperado.txt`. Si M1 y M2 divergen, es ROJO aunque cada uno por
separado parezca verde. En `--fixtures ambas` el propio `run_gate` ya cruza mapa-a-mapa M1 vs M2.

**Paso 4 — Criterio de no-regresión (qué debe seguir cierto).**
La subida se acepta **solo si**, tras el cambio de versión:
- **LIMPIAS → SANO.** Las fixtures limpias siguen agregando `SANO` en todos los detectores.
- **ROTAS → cada defecto detectado EXACTAMENTE.** Cada fixture rota sigue emitiendo el rojo
  que declara su `esperado.txt` (id de invariante + veredicto de detector), ni más ni menos.
  **Recuento verificado en vivo (09/07/2026):** hay **12 carpetas** en `gate/fixtures/rotas/`,
  cada una con su `esperado.txt`. Las **12** las consume el gate: tanto `run_gate.py`
  (`correr_rotas`) como `verificador_minimo.py` (método 2) recorren **todos** los subdirectorios
  de `rotas/` con `(FIXTURES/"rotas").iterdir()` — no hay lista fija, se itera el disco. Por eso
  el recuento es literalmente "contar las carpetas".
  - **11 fixtures rotas "clásicas"** (una por defecto de detector): `01_skill_invisible`
    (INV-R1), `02_colision_routing` (INV-R4), `03_wikilink_roto` (LINT-WIKILINK),
    `04_envelope_blocked_sin_summary` y `05_status_invalido` (RESULT-CONTRACT),
    `06_mdlink_roto` (LINT-MDLINK), `07_abspath_portabilidad` y `09_abspath_midline`
    (LINT-ABSPATH), `08_ragsec_rag_inexistente` (LINT-RAGSEC), `10_mdlink_basename_falso`
    (LINT-MDLINK), `11_wikilink_carpeta` (LINT-WIKILINK).
  - **+1 fixture con test dedicado:** `06_colision_routing_parcial` (INV-R4, Jaccard ~0.33).
    Se añadió como banco del test `gate/test_colision_parcial_config.py`, que ejercita casos de
    config que el gate por sí solo no cubre (`jaccard_warn` ausente / valor bool → `ConfigError`).
    **Matiz importante:** además de servir a ese test, el gate **también la consume** (está en
    `rotas/` con su `esperado.txt`, y ambos métodos iteran el disco). No es "solo del test": es
    **fixture-de-test que el gate también carga**. Verificado ejecutando el iterador en vivo.
  > **Nota de mantenimiento:** si se añaden o quitan fixtures rotas, este recuento y el del
  > ROADMAP deben re-verificarse; no fiar la cifra de este documento sin contar las carpetas
  > (`ls -d gate/fixtures/rotas/*/` → 12 a 09/07/2026). Distinguir "carpetas en disco" (12, todas
  > consumidas por el gate) de "clásicas de un solo defecto" (11).
- **Ambos métodos VERDE y convergentes.** M1 y M2 coinciden fixture a fixture.

**Paso 5 — Si degrada, revertir.**
Si cualquier criterio del paso 4 falla (una limpia deja de dar SANO, una rota deja de
detectar su defecto, o M1 y M2 divergen), **revertir la subida de versión** (volver al
intérprete/PyYAML anterior) y no adoptar el cambio. El kit no toca tu entorno (READ-ONLY),
así que revertir es volver a instalar la versión previa de la dependencia; no hay estado que
deshacer. Diagnosticar la causa antes de reintentar; no subir "a ver si esta vez pasa".

---

## 3. Última verificación en vivo (este ladrillo)

Ejecutado el **06/07/2026** desde la carpeta del kit, tras crear este documento (es inerte;
no toca código — la ejecución es no-regresión de fontanería):

- Entorno: **Python 3.14.6**, **PyYAML 6.0.3**.
- `python gate/run_gate.py --fixtures ambas` → `GATE (metodo 1 + convergencia directa m1/m2) VERDE` · exit 0.
- `python gate/verificador_minimo.py` → `VERIFICADOR MINIMO (metodo 2) VERDE` · exit 0.

Ambos métodos VERDE. Añade dos filas PROBADO a la matriz (Python 3.14, PyYAML 6.0.3) que no
constaban antes.

---

## 4. Por qué el pin `<7.0` — qué se rompe si sube PyYAML a 7.x

**El pin excluye 7.x a propósito.** Motivo de fondo: la serie 7.x de PyYAML es una versión
mayor y, como todo cambio de versión mayor, puede alterar el **contrato de carga** (los
*loaders*) del que depende `motor/config_loader.py`. El kit carga la config por el camino
**seguro** (`yaml.safe_load` / `SafeLoader`), no por el `Loader` inseguro por defecto que
las versiones históricas de PyYAML arrastraban. La familia de cambios que motiva el techo:

- **Endurecimiento / reordenación de los loaders.** PyYAML ha ido empujando desde hace años
  a que `load()` exija un `Loader` explícito y a que el camino por defecto sea el seguro. Un
  salto de versión mayor es el punto natural donde ese contrato puede **cambiar de firma o de
  comportamiento** (qué acepta `safe_load`, qué tipos construye, qué warnings pasan a error).
- **Riesgo concreto para este kit.** Si 7.x cambia cómo `safe_load` resuelve tipos escalares
  (fechas, `on/off`→bool, números), un `config/*.yaml` que hoy carga con un tipo podría
  cargar con otro, y el `config_loader` fail-fast (que aborta ante clave/tipo inesperado)
  podría empezar a **abortar sobre config que antes era válida** — o, peor, cargar un valor
  con el tipo equivocado sin avisar. Eso rompería el gate por un camino silencioso.

**Por eso el techo NO se sube a ciegas.** 7.x pasa de EXCLUIDO a candidato **solo** tras
correr el protocolo del §2 con PyYAML 7.x instalado y comprobar que:
1. las fixtures **limpias siguen dando SANO** (la config sigue cargando con los mismos
   tipos), y
2. las **12 rotas siguen detectando su defecto exacto** (las 11 clásicas + `06_colision_routing_parcial`,
   ver §2 paso 4), por **los dos métodos**.

Si eso se cumple, se amplía el pin a `<8.0` (o al techo verificado) y se anota PyYAML 7.x
como **PROBADO** en la matriz §1.2, con fecha. Hasta entonces, `<7.0` es la frontera segura:
lo verificado se soporta; lo no verificado se excluye, no se supone.

---

*UPGRADE.md · `agent-governance-checks` · creado 06/07/2026. Matriz basada en README/install/
ROADMAP + verificación en vivo (Python 3.14.6 · PyYAML 6.0.3, gate VERDE por 2 métodos). Datos
no constatados marcados NO VERIFICADO, no inventados. Cifra de fixtures rotas reconciliada
09/07/2026: **12 carpetas en disco**, todas consumidas por el gate (11 clásicas de un defecto +
`06_colision_routing_parcial`, que además tiene test dedicado). Recuentos previos "11" (este doc)
y "8" (ROADMAP) quedaban por detrás del disco; ahora ambos docs dicen 12.*
