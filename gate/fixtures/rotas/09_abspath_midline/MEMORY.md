# MEMORY — fixture ROTA 09 (ruta absoluta en MITAD de linea)

DEFECTO SEMBRADO: la ruta absoluta no esta al inicio de linea sino en medio de la
prosa (el caso mas frecuente en notas reales: "vive en C:\...", "detalle en C:\..").
El patron anclado a '^' la dejaba pasar -> falso negativo D1 de la auditoria.

El detalle del informe vive en C:\datos\proyecto\fichero.md para consultarlo luego.

lint_corpus debe cazar la ruta absoluta aunque este a media linea -> LINT-ABSPATH
FALLA -> veredicto VIGILAR. Sin wikilinks ni mdlinks rotos (para aislar ABSPATH).
