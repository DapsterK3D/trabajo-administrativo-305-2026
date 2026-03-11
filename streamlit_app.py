import json
import os
import re
from typing import Dict, Any, List

import streamlit as st

# -----------------------------
# CONFIGURACIÓN GENERAL
# -----------------------------
st.set_page_config(
    page_title="Contencioso-administrativa vs Civil",
    page_icon="⚖️",
    layout="centered"
)

st.title("⚖️ Contencioso-administrativa vs Civil")
st.subheader("¿A qué jurisdicción demandarás?")
st.caption(
    "Orientador interactivo para Colombia sobre controversias entre derecho administrativo "
    "y derecho privado, especialmente en materia de servicios públicos."
)

st.info(
    "Esta herramienta es académica y orientativa. No reemplaza asesoría jurídica profesional. "
    "Su resultado es preliminar y depende de la información suministrada."
)

# -----------------------------
# INTENTO DE CARGAR OPENAI
# -----------------------------
OPENAI_AVAILABLE = False
client = None
api_key = None

try:
    from openai import OpenAI  # type: ignore

    api_key = st.secrets.get("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY"))
    if api_key:
        client = OpenAI(api_key=api_key)
        OPENAI_AVAILABLE = True
except Exception:
    OPENAI_AVAILABLE = False
    client = None


# -----------------------------
# CONOCIMIENTO BASE COLOMBIA
# -----------------------------
PUBLIC_ENTITIES = [
    "ministerio", "superintendencia", "gobernación", "gobernacion", "alcaldía", "alcaldia",
    "departamento administrativo", "agencia nacional", "uae", "unidad administrativa",
    "instituto", "secretaría", "secretaria", "contraloría", "contraloria", "procuraduría",
    "procuraduria", "registraduría", "registraduria", "rama judicial", "consejo de estado",
    "fiscalía", "fiscalia", "defensoría", "defensoria", "personería", "personeria",
    "empresa industrial y comercial del estado", "eice", "establecimiento público",
    "establecimiento publico"
]

PRIVATE_FUNCTION_ENTITIES = [
    "cámara de comercio", "camara de comercio", "notaría", "notaria",
    "curaduría urbana", "curaduria urbana"
]

SERVICE_PUBLIC_ENTITIES = [
    "enel", "epm", "aguas de bogotá", "aguas de bogota", "triple a", "codensa",
    "empresa de acueducto", "empresa de energía", "empresa de energia",
    "operador postal", "empresa de telecomunicaciones", "claro", "movistar", "tigo",
    "vanti", "air-e", "afinia"
]

PUBLIC_SERVICE_KEYWORDS = [
    "energía", "energia", "acueducto", "alcantarillado", "aseo", "gas", "telecomunicaciones",
    "internet", "telefonía", "telefonia", "servicio público", "servicio publico",
    "servicios públicos", "servicios publicos", "postal", "correo", "conectividad"
]

ADMINISTRATIVE_ACTION_KEYWORDS = [
    "resolución", "resolucion", "acto administrativo", "sanción", "sancion",
    "recurso de reposición", "recurso de reposicion", "recurso de apelación",
    "recurso de apelacion", "certificación", "certificacion", "registro mercantil",
    "negó", "nego", "rechazó", "rechazo", "suspendió", "suspendio", "cortó", "corto",
    "decisión unilateral", "decision unilateral"
]

PRIVATE_DISPUTE_KEYWORDS = [
    "contrato", "incumplimiento", "daños", "daños y perjuicios", "daño", "perjuicios",
    "responsabilidad civil", "indemnización", "indemnizacion", "cobro", "factura",
    "relación de consumo", "relacion de consumo", "cláusula", "clausula",
    "mora", "pago", "obligación", "obligacion"
]


# -----------------------------
# FUNCIONES AUXILIARES
# -----------------------------
def normalize(text: str) -> str:
    return text.lower().strip() if text else ""


def contains_any(text: str, keywords: List[str]) -> bool:
    t = normalize(text)
    return any(k in t for k in keywords)


