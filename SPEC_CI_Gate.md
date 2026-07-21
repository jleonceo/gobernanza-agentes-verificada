# SPEC. CI del gate (ci_gate.py)

> Entrada del DAG (enjambre-programador). Ladrillo `ROADMAP_App03` pendiente #1. Reversible, VÍA C = autónomo.

## Problema
Hoy el gate se ejecuta a mano; sin cadencia, la deriva de SANO→VIGILAR pasa desapercibida.

## Criterios de aceptación (la suite los verifica)
1. **`ci_gate.py`** (stdlib puro) en la raíz del kit: ejecuta `gate/run_gate.py` (fixtures limpias Y rotas) **y**
   `gate/verificador_minimo.py`, agrega los resultados y devuelve **exit 0 solo si TODO es verde/SANO**; exit≠0 en cuanto algo degrade.
2. Salida de **una línea** por check + un veredicto final legible (apto para hook de git / log de CI).
3. **NO modifica** el gate ni los detectores; solo los invoca (por subprocess o import). Determinista, sin red.
4. **Test:** un caso que confirme exit 0 con el repo limpio, y otro que (forzando un fixture degradado de forma efímera) confirme exit≠0. Limpia lo que ensucie.
5. **No-regresión:** `gate/run_gate.py` y `gate/verificador_minimo.py` siguen verde por su cuenta.

## Fuera de alcance
No tocar config/*.yaml ni la lógica de detección. Solo orquestar las corridas existentes.

---

## Adéndum 07/07/2026: tercer check: guardarraíl anti-drift doc↔kit

Tras la auditoría del 07/07 (pega #2, envoltura de producto), `ci_gate.py` orquesta un
**tercer check**: `gate/test_install_sincronizado.py` (install.md **y** README.md
sincronizados con el kit real: nº de detectores derivado de `run_gate.py`, config
requerida/opcional derivada de `config_loader`). Mismo contrato: exit 0 solo si los
3 checks son verdes. Los criterios 1-5 originales no cambian; el test del criterio 4
(`test_ci_gate.py`) no fija el número de checks, así que sigue verde sin tocar.
