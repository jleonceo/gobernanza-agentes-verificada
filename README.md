# gobernanza-agentes-verificada

**Un sistema de agentes de IA deja de funcionar como se diseñó sin dar un solo error. Esta
herramienta lo comprueba con código.**

[Español](#español) · [English](#english)

---

## Español

### El problema

Monta un sistema con varias habilidades de IA, cada una con su especialidad, y un repartidor
que decide cuál atiende cada petición. Funciona.

Meses después sigue funcionando. Pero ya no es el sistema que construiste. Una
habilidad dejó de recibir trabajo porque nadie regeneró la lista que el repartidor consulta.
Dos habilidades se describen de forma tan parecida que el repartidor las confunde. Media docena
de documentos apuntan a ficheros que se borraron hace semanas.

Nada de eso da un error. El sistema responde igual de rápido y con la misma cara de estar bien.
Por eso no se detecta mirando. Hay que medirlo.

### Dos casos reales, del sistema donde nació esta herramienta

**La habilidad que nadie llamaba.** El 21 de julio de 2026 descubrí que dos habilidades llevaban
semanas sin recibir un solo encargo. Existían en el disco, funcionaban al llamarlas a mano, y el
repartidor no sabía de ellas porque faltaban en su lista. Se descubrió por casualidad.

**El experto equivocado.** Ese mismo día, una pregunta sobre indemnización por despido se
enrutaba al experto contable en lugar de al de personal. Tres veces de tres. La causa no estaba
en la habilidad de personal. Estaba en que la del contable reclamaba las mismas palabras, y
nadie había escrito dónde acababa cada una.

Los dos fallos son exactamente lo que este kit detecta. Ninguno de los dos dio un error.

### Qué comprueba

Cinco detectores, todos de solo lectura y sin modelos de lenguaje:

| Detector | Qué encuentra |
|---|---|
| `gate_routing` | Habilidades que el repartidor no conoce, y pares de habilidades que no sabe distinguir |
| `lint_corpus` | Referencias y enlaces que apuntan a ficheros que ya no existen |
| `result_contract` | Entregas entre agentes sin el sobre obligatorio de estado, riesgo y resumen |
| `audit_chain` | Un registro de auditoría al que le falta un eslabón o le han cambiado el orden |
| `panel_salud` | Un panel que da verde agregando comprobaciones que en realidad no se ejecutaron |

### El verificador del verificador, que casi nadie incluye

Cualquier herramienta que emite un veredicto tiene el mismo problema. Si dice verde, ¿cómo sabes
que el verde es cierto y no un fallo de la propia herramienta?

Aquí hay dos caminos independientes. El primero recorre el sistema y emite su veredicto. El
segundo lo recalcula por su cuenta, sin importar nada del primero. **Si los dos no coinciden, el
resultado es rojo aunque por separado los dos digan verde.**

Es la doble comprobación de toda la vida, puesta en código en lugar de dejarla a la disciplina de
quien lo ejecuta.

### Cómo se usa

```
python gate/run_gate.py --fixtures ambas      # el gate completo, con sus casos de prueba
python gate/verificador_minimo.py             # el segundo método, independiente del primero
python ci_gate.py                             # los tres controles juntos, para integración continua
python contrato/result_contract.py sobre.json # validar el sobre de una entrega concreta
```

Instalación y configuración paso a paso en [install.md](install.md). Las reglas que cumple
cualquier detector nuevo están en [CONTRATO_DETECTOR.md](CONTRATO_DETECTOR.md).

### Qué NO hace

- **No usa IA.** Es código que lee ficheros y compara. Ahí está la gracia: da el mismo resultado
  hoy y dentro de seis meses, sin depender del modelo que tengas contratado.
- **No arregla nada.** Señala. Reparar exige conocer el sistema, y eso no lo sabe una herramienta.
- **No mide si tus agentes responden bien.** Mide si la instalación sigue entera. Para lo primero
  hay otros repos, enlazados abajo.

### Repos relacionados

| Repo | Qué cuenta |
|---|---|
| [gobernanza-skills-analiticas](https://github.com/jleonceo/gobernanza-skills-analiticas) | El método de gobernanza en prosa. Este repo es el código que lo comprueba |
| [guardianes-verificados-ia](https://github.com/jleonceo/guardianes-verificados-ia) | Guardianes probados con mutación. Mismo principio, otra capa del sistema |
| [orquestacion-enjambres-ia](https://github.com/jleonceo/orquestacion-enjambres-ia) | Cómo se decide a qué agente va cada petición |
| [verificacion-determinista-ia](https://github.com/jleonceo/verificacion-determinista-ia) | Comprobaciones sin IA sobre datos contables. Mismo principio, otro dominio |
| [llm-eval-contable](https://github.com/jleonceo/llm-eval-contable) | Cómo se evalúa si una habilidad responde bien |

---

## English

### The problem

You build a system with several AI skills, each one a specialist, plus a router that decides
which skill handles each request. It works.

Months later it still works. And yet it is no longer the system you built. One skill stopped
receiving work because nobody regenerated the list the router reads. Two skills are described so
similarly that the router cannot tell them apart. A handful of documents point to files deleted
weeks ago.

None of this raises an error. The system answers just as fast, looking just as healthy. You
cannot spot it by looking. You have to measure it.

### Two real cases, from the system this tool came from

**The skill nobody called.** On 21 July 2026 I found two skills that had gone weeks without a
single assignment. They existed on disk, they worked when called by hand, and the router did not
know about them because they were missing from its list. It was found by accident.

**The wrong expert.** That same day, a question about severance pay was routed to the accounting
expert instead of the HR one. Three times out of three. The cause was not the HR skill. It was
that the accounting one claimed the same words, and nobody had written down where each one ended.

Both failures are exactly what this kit detects. Neither raised an error.

### What it checks

Five detectors, all read-only, none of them using a language model:

| Detector | What it finds |
|---|---|
| `gate_routing` | Skills the router does not know about, and skill pairs it cannot tell apart |
| `lint_corpus` | Links and pointers to files that no longer exist |
| `result_contract` | Agent handoffs missing the required status, risk and summary envelope |
| `audit_chain` | An audit trail with a missing link or a reordered entry |
| `panel_salud` | A dashboard reporting green by aggregating checks that never actually ran |

### The verifier's verifier, which almost nobody ships

Any tool that issues a verdict has the same problem. If it says green, how do you know the green
is true and not a bug in the tool itself?

There are two independent paths here. The first walks the system and issues its verdict. The
second recomputes it on its own, importing nothing from the first. **If the two disagree, the
result is red even when each one says green on its own.**

It is plain double-checking, put into code instead of left to the discipline of whoever runs it.

### Usage

```
python gate/run_gate.py --fixtures ambas      # the full gate, with its test fixtures
python gate/verificador_minimo.py             # the second method, independent of the first
python ci_gate.py                             # all three checks, for continuous integration
python contrato/result_contract.py env.json   # validate one handoff envelope
```

Step by step setup in [install.md](install.md). The rules any new detector must satisfy are in
[CONTRATO_DETECTOR.md](CONTRATO_DETECTOR.md).

### What it does NOT do

- **No AI involved.** It is code that reads files and compares. That is the point: same result
  today and in six months, with no dependency on which model you pay for.
- **It fixes nothing.** It reports. Fixing requires knowing the system, which a tool does not.
- **It does not measure whether your agents answer well.** It measures whether the installation
  is still intact. For that, see the related repos below.

### Related repos

| Repo | What it covers |
|---|---|
| [gobernanza-skills-analiticas](https://github.com/jleonceo/gobernanza-skills-analiticas) | The governance method in prose. This repo is the code that checks it |
| [guardianes-verificados-ia](https://github.com/jleonceo/guardianes-verificados-ia) | Guards proven by mutation testing. Same principle, another layer |
| [orquestacion-enjambres-ia](https://github.com/jleonceo/orquestacion-enjambres-ia) | How each request is assigned to an agent |
| [verificacion-determinista-ia](https://github.com/jleonceo/verificacion-determinista-ia) | Checks without AI over accounting data. Same principle, another domain |
| [llm-eval-contable](https://github.com/jleonceo/llm-eval-contable) | How to evaluate whether a skill answers well |

---

*Licencia Apache 2.0 (ver [LICENSE](LICENSE)). Extraído de un sistema en producción y
publicado como kit independiente.*
