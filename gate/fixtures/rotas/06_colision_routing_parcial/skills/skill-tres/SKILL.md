---
name: skill-tres
description: Detecta duplicados en un listado de facturas y propone conciliacion bancaria automatica.
---

# skill-tres

DEFECTO SEMBRADO (parte 1 de 2): descripcion PARCIALMENTE solapada con skill-cuatro
(Jaccard ~0.33, entre el umbral operativo 0.22 y el castrado 1.0). NO son identicas.
El router no puede desambiguar con fiabilidad -> INV-R4 (colision Jaccard) debe FALLAR
con el umbral operativo, y SEGUIR fallando pase lo que pase con la config (ver test).
