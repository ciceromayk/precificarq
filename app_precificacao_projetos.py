# app_precificacao_projetos.py
# -------------------------------------------------------------
# APLICATIVO STREAMLIT PARA PRECIFICAÇÃO DE PROJETOS (CAU/BR)
# Módulos integrados:
#  - MÓDULO II (condições gerais): PV = Sc × BH × (fp × R)
#  - MÓDULO I (apoio ao cálculo de BH, IC e Fator K)
# -------------------------------------------------------------
# Referências normativas (ver PDF do usuário):
# - Módulo II – Fórmula básica e definições (PV, fp interp., R=Sp/Sc) 
# - Módulo I – Anexo I (Tabela 8 - BH via CUB e fator de adequação)
#             Anexo II (Índice de Complexidade – IC)
#             Anexos III a VI (K1..K4) e Anexo VII (Resumo do cálculo do Fator K)
# -------------------------------------------------------------

import io
import math
import json
import datetime as dt
from typing import Optional, Dict, List

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
# HELPERS (MÓD. II)
# ----------------------

def interpolate_fp(fp1: float, fp2: float, sc1: float, sc2: float, sc: float) -> float:
    """Interpolação linear de fp entre dois pontos (sc1->fp1) e (sc2->fp2)."""
    if sc2 == sc1:
        return fp1
    return fp1 - ((fp1 - fp2) * ((sc - sc1) / (sc2 - sc1)))


def estimate_r_by_repetition(q: int) -> float:
    """Estimativa prática para r (redutor de áreas repetidas) quando a Tabela oficial não estiver disponível."""
    if q <= 1:
        return 1.0
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
# HELPERS (MÓD. I) — BH, IC, K
# ----------------------

# Pequena amostra de TIPOLOGIAS (Anexo I - Tabela 8) com CUB simbólico e fator de adequação.
# (Você pode ampliar/editar este dicionário ou carregar planilhas completas.)
TIPOLOGIAS_BH = [
    {
        "grupo": "Habitacional > Residencial",
        "item": "Edifícios de apartamentos / padrão normal",
        "categoria": "I",
        "cub_ref": "R-8-N",
        "fator_adequacao": 1.5,
    },
    {
        "grupo": "Habitacional > Residencial",
        "item": "Edifícios de apartamentos / padrão alto",
        "categoria": "II",
        "cub_ref": "R-16-A",
        "fator_adequacao": 1.5,
    },
    {
        "grupo": "Habitacional > Residencial",
        "item": "Residência unifamiliar / padrão elevado",
        "categoria": "IV",
        "cub_ref": "R-1-A",
        "fator_adequacao": 2.0,
    },
    {
        "grupo": "Comércio > Lojas/Magazines/Shopping",
        "item": "Lojas de departamentos, centros comerciais, shopping",
        "categoria": "III/IV",
        "cub_ref": "CAL-8-N",
        "fator_adequacao": 1.3,
    },
]


def calcular_bh(cub_basico: float, fator_adequacao: float) -> float:
    """BH = CUB_básico × fator de adequação (Anexo I, Tabela 8)."""
    return cub_basico * fator_adequacao

# Índice de Complexidade (IC) — 10 indicadores com fatores 0,70 / 1,00 / 1,30
IC_OPCOES = {
    "Baixo": 0.70,
    "Médio": 1.00,
    "Alto": 1.30,
}
IC_INDICADORES = [
    "Porte do projeto",
    "Quantidade de especialistas",
    "Quantidade de aprovações",
    "Grau de detalhamento",
    "Grau de responsabilidade civil",
    "Sofisticação tecnológica (complementares)",
    "Intensidade de participação do cliente",
    "Complexidade compositiva",
    "Complexidade de pesquisas prévias",
    "Complexidade do desenvolvimento/execução",
]


def calcular_ic_media(fatores: List[float]) -> float:
    return sum(fatores) / len(fatores) if fatores else 1.0

# Fator K = composição de K1..K4

def fator_K_generico(ES: float, DI: float, L: float, DL: float) -> float:
    """Aplica K = (1+ES)×(1+DI)×(1+L)×(1+DL), com entradas em percentuais (ex.: 20 para 20%)."""
    ESf, DIf, Lf, DLf = (ES/100.0), (DI/100.0), (L/100.0), (DL/100.0)
    return (1+ESf) * (1+DIf) * (1+Lf) * (1+DLf)

