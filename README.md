# gobernanza-agentes-verificada

**Las reglas que escribes para un sistema de agentes de IA no las cumple nadie mientras no haya
algo que las imponga. Este kit es ese algo: código que mide si el sistema sigue siendo el que
montaste, y contesta con un veredicto.**

[Español](#español) · [English](#english)

---

## Español

### El problema

Cuando un frigorífico se apaga del todo, alguien lo nota en dos horas: deja de zumbar, la luz no
se enciende y se abre para mirar. Cuando lo que se estropea es el termostato, sigue zumbando con
su luz puesta, y lo que avisa una semana después es la leche cortada.

Casi todo el software falla de la primera manera, y por eso llevamos décadas confiando en que el
error salte solo. Un sistema montado con varias habilidades de inteligencia artificial, cada una
especializada en su materia, falla de la segunda.

En un sistema así hay un **enrutador**, que es la pieza encargada de decidir cuál de las
habilidades atiende cada petición, y que trabaja como quien mira una lista de extensiones pegada
al lado de la centralita. Contratan a una perito, nadie añade su extensión al papel, y las
llamadas de peritajes las sigue cogiendo el de siniestros, que se defiende bastante bien con ellas
y no se queja de nada. Ese teléfono no suena en cuatro meses, y el daño lleva ahí desde el primer
día con forma de normalidad.

Con los meses se tuercen solas tres cosas. Una habilidad deja de recibir encargos porque nadie
regeneró la lista que el enrutador consulta. Dos habilidades acaban descritas con palabras tan
parecidas que el enrutador ya no las distingue, y el trabajo se va siempre a la misma. Media
docena de documentos internos siguen citando ficheros que se borraron hace semanas.

Ninguna de las tres da un error. El sistema responde igual de rápido y con la misma cara de estar
sano, de modo que mirarlo no sirve de nada: hay que medirlo con algo que no dependa de que ese día
estuvieras atento.

### Un ejemplo que se ejecuta en medio segundo

Dentro del repositorio hay carpetas con un defecto plantado a propósito. Cada una es una **fixture
rota**: un sistema en miniatura con una avería sembrada y, al lado, un fichero que declara el rojo
exacto que esa avería tiene que provocar. Sirven para comprobar que la alarma suena, porque una
alarma que nunca ha sonado no demuestra nada.

La de `gate/fixtures/rotas/01_skill_invisible/` contiene una habilidad llamada `skill-fantasma`,
con su ficha en regla y su descripción escrita, que no figura en el registro de al lado. Funciona
perfectamente si la llamas a mano; sencillamente, el enrutador no sabe que existe.

Le pides al kit que examine esa carpeta:

```
python gate/run_gate.py --root gate/fixtures/rotas/01_skill_invisible
```

Y contesta:

```
DEFECTOS: INV-R1
  - INV-R1: skills con descriptor y ausentes del registro de routing: skill-fantasma
CORPUS ...01_skill_invisible -> ENFERMO  (audit_chain=SANO; gate_routing=ENFERMO;
lint_corpus=SANO; panel_salud=SANO; result_contract=SANO)
```

Ahí está el kit entero en cuatro líneas. Le señalas la carpeta donde vive tu sistema de agentes,
recorre lo que hay dentro y devuelve un semáforo escrito (`SANO`, `VIGILAR` o `ENFERMO`) con el
nombre del defecto y el de la pieza que lo arrastra. Ningún modelo de lenguaje interviene en el
camino, que es la razón de que conteste hoy lo mismo que dentro de seis meses.

### Los dos fallos reales que lo originaron

**La habilidad invisible (24 de junio de 2026).** Una habilidad quedó fuera del registro que el
enrutador consulta y dejó de recibir encargos. Existía en el disco, tenía su descripción y
funcionaba al llamarla a mano. La avería se descubrió por casualidad, y hoy está anotada en el
comentario de cabecera del propio detector que la busca.

**El experto equivocado (21 de julio de 2026).** Una pregunta sobre indemnización por despido se
enrutaba al experto contable en lugar de al de personal, tres veces de tres. La causa vivía en la
ficha de al lado: la del contable reclamaba en su frase las palabras «nóminas, Seguridad Social»
sin aclarar que lo suyo era contabilizarlas. Nunca se escribió dónde acababa cada una. Ese mismo
día se contaron cinco habilidades que perdían encargos por descripciones que colisionaban.

Los dos fallos son exactamente lo que este kit detecta. Ninguno de los dos dio un error.

### Qué comprueba

Un **detector** es un programa pequeño que busca un solo tipo de defecto, lee sin escribir nada y
devuelve su veredicto. Aquí hay cinco detectores, todos de solo lectura y ninguno de ellos con un
modelo de lenguaje dentro:

| Detector | Qué encuentra |
|---|---|
| `gate_routing` | Habilidades que el enrutador no conoce, y pares que ya no distingue |
| `lint_corpus` | Referencias y enlaces que apuntan a ficheros que ya no existen |
| `result_contract` | Entregas entre habilidades sin el sobre obligatorio de estado, riesgo y resumen |
| `audit_chain` | Un registro de auditoría al que le falta un eslabón o le han cambiado el orden |
| `panel_salud` | Un panel que da verde agregando comprobaciones que en realidad no se ejecutaron |

**La colisión de descripciones.** Cada habilidad se presenta con una frase que dice de qué se
ocupa, y de esas frases se fía el enrutador para repartir. Para medir el parecido, el kit reduce
cada frase a su lista de palabras y calcula qué porcentaje de palabras comparten las dos listas.
Avisa por encima del 22 por ciento, un umbral que vive en `config/umbrales.yaml` y que se sube o
se baja sin tocar el programa.

**El sobre de la entrega.** Cuando una habilidad termina y le pasa el trabajo a otra, adjunta un
sobre: una ficha breve con el estado de la entrega, el riesgo y un resumen. La regla dura del kit
es que un estado de bloqueo o de error obliga a rellenar el resumen, porque un bloqueo sin
explicación equivale a no haber avisado. En `gate/fixtures/rotas/04_envelope_blocked_sin_summary/`
hay uno declarado bloqueado y de riesgo alto con el resumen en blanco:

```
python contrato/result_contract.py gate/fixtures/rotas/04_envelope_blocked_sin_summary/envelope.json

ESTADO: INVALIDO
  ERROR: 'summary' no puede ir vacio
  ERROR: status=BLOCKED exige un summary que explique el motivo del corte
         (minimo 15 caracteres; se muestra al humano)
```

El segundo motivo aclara para quién era ese resumen que falta: se le muestra a la persona que
tiene que decidir.

**La cadena de auditoría.** Un registro de auditoría apunta, entrada por entrada, qué hizo el
sistema y cuándo. Aquí cada entrada lleva calculada una huella de la anterior, de manera que van
encadenadas: si alguien borra una del medio, reordena dos o retoca una, las huellas dejan de casar
y se ve dónde.

### El verificador del verificador

Cualquier herramienta que emite un veredicto arrastra el mismo agujero: si dice verde, ¿cómo sabes
que el verde es cierto y no un fallo de la propia herramienta?

Aquí hay dos caminos escritos por separado. El primero recorre el sistema con su motor y emite su
veredicto; el segundo lo recalcula con código propio, sin importar nada del primero, y después se
comparan resultado contra resultado. **Si los dos discrepan, el veredicto es rojo aunque cada uno
por su lado diga verde.**

Es la doble comprobación de toda la vida, puesta en código en lugar de dejarla a la disciplina de
quien lo ejecuta. La promesa se probó estropeando una pieza del primer camino, la que resume el
estado de cada detector: el primer camino se declaró verde, el segundo también, y la comparación
de los dos los delató fixture a fixture con siete líneas de divergencias.

### Cómo se usa

Un **gate** es una puerta de paso: devuelve un cero cuando todo está en orden y un uno cuando algo
falla, que es como un programa le dice a otro «sigue» o «para», y con eso se cuelga de un proceso
automático que lo ejecute solo.

```
python ci_gate.py                             # los tres controles juntos, medio segundo
python gate/run_gate.py --fixtures ambas      # el gate completo sobre sus casos de prueba
python gate/run_gate.py --root <tu_carpeta>   # el gate sobre TU sistema
python gate/verificador_minimo.py             # el segundo método, independiente del primero
python contrato/result_contract.py sobre.json # validar el sobre de una entrega concreta
```

Instalación y configuración paso a paso en [install.md](install.md). Las reglas que cumple
cualquier detector nuevo están en [CONTRATO_DETECTOR.md](CONTRATO_DETECTOR.md).

### Qué está medido

Ejecutado el 22/07/2026 con Python 3.14.6, sin copiar ninguna cifra de la documentación:

| Comprobación | Resultado |
|---|---|
| `ci_gate.py`, los tres controles | `CI-GATE VERDE: 3/3` |
| `run_gate.py --fixtures ambas` | verde |
| Las pruebas del repositorio | 49 pasan, 0 fallan, en 2,76 segundos |
| Los diecisiete defectos plantados | los diecisiete dan su rojo exacto |
| Sobre un sistema real de 51 habilidades | `ENFERMO`, con dos punteros colgantes nombrados |

El contenido son 5.068 líneas de programa entre cinco detectores, el motor que los ejecuta y
diecinueve casos de prueba, de los cuales diecisiete llevan su defecto sembrado.

Y una medición que interesa más que la tabla. Cada detector se dejó ciego por turnos, haciendo que
contestara «todo bien» pasara lo que pasara, para ver a cuáles echa de menos el conjunto:

| Detector dejado ciego | El conjunto |
|---|---|
| routing (habilidades invisibles) | se pone rojo; cazado |
| enlaces y punteros del corpus | se pone rojo; cazado |
| sobres de entrega | se pone rojo; cazado |
| cadena de auditoría | se pone rojo; cazado |
| panel de salud | **sigue verde** |

Cuatro de los cinco están protegidos por algún defecto sembrado que los obliga a hablar. Al panel
de salud no le toca ninguno de los diecisiete, porque solo aparece en el caso limpio esperando un
verde, así que puede apagarse entero sin que nada chille. Queda escrito aquí porque un semáforo en
verde vale lo que valgan sus controles negativos, y a este le falta uno.

### Sus límites

**Lo que mide es la instalación.** Comprueba que cada pieza está donde dice estar y que se
referencian bien entre ellas. Si tus agentes contestan bien o mal es otra pregunta, con otras
herramientas: los repos de abajo cubren esa.

**Un puntero puede estar vivo fuera del mapa.** Al ejecutarlo contra un sistema real señaló dos
documentos citados por una habilidad y ausentes de la carpeta. Existen los dos, en otro proyecto.
El aviso es literalmente cierto y engaña: dice «no está en el corpus» y se lee «lo borraron».

**Avisa de más en la portabilidad.** En ese mismo sistema marcó 26 ficheros por llevar dentro
rutas de un ordenador concreto, cosa que es verdad y es un defecto de fondo, aunque revisarlos uno
por uno lleva una tarde.

**La cadena de auditoría detecta el retoque y no lo impide.** Caza que alguien cambie o reordene
lo ya escrito; que alguien corte las últimas entradas queda fuera de su alcance en esta versión, y
así está declarado en su documentación, con una carpeta de prueba que lo demuestra.

**Hay que decirle dónde está cada cosa.** Apuntarlo a un sistema real costó cambiar dos líneas de
configuración, sin tocar el programa por ninguna de ellas. Sigue siendo trabajo previo.

**Señala el defecto y no lo repara.** Su trabajo termina al nombrarlo; decidir qué se cambia exige
conocer el sistema, cosa que ninguna herramienta puede hacer por ti.

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

When a fridge dies outright, somebody notices within two hours: it stops humming, the light stays
off, and it gets opened. When what breaks is the thermostat, it keeps humming with its light on,
and the warning that arrives a week later is the milk gone sour.

Almost all software fails the first way, which is why we have spent decades trusting the error to
raise itself. A system built out of several artificial intelligence skills, each one a specialist,
fails the second way.

Such a system has a **router**, the piece in charge of deciding which skill handles each request,
working much like whoever reads the list of extensions taped next to the switchboard. A loss
adjuster is hired, nobody adds her extension to the sheet, and the adjusting calls keep being
answered by the claims desk, which copes reasonably well and never complains. That phone does not
ring for four months, and the damage has been there since day one wearing the face of normality.

Over the months three things bend on their own. One skill stops receiving work because nobody
regenerated the list the router reads. Two skills end up described in words so alike that the
router can no longer tell them apart, and the work always goes to the same one. A handful of
internal documents keep citing files deleted weeks ago.

None of the three raises an error. The system answers just as fast and looks just as healthy, so
looking at it gets you nowhere: you have to measure it with something that does not depend on you
paying attention that day.

### An example that runs in half a second

Inside the repository there are folders with a defect planted on purpose. Each one is a **broken
fixture**: a miniature system with a seeded fault and, beside it, a file declaring the exact red
that fault must produce. They exist to prove the alarm rings, because an alarm that has never gone
off proves nothing.

The one in `gate/fixtures/rotas/01_skill_invisible/` holds a skill called `skill-fantasma`, with
its card in order and its description written, that does not appear in the registry next to it. It
works perfectly when called by hand; the router simply does not know it exists.

You point the kit at that folder:

```
python gate/run_gate.py --root gate/fixtures/rotas/01_skill_invisible
```

And it answers:

```
DEFECTOS: INV-R1
  - INV-R1: skills con descriptor y ausentes del registro de routing: skill-fantasma
CORPUS ...01_skill_invisible -> ENFERMO  (audit_chain=SANO; gate_routing=ENFERMO;
lint_corpus=SANO; panel_salud=SANO; result_contract=SANO)
```

That is the whole kit in four lines. You point it at the folder where your agent system lives; it
walks what is inside and returns a written traffic light (`SANO`, `VIGILAR` or `ENFERMO`) with the
name of the defect and of the piece carrying it. No language model takes part along the way, which
is why it returns the same result today and six months from now.

### The two real failures behind it

**The invisible skill (24 June 2026).** A skill fell out of the registry the router reads and
stopped receiving work. It existed on disk, it had its description and it worked when called by
hand. The fault was found by accident. It is written today in the header comment of the very
detector that looks for it.

**The wrong expert (21 July 2026).** A question about severance pay was routed to the accounting
expert instead of the HR one, three times out of three. The cause lived in the card next door: the
accounting one claimed the words "payroll, Social Security" in its own sentence without stating
that its part was recording them in the books. Nobody had written down where each one ended. That
same day, five skills were found losing work to colliding descriptions.

Both failures are exactly what this kit detects. Neither of them raised an error.

### What it checks

A **detector** is a small program that looks for one single kind of defect, reads without writing
anything, and returns its verdict. There are five of them here, all read-only, none carrying a
language model inside:

| Detector | What it finds |
|---|---|
| `gate_routing` | Skills the router does not know about, and pairs it cannot tell apart |
| `lint_corpus` | Links and pointers to files that no longer exist |
| `result_contract` | Skill handoffs missing the required status, risk and summary envelope |
| `audit_chain` | An audit trail with a missing link or a reordered entry |
| `panel_salud` | A dashboard reporting green by aggregating checks that never actually ran |

**Colliding descriptions.** Each skill introduces itself with a sentence stating what it covers,
and those sentences are what the router trusts when it assigns work. To measure how alike two of
them are, the kit reduces each sentence to its list of words and computes what percentage of words
the two lists share. It warns above 22 per cent, a threshold living in `config/umbrales.yaml` that
you raise or lower without touching the program.

**The handoff envelope.** When a skill finishes and passes the work to another, it attaches an
envelope: a short card with the status of the handoff, the risk and a summary. The kit's hard rule
is that a blocked or errored status forces the summary to be filled, because a block without an
explanation amounts to no warning at all. In
`gate/fixtures/rotas/04_envelope_blocked_sin_summary/` there is one declared blocked and high risk
with the summary left empty:

```
python contrato/result_contract.py gate/fixtures/rotas/04_envelope_blocked_sin_summary/envelope.json

ESTADO: INVALIDO
  ERROR: 'summary' no puede ir vacio
  ERROR: status=BLOCKED exige un summary que explique el motivo del corte
         (minimo 15 caracteres; se muestra al humano)
```

The second reason spells out who that missing summary was for: it is shown to the person who has
to decide.

**The audit chain.** An audit trail records, entry by entry, what the system did and when. Here
each entry carries a computed fingerprint of the previous one, so they run chained together: if
somebody deletes one from the middle, reorders two or edits one, the fingerprints stop matching
and it shows where.

### The verifier's verifier

Any tool that issues a verdict carries the same hole: if it says green, how do you know the green
is true and not a bug in the tool itself?

There are two paths here, written separately. The first walks the system with its engine and
issues its verdict; the second recomputes it with its own code, importing nothing from the first,
and then the two results are compared against each other. **If the two disagree, the verdict is
red even when each one says green on its own.**

It is ordinary double-checking, written into the code instead of left to the discipline of
whoever runs it. The promise was tested by breaking one piece of the first path, the one
summarising each detector's status: the first path declared itself green, the second did too, and
comparing them gave away the difference fixture by fixture in seven lines.

### Usage

A **gate** is a checkpoint: it returns a zero when everything is in order and a one when something
fails, which is how one program tells another "carry on" or "stop". That is what lets you hang the
kit off an automated process that runs it for you.

```
python ci_gate.py                             # all three checks together, half a second
python gate/run_gate.py --fixtures ambas      # the full gate over its own test fixtures
python gate/run_gate.py --root <your_folder>  # the gate over YOUR system
python gate/verificador_minimo.py             # the second method, independent of the first
python contrato/result_contract.py env.json   # validate one handoff envelope
```

Step by step setup in [install.md](install.md). The rules any new detector must satisfy are in
[CONTRATO_DETECTOR.md](CONTRATO_DETECTOR.md).

### What has been measured

Run on 22/07/2026 with Python 3.14.6, with no figure copied from the documentation:

| Check | Result |
|---|---|
| `ci_gate.py`, the three controls | `CI-GATE VERDE: 3/3` |
| `run_gate.py --fixtures ambas` | green |
| The repository test suite | 49 pass, 0 fail, in 2.76 seconds |
| The seventeen planted defects | all seventeen produce their exact red |
| Against a real system of 51 skills | `ENFERMO`, naming two dangling pointers |

The contents are 5,068 lines of program across five detectors, the engine that runs them and
nineteen test cases, seventeen of which carry a seeded defect.

And one measurement that matters more than the table. Each detector was blinded in turn, made to
answer "all fine" whatever happened, to see which ones the whole misses:

| Detector blinded | The whole |
|---|---|
| routing (invisible skills) | turns red; caught |
| corpus links and pointers | turns red; caught |
| handoff envelopes | turns red; caught |
| audit chain | turns red; caught |
| health dashboard | **stays green** |

Four of the five are protected by some seeded defect that forces them to speak. None of the
seventeen touches the health dashboard, which only appears in the clean case awaiting a green, so
it can be switched off entirely without anything squealing. This is written here because a green
traffic light is worth whatever its negative controls are worth. This one is missing one.

### Its limits

**What it measures is the installation.** It checks that each piece is where it says it is and
that they reference each other correctly. Whether your agents answer well is a different question,
for different tools: the repos below cover that one.

**A pointer can be alive outside the map.** Run against a real system, it flagged two documents
cited by a skill and absent from the folder. Both exist, in another project. The warning is
literally true and misleading: it says "not in the corpus" and gets read as "it was deleted".

**It over-warns on portability.** In that same system it flagged 26 files for carrying one
particular machine's paths inside them, which is true and is a genuine defect, though reviewing
them one by one takes an afternoon.

**The audit chain detects tampering and does not prevent it.** It catches anyone changing or
reordering what is already written; anyone truncating the last entries falls outside its reach in
this version. Its own documentation declares that limit, with a test folder proving it.

**You have to tell it where everything is.** Pointing it at a real system took changing two
configuration lines, without touching the program for either of them. It is still work up front.

**It names the defect and does not repair it.** Its job ends at naming it; deciding what to change
demands knowing the system, which no tool can do for you.

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
