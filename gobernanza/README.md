# Gobernanza — métricas DIU / CDL

Miden la **gobernanza misma**, no el corpus: cuando el sistema **defiere** una decisión al
humano (VÍA C), ¿esa deferencia **informa** o es **cortina**?

## Qué miden

Cada deferencia se puntúa en tres dimensiones [0,1]:

| dim | pregunta |
|---|---|
| `spec` | ¿dice **concretamente** qué información/decisión falta? |
| `causal` | ¿explica **por qué** se difiere (qué lo hace irreducible al sistema)? |
| `bshift` | ¿la deferencia **cambia el curso** frente a decidir por defecto? |

- **DIU** (Deferral Information Utilisation) = media de la media **geométrica**
  `(spec·causal·bshift)^(1/3)`. Geométrica a propósito: una dimensión floja **hunde** el
  término (no se compensa) → exige las tres no-nulas. ~1 = deferencias ricas.
- **CDL** (Cosmetic Deadlock rate) = fracción con `spec < θ OR causal < θ` (θ=0.3).
  Bajo = bueno; alto = se difiere por deferir. `bshift` **no** entra en CDL.

## Para qué sirve

Instrumento contra el **sobre-filtrado** (memoria `guardar-contra-sobrefiltrado`): si el
sistema para mucho a preguntar a Juan pero con **DIU bajo / CDL alto**, esas paradas son
ruido, no gobernanza → hay que **subir el listón** de "cuándo merece la pena parar".

## Uso

```
python gobernanza/metricas_gobernanza.py <deferencias.json> [--theta 0.3]
```

`deferencias.json` = lista de `{id, spec, causal, bshift}` (o `{"deferencias":[...]}`).
Módulo importable: `compute_diu`, `compute_cdl`, `evaluar`. **stdlib puro, READ-ONLY,
determinista, fail-fast** (puntuación fuera de [0,1] o dimensión ausente = error, sin clamp
silencioso). Tests: `python gobernanza/test_metricas_gobernanza.py`.

## Dogfooding (08/07/2026)

Sobre las deferencias reales a Juan de las sesiones 07-08/07 (`deferencias_sesion_ejemplo.json`):
**DIU 0.713 · CDL 0.000** → las deferencias informan y ninguna es cortina. (Muestra manual
ilustrativa; el log real se generaría instrumentando las deferencias VÍA C.)

## Prior art

Re-implementado desde la **fuente primaria** de `mech-gov-framework` de SantanderAI
(`metrics/governance/{diu,cdl}.py`), leída el 08/07 (`Radar_Santander_Seguimiento_08072026.md`
§2.4). Fórmulas re-escritas desde su descripción (media geométrica; θ=0.3 estándar), **no
copiadas**; θ es config-driven.

## Backlog (no en v1)

- Instrumentar la captura automática de deferencias VÍA C (hoy la puntuación es a mano).
- Otras métricas de `mech-gov` sin leer aún (ESD/FVS/IPI); commit-reveal E3 para verificadores
  duales (memoria/`Radar_Santander_Seguimiento_08072026.md` §3).
