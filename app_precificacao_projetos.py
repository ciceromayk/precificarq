# app_precificacao_projetos.py
# -------------------------------------------------------------
# APLICATIVO STREAMLIT PARA PRECIFICAÇÃO DE PROJETOS
# Baseado na metodologia das Tabelas de Honorários do CAU/BR (Módulo II)
# Fórmula (Módulo II – Condições Gerais): PV = Sc × BH × (fp × R)
# Onde: R = Sp/Sc, e Sp = Snr + (Sr × r)
# -------------------------------------------------------------
# NOTA IMPORTANTE:
# - Este app implementa a FÓRMULA BÁSICA e os conceitos STRUCTURAIS do Módulo II.
# - As TABELAS (BH por tipologia/estado, fp por faixas de área, r por número de repetições)
#   variam conforme o Módulo I/Anexos do CAU/BR e devem ser informadas pelo usuário
#   ou carregadas via planilha para aderência total à norma.
# - Incluímos utilitários para INTERPOLAR fp e para CALCULAR r por estimativa — ambos
#   opcionais — para facilitar no dia a dia quando as tabelas não estiverem à mão.
# -------------------------------------------------------------

import io
import math
import json
import datetime as dt
from typing import Optional, Dict

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Precificação de Projetos — CAU/BR", page_icon="📐", layout="wide")

# ----------------------
# SIDEBAR / IDENTIDADE
# ----------------------
st.sidebar.title("📐 Precificação de Projetos — CAU/BR")
st.sidebar.caption(
    "App de apoio ao cálculo de honorários. Informe BH, fp e parâmetros de área conforme as Tabelas do CAU/BR."
)

# ----------------------
# HELPERS
# ----------------------

def interpolate_fp(fp1: float, fp2: float, sc1: float, sc2: float, sc: float) -> float:
    """Interpolação linear de fp entre dois pontos (sc1->fp1) e (sc2->fp2).
    Fórmula sugerida no Módulo II: fp = fp1 - {(fp1-fp2) × [(Sc-Sc1)/(Sc2-Sc1)]}
    """
    if sc1 == sc2:
        return fp1
    return fp1 - ((fp1 - fp2) * ((sc - sc1) / (sc2 - sc1)))


def estimate_r_by_repetition(q: int) -> float:
    """Estimativa prática de redutor r para áreas repetidas (quando a tabela oficial não estiver disponível).
    Ajuste conforme sua política interna. Retorne entre 0 e 1.
    """
    if q <= 1:
        return 1.0  # Sem repetição: r = 1 (área repetida vira efetivamente não-repetida)
    if 2 <= q <= 4:
        return 0.70
    if 5 <= q <= 8:
        return 0.60
    if 9 <= q <= 16:
        return 0.50
    if 17 <= q <= 32:
        return 0.40
    return 0.35


def compute_R(snr: float, sr: float, r: float, sc: float) -> float:
    sp = snr + (sr * r)
    return (sp / sc) if sc else 0.0


def compute_PV(sc: float, bh: float, fp: float, R: float) -> float:
    return sc * bh * (fp * R)


# ----------------------
# DADOS DE ENTRADA
# ----------------------
colA, colB, colC = st.columns([1.2, 1, 1])

with colA:
    st.subheader("1) Parâmetros Gerais")
    projeto = st.text_input("Nome do Projeto", value="Edifício Residencial Exemplo")
    cliente = st.text_input("Cliente / Contratante", value="IDIBRA / Exemplo")
    uf = st.selectbox("UF do empreendimento", options=[
        "AC","AL","AP","AM","BA","CE","DF","ES","GO","MA","MT","MS","MG","PA",
        "PB","PR","PE","PI","RJ","RN","RS","RO","RR","SC","SP","SE","TO"
    ], index=6)
    tipologia = st.text_input("Tipologia (livre)", value="Residencial multifamiliar")

with colB:
    st.subheader("2) Áreas (m²)")
    sc = st.number_input("Sc — Área construída estimada (TOTAL)", min_value=0.0, value=5000.0, step=10.0)
    snr = st.number_input("Snr — Área NÃO repetida", min_value=0.0, value=1500.0, step=10.0)
    sr = st.number_input("Sr — Área repetida", min_value=0.0, value=3500.0, step=10.0)

with colC:
    st.subheader("3) Repetição (r)")
    mode_r = st.radio("Como obter o redutor r?", ["Informar manualmente", "Estimar por nº de repetições (q)"])
    if mode_r == "Informar manualmente":
        r = st.slider("r — Redutor para áreas repetidas (0 a 1)", min_value=0.0, max_value=1.0, value=0.6, step=0.01)
        q = None
    else:
        q = st.number_input("q — Nº de repetições (ex.: nº de pavimentos-tipo)", min_value=1, value=8, step=1)
        r = estimate_r_by_repetition(q)
        st.info(f"r estimado = {r:0.2f} (ajuste conforme as Tabelas oficiais)")

R = compute_R(snr, sr, r, sc)

st.divider()

col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    st.subheader("4) BH — Base de Honorários")
    st.caption("Valor conforme Módulo I — Anexo I (Base de Honorários por tipologia/estado). Informe manualmente ou carregue tabela.")
    bh = st.number_input("BH (R$/m²)", min_value=0.0, value=120.0, step=1.0)