def classify_entity(entidad: str, actividad: str) -> Dict[str, Any]:
    entidad_n = normalize(entidad)
    actividad_n = normalize(actividad)

    naturaleza = "indeterminada"
    presta_servicio_publico = False
    ejerce_funcion_administrativa = False
    razones = []

    # Naturaleza pública
    if contains_any(entidad_n, PUBLIC_ENTITIES):
        naturaleza = "publica"
        razones.append("La entidad parece ser pública por su denominación.")

    # Entidades privadas que ejercen funciones públicas
    if contains_any(entidad_n, PRIVATE_FUNCTION_ENTITIES):
        if naturaleza == "indeterminada":
            naturaleza = "privada"
        ejerce_funcion_administrativa = True
        razones.append("La entidad parece ser privada pero ejerce funciones públicas o administrativas específicas.")

    # Prestación de servicios públicos
    if contains_any(entidad_n, SERVICE_PUBLIC_ENTITIES) or contains_any(actividad_n, PUBLIC_SERVICE_KEYWORDS):
        presta_servicio_publico = True
        razones.append("La entidad o su actividad parece estar vinculada a la prestación de un servicio público.")

    # Si la actividad menciona expresamente registro, certificación, vigilancia, inspección
    if any(word in actividad_n for word in ["registro", "certificación", "certificacion", "vigilancia", "inspección", "inspeccion", "control"]):
        ejerce_funcion_administrativa = True
        razones.append("La actividad descrita sugiere ejercicio de función administrativa.")

    return {
        "naturaleza": naturaleza,
        "presta_servicio_publico": presta_servicio_publico,
        "ejerce_funcion_administrativa": ejerce_funcion_administrativa,
        "razones": razones
    }


def classify_conduct(problema: str, documento: str) -> Dict[str, Any]:
    problema_n = normalize(problema)
    documento_n = normalize(documento)
    razones = []

    acto_o_conducta = "indeterminado"

    # Documento fuerte
    if any(word in documento_n for word in ["resolución", "resolucion", "acto administrativo"]):
        acto_o_conducta = "acto_administrativo"
        razones.append("El documento aportado parece ser un acto administrativo.")
    elif any(word in documento_n for word in ["factura", "recibo"]):
        acto_o_conducta = "facturacion_servicio_publico"
        razones.append("El documento aportado parece ser una factura o recibo.")
    elif "contrato" in documento_n:
        acto_o_conducta = "incumplimiento_contractual"
        razones.append("El documento aportado parece ser un contrato.")
    else:
        # Problema narrado
        if contains_any(problema_n, ["sanción", "sancion", "multa"]):
            acto_o_conducta = "sancion"
            razones.append("La situación descrita parece referirse a una sanción.")
        elif contains_any(problema_n, ["suspendió el servicio", "suspendio el servicio", "cortó el servicio", "corto el servicio", "me suspendieron el servicio", "me cortaron el servicio"]):
            acto_o_conducta = "suspension_o_corte_servicio"
            razones.append("La situación descrita parece referirse a suspensión o corte del servicio.")
        elif contains_any(problema_n, ["me cobraron", "cobro", "factura", "facturación", "facturacion"]):
            acto_o_conducta = "facturacion_servicio_publico"
            razones.append("La situación descrita parece referirse a facturación o cobro.")
        elif contains_any(problema_n, ["negó", "nego", "rechazó", "rechazo", "no me inscribió", "no me certificó", "no me certifico"]):
            acto_o_conducta = "negativa_registro_o_certificacion"
            razones.append("La situación descrita parece referirse a negativa de registro o certificación.")
        elif contains_any(problema_n, ["incumplió", "incumplio", "no cumplió", "no cumplio", "cláusula", "clausula", "contrato"]):
            acto_o_conducta = "incumplimiento_contractual"
            razones.append("La situación descrita parece referirse a incumplimiento contractual.")
        elif contains_any(problema_n, ["daño", "daños", "perjuicio", "perjuicios", "indemnización", "indemnizacion"]):
            acto_o_conducta = "responsabilidad_civil"
            razones.append("La situación descrita parece referirse a responsabilidad civil o perjuicios.")
        elif contains_any(problema_n, ["consumidor", "compra", "producto", "garantía", "garantia"]):
            acto_o_conducta = "relacion_de_consumo"
            razones.append("La situación descrita parece referirse a una relación de consumo.")

    return {
        "acto_o_conducta": acto_o_conducta,
        "razones": razones
    }


def heuristic_analysis(entidad: str, actividad: str, problema: str, documento: str) -> Dict[str, Any]:
    entity_data = classify_entity(entidad, actividad)
    conduct_data = classify_conduct(problema, documento)

    razones = entity_data["razones"] + conduct_data["razones"]

    return {
        "entidad_nombre": entidad.strip() if entidad else "No identificada",
        "entidad_naturaleza": entity_data["naturaleza"],
        "presta_servicio_publico": entity_data["presta_servicio_publico"],
        "ejerce_funcion_administrativa": entity_data["ejerce_funcion_administrativa"],
        "acto_o_conducta_principal": conduct_data["acto_o_conducta"],
        "documento_relevante": documento.strip() if documento else "No aportado",
        "razones_clave": razones if razones else ["No fue posible clasificar con plena precisión la información suministrada."],
        "nivel_confianza": "medio" if razones else "bajo"
    }


