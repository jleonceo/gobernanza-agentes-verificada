# -*- coding: utf-8 -*-
"""
envelope_schema.py — ESQUEMA TIPADO (Pydantic) del envelope del Result Contract.

ARTEFACTO DE PILOTO. NO cablea nada vivo. Es la pieza "aguas arriba" que el doc
de evaluación recomienda: el esquema que se pasaría a Structured Outputs de
Anthropic (output_format / output_config.format) para constreñir la GENERACIÓN
del envelope en origen. El validador determinista result_contract.py sigue siendo
el tirante aguas abajo; este esquema es el cinturón.

ANCLAJE (de dónde salen exactamente los campos y las reglas):
  - evals/result_contract.py  (validador vigente, versión pydantic):
        CAMPOS  = ("status","risk","skill_applied","summary","artifacts","next")   (:53)
        Status  = OK|WARN|BLOCKED|ERROR                                            (:39-43)
        Risk    = LOW|MEDIUM|HIGH|CRITICAL                                          (:46-50)
        summary/next no vacíos                                                      (:66-71)
        REGLA DURA: status ∈ {BLOCKED,ERROR} => len(summary.strip()) >= 15          (:73-83)
  - agent-governance-checks/contrato/result_contract.py (kit stdlib):
        MIN_SUMMARY_CORTE = 15                                                      (:54)
        STATUS_DE_CORTE = ("BLOCKED","ERROR")                                       (:48)
  - Evaluacion_Structured_Outputs_ResultContract_04072026.md §4.5.1:
        "Definir el esquema del envelope una sola vez como modelo Pydantic
         (los 6 campos, los 2 enums como Enum), reutilizando la definición que ya
         vive en evals/result_contract.py:39-64 para que el esquema del SDK y el
         validador determinista NO diverjan."

NOTA sobre nombres de campo: el contrato VIGENTE usa 'artifacts' y 'next' (NO
'files'/'verification'/'blocked_reason'). Este esquema refleja el contrato REAL en
vivo, no un contrato hipotético. El motivo del corte NO es un campo aparte: por
diseño del contrato viaja DENTRO de 'summary' (regla dura del corte). Eso se
documenta aquí para que el gate de Juan lo tenga a la vista.

Genera JSON Schema con:  EnvelopeResultContract.model_json_schema()
que es exactamente lo que se pasaría a  output_format={"type":"json_schema","schema": ...}.
"""

from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


# --- Enums del contrato (idénticos a evals/result_contract.py:39-50) --------

class Status(str, Enum):
    OK = "OK"
    WARN = "WARN"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


class Risk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# status que cortan el flujo: exigen summary con sustancia (no telegráfico).
STATUS_DE_CORTE = (Status.BLOCKED, Status.ERROR)
MIN_SUMMARY_CORTE = 15  # anclado a contrato/result_contract.py:54


# --- El envelope tipado -----------------------------------------------------

class EnvelopeResultContract(BaseModel):
    """
    Envelope del handoff del Result Contract v1.2, tipado para Structured Outputs.

    Los 6 campos son obligatorios (reflejo de CAMPOS en el validador vigente).
    'skill_applied' es booleano en el contrato (evals/result_contract.py:120-124
    parsea 'true'/'false'); el kit stdlib lo acepta también como str, pero el
    esquema tipado aguas arriba lo fija como bool para constreñir la generación.
    """

    model_config = {"extra": "forbid"}  # gramática estricta: sin campos de más

    status: Status = Field(description="Estado del handoff. Enum del contrato.")
    risk: Risk = Field(description="Nivel de riesgo. Enum del contrato.")
    skill_applied: bool = Field(description="Si se aplicó la skill del dominio.")
    summary: str = Field(description="Resumen; si el flujo se corta, explica el motivo.")
    artifacts: str = Field(description="Artefactos producidos por el handoff.")
    next: str = Field(description="Siguiente paso propuesto.")

    @field_validator("summary", "next")
    @classmethod
    def _no_vacio(cls, v, info):
        if not v or not v.strip():
            raise ValueError("'%s' no puede ir vacío" % info.field_name)
        return v

    @model_validator(mode="after")
    def _summary_explica_el_corte(self):
        # Regla dura del contrato: un corte (BLOCKED/ERROR) es lo único que el
        # orquestador muestra a Juan; el summary no puede ser telegráfico.
        if self.status in STATUS_DE_CORTE:
            if len(self.summary.strip()) < MIN_SUMMARY_CORTE:
                raise ValueError(
                    "status=%s exige un summary que explique el motivo del corte "
                    "(mínimo %d caracteres)" % (self.status.value, MIN_SUMMARY_CORTE)
                )
        return self


if __name__ == "__main__":
    import json
    # Imprime el JSON Schema que se pasaría a Structured Outputs (output_format).
    print(json.dumps(EnvelopeResultContract.model_json_schema(), indent=2, ensure_ascii=False))
