# MEMORY — fixture ROTA 11 (wikilink al nombre de una CARPETA cualquiera)

DEFECTO SEMBRADO: [[rag]] apunta al nombre de la carpeta 'rag/', que contiene un
.md (Guia_Alfa.md) pero NO un 'rag.md' ni una skill 'rag'. El detector aceptaba el
nombre de CUALQUIER carpeta con un .md como destino valido -> falso negativo D3.

- [[rag]] — no hay rag.md ni skills/rag/SKILL.md; 'rag' es solo el nombre de una carpeta.

lint_corpus debe cazar el wikilink sin destino -> LINT-WIKILINK FALLA -> ENFERMO.
Sin mdlinks (para aislar WIKILINK).