# -----------------------------
# EXTRACCIÓN CON IA (OPCIONAL)
# -----------------------------
def build_ai_prompt(entidad: str, actividad: str, problema: str, documento: str) -> str:
    return f"""
Eres un asistente académico experto en derecho colombiano.

Tu tarea es clasificar un caso de frontera entre derecho administrativo y derecho privado,
especialmente en materia de servicios públicos en Colombia.

Responde SOLO en JSON válido con esta estructura exacta:

{{
  "entidad_nombre": "string",
  "entidad_naturaleza": "publica|privada|mixta|indeterminada",
  "presta_servicio_publico": true,
  "ejerce_funcion_administrativa": true,
  "acto_o_conducta_principal": "acto_administrativo|sancion|facturacion_servicio_publico|suspension_o_corte_servicio|negativa_registro_o_certificacion|incumplimiento_contractual|responsabilidad_civil|relacion_de_consumo|cobro_privado|otro|indeterminado",
  "documento_relevante": "string",
  "razones_clave": ["string", "string"],
  "nivel_confianza": "alto|medio|bajo"
}}

Criterios:
- Si la entidad es ministerio, alcaldía, superintendencia, gobernación u otra entidad estatal, clasifícala como pública.
- Si es cámara de comercio, notaría o curaduría urbana, normalmente es privada, pero puede ejercer función administrativa.
- Si el caso surge de resolución, sanción, registro, certificación o decisión unilateral de autoridad, inclínate por acto administrativo.
- Si el caso surge de incumplimiento contractual, daños patrimoniales o relación de consumo, inclínate por derecho privado.
- Contexto exclusivo: Colombia.

Datos del caso:
Entidad: {entidad}
¿Qué hace la entidad?: {actividad}
¿Qué te hizo exactamente?: {problema}
Documento o soporte: {documento}
"""


def ai_analysis(entidad: str, actividad: str, problema: str, documento: str) -> Dict[str, Any]:
    if not OPENAI_AVAILABLE or client is None:
        raise RuntimeError("La integración con OpenAI no está disponible.")

    prompt = build_ai_prompt(entidad, actividad, problema, documento)

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )

    text = response.output_text.strip()

    # Intento de extraer JSON incluso si viene rodeado de texto
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        raise ValueError("La IA no devolvió un JSON reconocible.")

    data = json.loads(match.group(0))
    return data


# -----------------------------
# MOTOR DE DECISIÓN FINAL
# -----------------------------
def decide_jurisdiction(features: Dict[str, Any]) -> Dict[str, str]:
    naturaleza = features.get("entidad_naturaleza", "indeterminada")
    servicio_publico = features.get("presta_servicio_publico", False)
    funcion_admin = features.get("ejerce_funcion_administrativa", False)
    acto = features.get("acto_o_conducta_principal", "indeterminado")
    confianza = features.get("nivel_confianza", "bajo")

    # Regla 1: función administrativa o acto administrativo
    if funcion_admin or acto in ["acto_administrativo", "sancion", "negativa_registro_o_certificacion"]:
        return {
            "jurisdiccion": "Contencioso-administrativa",
            "explicacion": (
                "La controversia parece corresponder a la jurisdicción contencioso-administrativa, "
                "puesto que la entidad estaría ejerciendo función administrativa o la actuación "
                "discutida tiene apariencia de acto administrativo o de autoridad."
            ),
            "confianza": confianza
        }

    # Regla 2: entidad pública con actuación típica de autoridad
    if naturaleza == "publica" and acto not in ["incumplimiento_contractual", "responsabilidad_civil", "relacion_de_consumo", "cobro_privado"]:
        return {
            "jurisdiccion": "Contencioso-administrativa",
            "explicacion": (
                "La controversia parece corresponder a la jurisdicción contencioso-administrativa, "
                "porque la entidad identificada es pública y la actuación descrita no aparece, en principio, "
                "como una simple relación privada."
            ),
            "confianza": confianza
        }

    # Regla 3: conflictos privados claros
    if acto in ["incumplimiento_contractual", "responsabilidad_civil", "relacion_de_consumo", "cobro_privado"]:
        return {
            "jurisdiccion": "Civil / ordinaria",
            "explicacion": (
                "La controversia parece corresponder a la jurisdicción civil u ordinaria, "
                "puesto que se presenta como una relación privada, patrimonial, contractual "
                "o de responsabilidad civil."
            ),
            "confianza": confianza
        }

    # Regla 4: servicios públicos, zona gris
    if servicio_publico and acto in ["facturacion_servicio_publico", "suspension_o_corte_servicio"]:
        return {
            "jurisdiccion": "Probablemente contencioso-administrativa",
            "explicacion": (
                "El caso se ubica en una zona gris típica de los servicios públicos. "
                "Como la controversia surge de facturación, suspensión o corte del servicio, "
                "es probable que deba revisarse desde la jurisdicción contencioso-administrativa, "
                "aunque conviene examinar con detalle el documento emitido y el régimen especial aplicable."
            ),
            "confianza": confianza
        }

    # Regla 5: indeterminación
    return {
        "jurisdiccion": "Indeterminada / requiere revisión adicional",
        "explicacion": (
            "Con la información suministrada no es posible definir con seguridad la jurisdicción. "
            "Se requiere mayor precisión sobre la naturaleza de la entidad, el documento emitido y "
            "la actuación concreta."
        ),
        "confianza": confianza
    }