# Defaults ilustrativos a partir do Anexo VII (exemplo de tabela)
DEFAULTS_K = {
    "K1": {"ES": 85.64, "DI": 55.76, "L": 10.0, "DL": 22.37},
    "K2": {"ES": 20.0,  "DI": 15.0,  "L": 10.0, "DL": 22.37},
    "K3": {"ES": 0.0,   "DI": 15.0,  "L": 10.0, "DL": 22.37},
    "K4": {"ES": 0.0,   "DI": 10.0,  "L": 10.0, "DL": 22.37},
}

# ----------------------
# UI PRINCIPAL
# ----------------------
T1, T2, T3 = st.tabs(["Módulo II — PV", "Módulo I — BH, IC e K", "Relatórios & Exportação"])

with T1:
    colA, colB, colC = st.columns([1.2, 1, 1])

    with colA:
        st.subheader("1) Parâmetros Gerais")
        projeto = st.text_input("Nome do Projeto", value=st.session_state.get("projeto", "Edifício Residencial Exemplo"))
        cliente = st.text_input("Cliente / Contratante", value=st.session_state.get("cliente", "IDIBRA / Exemplo"))
        uf = st.selectbox("UF do empreendimento", options=[
            "AC","AL","AP","AM","BA","CE","DF","ES","GO","MA","MT","MS","MG","PA",
            "PB","PR","PE","PI","RJ","RN","RS","RO","RR","SC","SP","SE","TO"
        ], index=6)
        tipologia = st.text_input("Tipologia (livre)", value=st.session_state.get("tipologia", "Residencial multifamiliar"))

    with colB:
        st.subheader("2) Áreas (m²)")
        sc = st.number_input("Sc — Área construída estimada (TOTAL)", min_value=0.0, value=float(st.session_state.get("sc", 5000.0)), step=10.0, key="sc")
        snr = st.number_input("Snr — Área NÃO repetida", min_value=0.0, value=float(st.session_state.get("snr", 1500.0)), step=10.0, key="snr")
        sr = st.number_input("Sr — Área repetida", min_value=0.0, value=float(st.session_state.get("sr", 3500.0)), step=10.0, key="sr")

    with colC:
        st.subheader("3) Repetição (r)")
        mode_r = st.radio("Como obter o redutor r?", ["Informar manualmente", "Estimar por nº de repetições (q)"])
        if mode_r == "Informar manualmente":
            r = st.slider("r — Redutor para áreas repetidas (0 a 1)", min_value=0.0, max_value=1.0, value=float(st.session_state.get("r", 0.6)), step=0.01, key="r")
            q = None
        else:
            q = st.number_input("q — Nº de repetições (ex.: nº de pavimentos-tipo)", min_value=1, value=int(st.session_state.get("q", 8)), step=1)
            r = estimate_r_by_repetition(q)
            st.info(f"r estimado = {r:0.2f} (ajuste conforme as Tabelas oficiais)")

    R = compute_R(snr, sr, r, sc)

    st.divider()

    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        st.subheader("4) BH — Base de Honorários")
        st.caption("Se preferir, calcule o BH no Tab 'Módulo I' e clique em 'Usar BH calculado'.")
        if "BH_calculado" in st.session_state:
            st.info(f"BH calculado (Mód. I): R$ {st.session_state['BH_calculado']:,.2f}/m²")
        bh = st.number_input("BH (R$/m²)", min_value=0.0, value=float(st.session_state.get("bh", 120.0)), step=1.0, key="bh")

    with col2:
        st.subheader("5) fp — Fator Percentual")
        fp_mode = st.radio("Como obter fp?", ["Informar manualmente", "Interpolar entre duas faixas (Sc1→fp1; Sc2→fp2)"])
        if fp_mode == "Informar manualmente":
            fp = st.number_input("fp (fator adimensional; ex.: 0,18 = 18%)", min_value=0.0, max_value=1.0, value=float(st.session_state.get("fp", 0.18)), step=0.005, key="fp")
        else:
            sc1 = st.number_input("Sc1 (m²)", min_value=0.0, value=float(st.session_state.get("sc1", 3000.0)), step=10.0)
            fp1 = st.number_input("fp1 (para Sc1)", min_value=0.0, max_value=1.0, value=float(st.session_state.get("fp1", 0.22)), step=0.005)
            sc2 = st.number_input("Sc2 (m²)", min_value=0.0, value=float(st.session_state.get("sc2", 10000.0)), step=10.0)
            fp2 = st.number_input("fp2 (para Sc2)", min_value=0.0, max_value=1.0, value=float(st.session_state.get("fp2", 0.15)), step=0.005)
            fp = interpolate_fp(fp1, fp2, sc1, sc2, sc)
            st.info(f"fp interpolado = {fp:0.4f}")

    with col3:
        st.subheader("6) Encargos, BDI e Forma de Pagamento")
        incluir_bdi_extra = st.checkbox("Aplicar BDI adicional (opcional)")
        bdi_extra = st.number_input("BDI extra (% do PV)", min_value=0.0, max_value=100.0, value=float(st.session_state.get("bdi_extra", 0.0)), step=0.5) if incluir_bdi_extra else 0.0

    # Cálculo PV
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

    # Parcelamento
    st.subheader("Parcelamento Sugerido de Honorários")
    st.caption("Recomendação comum: 10% na assinatura; restante distribuído às etapas. Ajuste conforme contrato.")

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

    parcelas_valores = {etapa: (pct/100.0) * PV_total for etapa, pct in parcelas.items()}
    parcelas_df = pd.DataFrame({
        "Etapa": list(parcelas_valores.keys()),
        "%": [parcelas[k] for k in parcelas_valores.keys()],
        "Valor (R$)": [parcelas_valores[k] for k in parcelas_valores.keys()],
    })

    st.dataframe(parcelas_df, use_container_width=True)

