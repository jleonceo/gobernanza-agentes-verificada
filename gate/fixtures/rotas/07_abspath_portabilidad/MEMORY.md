# MEMORY — fixture ROTA 07 (ruta absoluta = defecto de portabilidad)

DEFECTO SEMBRADO: la linea de abajo empieza por una ruta absoluta, que rompe la
portabilidad del corpus (no se movera de esta maquina).

C:\Users\alguien\corpus\nota.md

lint_corpus debe marcar la ruta absoluta -> LINT-ABSPATH FALLA -> veredicto VIGILAR
(severidad media: no rompe la fontaneria, pero es un defecto de portabilidad).

Nota: sin wikilinks ni mdlinks rotos, para que solo dispare LINT-ABSPATH.
