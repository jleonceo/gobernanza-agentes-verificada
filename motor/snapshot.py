#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
motor/snapshot.py — snapshot datado NORMALIZADO del resultado de un run.

MECANISMO del SPEC (cierra hueco #7, REPRODUCIBILIDAD BIT-A-BIT): el snapshot de un
run debe ser IGUAL byte a byte entre dos entornos si el corpus y la config son los
mismos. Para eso se normaliza en tres ejes (los tres del test de aceptación):

  (a) RUTAS RELATIVAS a la root de instalación — nunca absolutas (difieren por máquina).
  (b) ORDEN CANÓNICO: todo listado ordenado con `sorted` (claves de dict incluidas al
      serializar), nunca `os.listdir` crudo (el orden del filesystem varía entre FS).
  (c) EXCLUYE mtime y fecha de ejecución — son ruido de entorno, no fallo real.

Sin estas tres, el criterio de reproducibilidad falla por causas que NO son fallos
(falso-rojo simétrico al falso-verde de mtimes que el origen ya corrigió).

El snapshot lleva un campo `datado` con la fecha SOLO como metadato humano fuera del
bloque normalizado — de modo que `snapshot_normalizado()` (lo que se compara bit-a-bit)
NO lo incluye. Determinista, stdlib puro, READ-ONLY.
"""

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path


def _relativizar(valor, root):
    """Si `valor` es (o contiene) una ruta bajo `root`, la relativiza con '/' canónico.

    Recorre dicts/listas recursivamente. Una ruta absoluta que cuelga de root pasa a
    ser relativa y con separador '/' (POSIX) para que Windows y Linux coincidan. Una
    cadena que no es ruta se deja intacta.
    """
    if isinstance(valor, dict):
        return {k: _relativizar(v, root) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_relativizar(v, root) for v in valor]
    if isinstance(valor, Path):
        return _rel_str(valor, root)
    if isinstance(valor, str) and _parece_ruta(valor):
        try:
            return _rel_str(Path(valor), root)
        except ValueError:
            return valor.replace("\\", "/")
    return valor


def _parece_ruta(s):
    # Heurística conservadora: contiene separador y termina en un fichero conocido,
    # o es una ruta absoluta. Evita relativizar prosa que casualmente lleve una barra.
    if "\\" in s or "/" in s:
        return True
    return False


def _rel_str(p, root):
    """Ruta relativa a root con separador '/'; si no cuelga de root, devuelve el nombre."""
    p = Path(p)
    root = Path(root)
    try:
        rel = p.resolve().relative_to(root.resolve())
        return rel.as_posix()
    except (ValueError, OSError):
        # Fuera de root: nos quedamos con la representación POSIX del propio valor,
        # sin la parte de máquina, para no filtrar rutas absolutas del entorno.
        return p.as_posix()


def _veredicto_a_dict(v):
    """Serializa un Veredicto (dataclass) a dict ordenado y estable.

    El campo `detalle` es explicación HUMANA: se conserva pero NO participa en la
    comparación de veredictos (contrato §2). Aquí se incluye porque el snapshot es
    auditable; el gate compara ok/id/esperado/obtenido, no la prosa de `detalle`.
    """
    if is_dataclass(v):
        return asdict(v)
    if isinstance(v, dict):
        return v
    # namedtuple u objeto con _asdict()
    if hasattr(v, "_asdict"):
        return dict(v._asdict())
    raise TypeError("no sé serializar un veredicto de tipo %s" % type(v))


def construir_snapshot(root, veredictos, agregado, por_detector):
    """Construye el bloque NORMALIZADO (sin fecha) de un run.

    · root         : Path de la raíz del corpus (para relativizar).
    · veredictos   : lista de Veredicto del run completo.
    · agregado     : semáforo agregado (SANO/VIGILAR/ENFERMO).
    · por_detector : dict {nombre_detector -> semáforo} — ordenado canónicamente.

    Devuelve un dict determinista: mismas entradas -> mismo dict, sin mtime/fecha.
    Las listas de veredictos se ordenan por (id, ok, esperado, obtenido) para que el
    orden de emisión de los detectores no cambie el snapshot.
    """
    vlist = [_veredicto_a_dict(v) for v in veredictos]
    vlist = [_relativizar(d, root) for d in vlist]
    vlist.sort(key=lambda d: (str(d.get("id")), bool(d.get("ok")),
                              str(d.get("esperado")), str(d.get("obtenido"))))
    detectores = {k: por_detector[k] for k in sorted(por_detector)}
    return {
        "agregado": agregado,
        "detectores": detectores,
        "veredictos": vlist,
    }


def snapshot_normalizado(root, veredictos, agregado, por_detector):
    """Serializa el snapshot normalizado a JSON canónico (comparable BIT-A-BIT).

    `sort_keys=True` + `ensure_ascii=False` + separadores fijos: dos runs equivalentes
    producen exactamente la misma cadena. NO incluye fecha ni mtime — es el bloque que
    el test de aceptación compara entre entorno-A y entorno-B.
    """
    bloque = construir_snapshot(root, veredictos, agregado, por_detector)
    return json.dumps(bloque, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"))


def snapshot_datado(root, veredictos, agregado, por_detector):
    """Snapshot para archivo humano: el bloque normalizado + un sello de fecha APARTE.

    El sello va en una clave `datado` HERMANA del bloque normalizado, no dentro de él:
    quien compara bit-a-bit usa `snapshot_normalizado()` (sin fecha); quien archiva para
    auditoría humana usa esto y ve cuándo se tomó. Así la fecha nunca contamina la
    comparación de reproducibilidad.
    """
    return {
        "datado": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "normalizado": construir_snapshot(root, veredictos, agregado, por_detector),
    }