with T2:
    st.subheader("Módulo I — BH (Base de Honorários)")

    colBH1, colBH2 = st.columns([1, 1])
    with colBH1:
        sel = st.selectbox(
            "Tipologia (amostra) — personalize conforme Anexo I",
            options=[f"{t['grupo']} · {t['item']} ({t['cub_ref']}, fator {t['fator_adequacao']})" for t in TIPOLOGIAS_BH],
        )
        tip = TIPOLOGIAS_BH[[f"{t['grupo']} · {t['item']} ({t['cub_ref']}, fator {t['fator_adequacao']})" for t in TIPOLOGIAS_BH].index(sel)]
        cub_basico = st.number_input(
            "CUB básico (R$/m²) do Estado/competência (obtido no SINDUSCON)",
            min_value=0.0,
            value=1000.0,
            step=1.0,
            help="Insira o CUB do mês/ref. Ex.: CE, residencial R-8-N, etc.",
        )
        bh_calc = calcular_bh(cub_basico, tip["fator_adequacao"])
        st.metric("BH calculado", f"R$ {bh_calc:,.2f}/m²")
        if st.button("Usar BH calculado no Tab Módulo II"):
            st.session_state["BH_calculado"] = bh_calc
            st.session_state["bh"] = bh_calc
            st.success("BH aplicado no Módulo II.")

    with colBH2:
        st.info(
            "BH = CUB_básico × Fator de adequação (Anexo I, Tabela 8). Personalize a base conforme sua tipologia."
        )
        st.caption("Dica: você pode ampliar o dicionário TIPOLOGIAS_BH, ou importar uma planilha completa das tipologias.")

    st.markdown("---")
    st.subheader("Módulo I — Índice de Complexidade (IC)")
    st.caption("Selecione o nível de cada indicador (0,70 / 1,00 / 1,30). O IC médio ajuda a adequar a coluna do fp na Tabela 5.")

    ic_cols = st.columns(2)
    fatores_escolhidos: List[float] = []
    for i, nome in enumerate(IC_INDICADORES):
        with ic_cols[i % 2]:
            escolha = st.radio(nome, list(IC_OPCOES.keys()), horizontal=True, key=f"ic_{i}")
            fatores_escolhidos.append(IC_OPCOES[escolha])
    ic_medio = calcular_ic_media(fatores_escolhidos)
    st.metric("IC médio (adimensional)", f"{ic_medio:0.2f}")
    st.caption("Use o IC para discutir com o cliente eventual mudança de coluna na Tabela de fp (mais ou menos complexo).")

    st.markdown("---")
    st.subheader("Módulo I — Fator K (K1..K4)")
    st.caption("Parâmetros de Encargos e BDI por componente; ajuste conforme a realidade fiscal/operacional do escritório.")

    Kexp = st.expander("Parâmetros (padrões ilustrativos do Anexo VII) — clique para editar", expanded=False)
    with Kexp:
        k_inputs = {}
        for kname in ["K1", "K2", "K3", "K4"]:
            st.markdown(f"**{kname}**")
            c1, c2, c3, c4 = st.columns(4)
            ES = c1.number_input(f"{kname} ES %", min_value=0.0, max_value=500.0, value=float(DEFAULTS_K[kname]["ES"]))
            DI = c2.number_input(f"{kname} DI %", min_value=0.0, max_value=500.0, value=float(DEFAULTS_K[kname]["DI"]))
            L  = c3.number_input(f"{kname} L %",  min_value=0.0, max_value=500.0, value=float(DEFAULTS_K[kname]["L"]))
            DL = c4.number_input(f"{kname} DL %", min_value=0.0, max_value=500.0, value=float(DEFAULTS_K[kname]["DL"]))
            k_inputs[kname] = {"ES": ES, "DI": DI, "L": L, "DL": DL}
            kval = fator_K_generico(ES, DI, L, DL)
            st.write(f"{kname} calculado = **{kval:0.4f}**")

    # Observação metodológica
    st.info("O Fator K resume incidências de ES e BDI por componentes (K1..K4). Utilize-o quando optar pela Modalidade 02 (Cálculo pelo Custo do Serviço).")