with col2:
    st.subheader("5) fp — Fator Percentual")
    fp_mode = st.radio("Como obter fp?", ["Informar manualmente", "Interpolar entre duas faixas (Sc1→fp1; Sc2→fp2)"])
    if fp_mode == "Informar manualmente":
        fp = st.number_input("fp (fator adimensional; ex.: 0,18 = 18%)", min_value=0.0, max_value=1.0, value=0.18, step=0.005)
    else:
        sc1 = st.number_input("Sc1 (m²)", min_value=0.0, value=3000.0, step=10.0)
        fp1 = st.number_input("fp1 (para Sc1)", min_value=0.0, max_value=1.0, value=0.22, step=0.005)
        sc2 = st.number_input("Sc2 (m²)", min_value=0.0, value=10000.0, step=10.0)
        fp2 = st.number_input("fp2 (para Sc2)", min_value=0.0, max_value=1.0, value=0.15, step=0.005)
        fp = interpolate_fp(fp1, fp2, sc1, sc2, sc)
        st.info(f"fp interpolado = {fp:0.4f}")

with col3:
    st.subheader("6) Encargos, BDI e Forma de Pagamento")
    st.caption("Conforme Módulo II: Encargos Sociais e BDI já estão embutidos no PV quando a metodologia oficial é seguida. Ajuste caso sua política interna difira.")
    incluir_bdi_extra = st.checkbox("Aplicar BDI adicional (opcional)")
    bdi_extra = st.number_input("BDI extra (% do PV)", min_value=0.0, max_value=100.0, value=0.0, step=0.5) if incluir_bdi_extra else 0.0

# ----------------------
# CÁLCULO
# ----------------------
PV = compute_PV(sc, bh, fp, R)
PV_total = PV * (1 + bdi_extra/100.0)

st.divider()

colL, colM, colR = st.columns([1, 1, 1])
with colL:
    st.metric("R — Razão Sp/Sc", f"{R:0.4f}")
    if q is not None:
        st.caption(f"Cálculo com q={q} repetições → r={r:0.2f}")
with colM:
    st.metric("PV (sem BDI extra)", f"R$ {PV:,.2f}")
with colR:
    st.metric("PV TOTAL (com BDI extra)", f"R$ {PV_total:,.2f}")

# ----------------------
# PARCELAMENTO
# ----------------------
st.subheader("Parcelamento Sugerido de Honorários")
st.caption("Recomendação do Módulo II: 10% na assinatura; restante proporcionado às etapas. Ajuste conforme contrato.")

parcelamento_presets = {
    "Padrão (Genérico)": {"Assinatura": 10, "Estudo Preliminar": 20, "Anteprojeto": 25, "Projeto Básico": 10, "Projeto para Execução": 30, "As Built / Encerramento": 5},
    "Sem Projeto Básico": {"Assinatura": 10, "Estudo Preliminar": 20, "Anteprojeto": 30, "Projeto para Execução": 35, "As Built / Encerramento": 5},
}

preset_nome = st.selectbox("Modelo de Parcelamento", list(parcelamento_presets.keys()))
parcelas = parcelamento_presets[preset_nome].copy()

with st.expander("Ajustar Percentuais (total deve = 100%)", expanded=False):
    soma = 0
    for k in list(parcelas.keys()):
        parcelas[k] = st.slider(k, 0, 100, parcelas[k], 1)
        soma += parcelas[k]
    st.write(f"**TOTAL**: {soma} %")
    if soma != 100:
        st.error("A soma dos percentuais deve ser exatamente 100%.")

# Distribuição em valores
parcelas_valores = {etapa: (pct/100.0) * PV_total for etapa, pct in parcelas.items()}
parcelas_df = pd.DataFrame({
    "Etapa": list(parcelas_valores.keys()),
    "%": [parcelas[k] for k in parcelas_valores.keys()],
    "Valor (R$)": [parcelas_valores[k] for k in parcelas_valores.keys()],
})

st.dataframe(parcelas_df, use_container_width=True)

# ----------------------
# RELATÓRIO / EXPORTAR
# ----------------------
st.subheader("Exportar Proposta Sintética")

proposta = {
    "identificacao": {
        "projeto": projeto,
        "cliente": cliente,
        "uf": uf,
        "tipologia": tipologia,
        "data": dt.date.today().isoformat(),
    },
    "entradas": {
        "Sc": sc,
        "Snr": snr,
        "Sr": sr,
        "r": r,
        "q": q,
        "R": R,
        "BH": bh,
        "fp": fp,
        "BDI_extra_%": bdi_extra,
    },
    "resultados": {
        "PV_sem_BDI": PV,
        "PV_total": PV_total,
    },
    "parcelamento": parcelas_valores,
}

json_bytes = json.dumps(proposta, ensure_ascii=False, indent=2).encode("utf-8")
st.download_button(
    label="⬇️ Baixar proposta (JSON)",
    data=json_bytes,
    file_name=f"proposta_{projeto.replace(' ','_')}.json",
    mime="application/json",
)

# Planilha CSV das parcelas
csv_buf = io.StringIO()
parcelas_df.to_csv(csv_buf, index=False)
st.download_button(
    label="⬇️ Baixar parcelamento (CSV)",
    data=csv_buf.getvalue().encode("utf-8"),
    file_name=f"parcelamento_{projeto.replace(' ','_')}.csv",
    mime="text/csv",
)

# ----------------------
# RODAPÉ
# ----------------------
st.caption(
    "Referência metodológica: Tabelas de Honorários do CAU/BR — Módulo II (PV = Sc × BH × (fp × R); Encargos/BDI; Forma de pagamento).\n"
    "A aderência completa requer os ANEXOS do Módulo I para BH, fp e r."
)
