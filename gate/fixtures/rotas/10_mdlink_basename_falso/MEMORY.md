# MEMORY — fixture ROTA 10 (mdlink a ruta ERRONEA con basename existente)

DEFECTO SEMBRADO: el enlace apunta a 'carpeta_inexistente/Guia_Alfa.md', que NO
existe; el detector lo daba por bueno solo porque existe un 'Guia_Alfa.md' en otra
carpeta (rag/). Resolver por basename global = falso negativo D2 de la auditoria.

- Ver [la guia](carpeta_inexistente/Guia_Alfa.md).

lint_corpus debe cazar que la RUTA no existe -> LINT-MDLINK FALLA -> ENFERMO.
Sin wikilinks (para aislar MDLINK).
