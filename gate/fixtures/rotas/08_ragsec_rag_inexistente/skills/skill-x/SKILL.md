---
name: skill-x
description: Skill sintetica que declara cargar un RAG que no existe en el corpus.
---

# skill-x

DEFECTO SEMBRADO: la seccion RAG de abajo nombra un fichero RAG que NO existe en el corpus.

## RAG QUE DEBES CARGAR

- `Guia_Que_No_Existe.md`

## Notas

lint_corpus debe cazar el RAG inexistente -> LINT-RAGSEC FALLA -> veredicto ENFERMO.
La skill SI esta en el registro (para que gate_routing quede SANO y solo dispare LINT-RAGSEC).