with T3:
    st.subheader("Exportar Proposta Sintética")

    # Recomputa para garantir consistência
    sc = float(st.session_state.get("sc", 0.0))
    snr = float(st.session_state.get("snr", 0.0))
    sr = float(st.session_state.get("sr", 0.0))
    r  = float(st.session_state.get("r", 1.0))
    R  = compute_R(snr, sr, r, sc)
    bh = float(st.session_state.get("bh", 0.0))
    fp = float(st.session_state.get("fp", 0.0))

    PV = compute_PV(sc, bh, fp, R)
    bdi_extra = float(st.session_state.get("bdi_extra", 0.0))
    PV_total = PV * (1 + bdi_extra/100.0)

    # Parcelas — regenerar com base no Tab 1, se existir
    try:
        parcelas_df
    except NameError:
        parcelas_df = pd.DataFrame({"Etapa": ["Assinatura"], "%": [10], "Valor (R$)": [PV_total*0.1]})

    proposta = {
        "identificacao": {
            "projeto": st.session_state.get("projeto", ""),
            "cliente": st.session_state.get("cliente", ""),
            "uf": st.session_state.get("uf", ""),
            "tipologia": st.session_state.get("tipologia", ""),
            "data": dt.date.today().isoformat(),
        },
        "entradas": {
            "Sc": sc,
            "Snr": snr,
            "Sr": sr,
            "r": r,
            "R": R,
            "BH": bh,
            "fp": fp,
            "BDI_extra_%": bdi_extra,
            "BH_calculado": st.session_state.get("BH_calculado", None),
        },
        "resultados": {
            "PV_sem_BDI": PV,
            "PV_total": PV_total,
        },
    }

    json_bytes = json.dumps(proposta, ensure_ascii=False, indent=2).encode("utf-8")
    st.download_button(
        label="⬇️ Baixar proposta (JSON)",
        data=json_bytes,
        file_name=f"proposta_{st.session_state.get('projeto','projeto')}.json",
        mime="application/json",
    )

    csv_buf = io.StringIO()
    parcelas_df.to_csv(csv_buf, index=False)
    st.download_button(
        label="⬇️ Baixar parcelamento (CSV)",
        data=csv_buf.getvalue().encode("utf-8"),
        file_name=f"parcelamento_{st.session_state.get('projeto','projeto')}.csv",
        mime="text/csv",
    )

st.caption("Metodologia: PV = Sc × BH × (fp × R) (Mód. II). BH pelo CUB×fator de adequação (Mód. I, Tabela 8). IC (Mód. I, Anexo II). Fator K (Anexo VII)."
    "A aderência completa requer o uso integral das tabelas do CAU/BR. Personalize as tipologias e parâmetros."
)