def render_result(features: Dict[str, Any], decision: Dict[str, str], source_label: str) -> None:
    st.success(f"Jurisdicción sugerida: {decision['jurisdiccion']}")
    st.markdown(f"**Explicación breve:** {decision['explicacion']}")
    st.markdown(f"**Nivel de confianza:** {decision['confianza']}")
    st.caption(f"Modo de análisis utilizado: {source_label}")

    with st.expander("Ver análisis jurídico del caso"):
        st.write(f"**Entidad identificada:** {features.get('entidad_nombre', 'No identificada')}")
        st.write(f"**Naturaleza de la entidad:** {features.get('entidad_naturaleza', 'Indeterminada')}")
        st.write(f"**Presta servicio público:** {features.get('presta_servicio_publico', False)}")
        st.write(f"**Ejerce función administrativa:** {features.get('ejerce_funcion_administrativa', False)}")
        st.write(f"**Acto o conducta principal:** {features.get('acto_o_conducta_principal', 'Indeterminado')}")
        st.write(f"**Documento relevante:** {features.get('documento_relevante', 'No aportado')}")
        st.write("**Razones clave:**")
        for r in features.get("razones_clave", []):
            st.write(f"- {r}")


# -----------------------------
# INTERFAZ
# -----------------------------
with st.form("case_form"):
    entidad = st.text_input(
        "1) ¿Qué entidad te causó el problema?",
        placeholder="Ejemplo: Enel, EPM, Cámara de Comercio de Bogotá, Superintendencia de Industria y Comercio..."
    )

    actividad = st.text_area(
        "2) ¿Qué hace esa entidad?",
        placeholder="Ejemplo: presta energía, registra comerciantes, vigila telecomunicaciones, presta internet..."
    )

    problema = st.text_area(
        "3) ¿Qué te hizo exactamente la entidad?",
        placeholder="Ejemplo: me suspendió el servicio, me negó un registro, incumplió un contrato, me sancionó..."
    )

    documento = st.text_input(
        "4) ¿Tienes algún documento o soporte?",
        placeholder="Ejemplo: resolución, factura, contrato, correo, respuesta escrita..."
    )

    usar_ia = st.checkbox(
        "Usar IA para interpretar el caso (si está disponible)",
        value=True
    )

    submitted = st.form_submit_button("Analizar caso")

if submitted:
    if not entidad.strip() or not actividad.strip() or not problema.strip():
        st.warning("Por favor completa al menos los tres primeros campos.")
    else:
        with st.spinner("Analizando el caso..."):
            features = None
            source_label = "Lógica jurídica interna"

            if usar_ia and OPENAI_AVAILABLE:
                try:
                    features = ai_analysis(entidad, actividad, problema, documento)
                    source_label = "IA + control jurídico"
                except Exception:
                    features = heuristic_analysis(entidad, actividad, problema, documento)
                    source_label = "Lógica jurídica interna (la IA no pudo procesar el caso)"
            else:
                features = heuristic_analysis(entidad, actividad, problema, documento)
                source_label = "Lógica jurídica interna"

            decision = decide_jurisdiction(features)
            render_result(features, decision, source_label)

st.divider()

with st.expander("¿Cómo funciona esta herramienta?"):
    st.write(
        """
        La app recibe una descripción sencilla del caso y analiza tres cosas:
        
        1. La entidad involucrada.
        2. La actividad que desarrolla.
        3. La actuación concreta que generó el conflicto.

        Con eso intenta identificar si el caso se acerca más a:
        - una controversia de función administrativa o acto administrativo,
        - o a una controversia privada, contractual o patrimonial.

        Si tienes configurada una API key de OpenAI, la herramienta puede usar IA para
        interpretar el lenguaje natural. Si no, funciona con una lógica jurídica interna de respaldo.
        """
    )

with st.expander("Advertencia metodológica"):
    st.write(
        """
        Este orientador está diseñado únicamente con fines académicos. 
        En Colombia existen zonas grises, especialmente en servicios públicos, donde la
        determinación de la jurisdicción puede depender del acto concreto, del régimen especial
        aplicable y de la jurisprudencia.
        """
    )