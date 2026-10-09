import sys
import traceback

# 1. Configuração inicial obrigatória
import streamlit as st
st.set_page_config(
    page_title="Sistema de Auditoria | DAH-FUNEAS",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# 2. Bloco protegido para capturar qualquer falha e exibir na tela
try:
    import os
    import io
    import re
    import base64
    from datetime import datetime
    import pandas as pd
    from docxtpl import DocxTemplate
    from streamlit_gsheets import GSheetsConnection
    from extractor import extrair_dados_processo, formatar_valor_reais
    from extractor_producao import extrair_dados_producao_medica
    from num2words import num2words
    import streamlit.components.v1 as components

    # Testa a inicialização dos Secrets / Conexão
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
    except Exception as err_conn:
        st.error("⚠️ FALHA NA CONEXÃO COM O GOOGLE SHEETS / SECRETS:")
        st.code(str(err_conn))
        st.stop()

except Exception as err_geral:
    st.error("🚨 OCORREU UM ERRO AO CARREGAR AS DEPENDÊNCIAS DO APLICATIVO:")
    st.code(traceback.format_exc())
    st.stop()

# ==========================================
# GATILHO DE DOWNLOAD DIRETO VIA JAVASCRIPT
# ==========================================
def disparar_download_imediato(conteudo_bytes, nome_arquivo):
    b64 = base64.b64encode(conteudo_bytes).decode()
    js_code = f"""
    <script>
        (function() {{
            try {{
                var doc = window.top.document;
                var a = doc.createElement('a');
                a.href = 'data:application/vnd.openxmlformats-officedocument.wordprocessingml.document;base64,{b64}';
                a.download = '{nome_arquivo}';
                doc.body.appendChild(a);
                a.click();
                doc.body.removeChild(a);
            }} catch (e) {{
                var a2 = document.createElement('a');
                a2.href = 'data:application/octet-stream;base64,{b64}';
                a2.download = '{nome_arquivo}';
                document.body.appendChild(a2);
                a2.click();
                document.body.removeChild(a2);
            }}
        }})();
    </script>
    """
    components.html(js_code, height=0, width=0)

def auto_formatar_data(valor):
    if not valor or pd.isna(valor):
        return ""
    v = str(valor).strip()
    if re.match(r"^\d{2}/\d{2}/\d{4}$", v):
        return v
    apenas_numeros = re.sub(r"\D", "", v)
    if len(apenas_numeros) == 8:
        return f"{apenas_numeros[:2]}/{apenas_numeros[2:4]}/{apenas_numeros[4:]}"
    elif len(apenas_numeros) == 6:
        dia, mes, ano = apenas_numeros[:2], apenas_numeros[2:4], apenas_numeros[4:]
        ano_completo = f"20{ano}" if int(ano) < 50 else f"19{ano}"
        return f"{dia}/{mes}/{ano_completo}"
    return v

# ==========================================
# ESTILOS CSS
# ==========================================
st.markdown(
    """
    <style>
        [data-testid="stSidebar"], [data-testid="stSidebarNav"], [data-testid="collapsedControl"] {
            display: none !important;
        }
        .block-container {
            padding-top: 1.2rem !important;
            padding-bottom: 2rem !important;
        }
        .dah-header {
            background: linear-gradient(90deg, #0f2b48 0%, #1e3a8a 100%);
            padding: 12px 24px;
            border-radius: 12px;
            color: #ffffff;
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 20px;
            box-shadow: 0 4px 10px rgba(0,0,0,0.08);
        }
        .dah-header h2 {
            margin: 0;
            font-size: 1.25rem;
            font-weight: 700;
            color: #ffffff;
        }
        .dah-header span {
            font-size: 0.85rem;
            color: #93c5fd;
        }
        div.stButton > button {
            transition: all 0.2s ease-in-out !important;
        }
        .btn-modulo-ativo button {
            background-color: #1e3a8a !important;
            color: #ffffff !important;
            border: 2px solid #1e3a8a !important;
            border-radius: 10px !important;
            padding: 12px 18px !important;
            font-size: 1.08rem !important;
            font-weight: 700 !important;
            box-shadow: 0 4px 12px rgba(30, 58, 138, 0.3) !important;
            transform: translateY(-1px);
        }
        .btn-modulo-inativo button {
            background-color: #f8fafc !important;
            color: #475569 !important;
            border: 2px solid #cbd5e1 !important;
            border-radius: 10px !important;
            padding: 12px 18px !important;
            font-size: 1.05rem !important;
            font-weight: 600 !important;
        }
        .btn-modulo-inativo button:hover {
            border-color: #94a3b8 !important;
            background-color: #f1f5f9 !important;
            color: #1e293b !important;
        }
    </style>
    """,
    unsafe_allow_html=True
)

# Header
st.markdown(
    """
    <div class="dah-header">
        <div>
            <h2>🏥 DAH • FUNEAS</h2>
            <span>Divisão de Auditoria Hospitalar — Sistema Integrado de Despachos</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

MEMBROS_EQUIPE = [
    {"nome": "Emily Trevizan", "cargo": "Chefe de Setor – DAH/FUNEAS"},
    {"nome": "Julia Veiga Ramalho", "cargo": "Assistente Administrativo – DAH/FUNEAS"},
    {"nome": "Michelle Medeiros", "cargo": "Assistente Administrativo – DAH/FUNEAS"},
    {"nome": "Soraya Pacheco dos Santos Lima", "cargo": "Assistente Administrativo – DAH/FUNEAS"},
    {"nome": "Outro (Digitar manualmente)", "cargo": "DAH/FUNEAS"},
]

if "modulo_ativo" not in st.session_state:
    st.session_state["modulo_ativo"] = "opme"

# Seletores
col_mod1, col_mod2, col_respiro, col_user = st.columns([1.6, 1.6, 0.4, 1.4])

with col_mod1:
    ativo_opme = (st.session_state["modulo_ativo"] == "opme")
    classe_opme = "btn-modulo-ativo" if ativo_opme else "btn-modulo-inativo"
    st.markdown(f'<div class="{classe_opme}">', unsafe_allow_html=True)
    if st.button("📦 Auditoria de OPME", key="btn_sel_opme", use_container_width=True):
        st.session_state["modulo_ativo"] = "opme"
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

with col_mod2:
    ativo_prod = (st.session_state["modulo_ativo"] == "producao")
    classe_prod = "btn-modulo-ativo" if ativo_prod else "btn-modulo-inativo"
    st.markdown(f'<div class="{classe_prod}">', unsafe_allow_html=True)
    if st.button("🩺 Produção / Escala Médica", key="btn_sel_prod", use_container_width=True):
        st.session_state["modulo_ativo"] = "producao"
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

with col_user:
    nomes_opcoes = [m["nome"] for m in MEMBROS_EQUIPE]
    nome_selecionado = st.selectbox(
        "👤 Analista Responsável:",
        nomes_opcoes,
        index=0,
        help="Responsável pela conferência do despacho"
    )

if nome_selecionado == "Outro (Digitar manualmente)":
    c_out1, c_out2 = st.columns(2)
    with c_out1:
        auditor_nome = st.text_input("Nome completo do Analista:")
    with c_out2:
        auditor_cargo = st.text_input("Cargo:", value="Assistente Administrativo – DAH/FUNEAS")
else:
    item_membro = next(m for m in MEMBROS_EQUIPE if m["nome"] == nome_selecionado)
    auditor_nome = item_membro["nome"]
    auditor_cargo = item_membro["cargo"]

st.markdown("---")

# MÓDULO OPME
if st.session_state["modulo_ativo"] == "opme":
    st.subheader("Gerador de Despacho de OPME")
    st.caption("Extração automatizada, emissão de despachos e registo consolidado no Google Sheets.")

    arquivo_pdf = st.file_uploader("Arraste ou selecione o PDF do eProtocolo (OPME):", type=["pdf"], key="up_opme")

    if arquivo_pdf is not None:
        if "dados_extraidos_opme" not in st.session_state or st.session_state.get("nome_arquivo_opme") != arquivo_pdf.name:
            with st.spinner("A extrair informações do processo de OPME..."):
                pdf_bytes = arquivo_pdf.read()
                st.session_state["dados_extraidos_opme"] = extrair_dados_processo(pdf_bytes)
                st.session_state["nome_arquivo_opme"] = arquivo_pdf.name

        dados = st.session_state["dados_extraidos_opme"]
        st.success("Dados extraídos com sucesso! Reveja as informações abaixo:")

        col1, col2, col3 = st.columns(3)
        with col1:
            protocolo = st.text_input("Protocolo nº", value=dados["protocolo"], key="opme_prot")
            hospital_sigla = st.text_input("Sigla da Unidade", value=dados["hospital_sigla"], key="opme_hsig")
            hospital_nome = st.text_input("Nome do Hospital", value=dados["hospital_nome"], key="opme_hnom")
        with col2:
            fornecedor_nome = st.text_input("Fornecedor", value=dados["fornecedor_nome"], key="opme_forn")
            cnpj = st.text_input("CNPJ", value=dados["cnpj"], key="opme_cnpj")
            competencia = st.text_input("Competência", value=dados["competencia"], key="opme_comp")
        with col3:
            contrato = st.text_input("Contrato nº", value=dados["contrato"], key="opme_cont")
            empenho = st.text_input("Nota de Despesa/Empenho", value=dados["empenho"], key="opme_emp")
            col_v1, col_v2 = st.columns(2)
            with col_v1:
                vig_inicio = st.text_input("Vigência Início", value=dados["vigencia_inicio"], key="opme_vini")
            with col_v2:
                vig_fim = st.text_input("Vigência Fim", value=dados["vigencia_fim"], key="opme_vfim")

        st.subheader("Relação de Notas Fiscais e Pacientes")
        st.caption("💡 *Dica:* Na data da cirurgia, pode digitar apenas os números (ex: `13112026`).")

        df_nfs = pd.DataFrame(dados["nfs"])
        if df_nfs.empty:
            df_nfs = pd.DataFrame(columns=["numero", "data_emissao", "valor", "paciente", "data_cirurgia"])

        df_editado = st.data_editor(
            df_nfs, num_rows="dynamic", use_container_width=True,
            column_config={
                "numero": "Nº NF", "data_emissao": "Data Emissão", "valor": "Valor (R$)",
                "paciente": "Nome do Paciente", 
                "data_cirurgia": st.column_config.TextColumn(
                    "Data Cirurgia (DD/MM/AAAA)",
                    help="Digite com ou sem barras (ex: 13112026)",
                    max_chars=10
                )
            },
            key="editor_opme"
        )

        total_calculado = 0.0
        for _, row in df_editado.iterrows():
            try:
                v = str(row["valor"]).replace(".", "").replace(",", ".").replace("R$", "").strip()
                total_calculado += float(v)
            except Exception:
                pass

        valor_total_str = formatar_valor_reais(total_calculado)
        try:
            valor_extenso_str = num2words(total_calculado, lang="pt_BR", to="currency").lower()
        except Exception:
            valor_extenso_str = ""

        exige_diretoria = total_calculado > 20000.0
        st.markdown(f"**Valor Total Consolidado:** R$ {valor_total_str} (*{valor_extenso_str}*)")

        if exige_diretoria:
            st.warning("⚠️ **Alçada Superior (> R$ 20.000,00):** O despacho incluirá a assinatura da Diretora Técnica (Dra. Acácia Nasr).")
        else:
            st.info("ℹ️ **Alçada Padrão (≤ R$ 20.000,00):** O despacho será assinado pelo Analista e pela Chefia da Divisão.")

        st.subheader("Parecer da Auditoria")
        tem_inconformidade = st.radio(
            "Foram detetadas inconformidades/glosas nas NFs ou documentos?",
            options=["Não (Parecer Favorável)", "Sim (Retorno à Unidade de Origem)"],
            index=0, key="radio_opme"
        )

        texto_inconformidade = ""
        if tem_inconformidade == "Sim (Retorno à Unidade de Origem)":
            texto_inconformidade = st.text_area("Descreva as inconformidades por paciente/NF:", height=120, key="txt_inc_opme")

        st.subheader("Geração do Despacho")
        candidatos_template = [
            os.path.abspath(os.path.join(os.path.dirname(__file__), "templates", "modelo_despacho.docx")),
            os.path.abspath(os.path.join(os.getcwd(), "templates", "modelo_despacho.docx")),
            os.path.join("templates", "modelo_despacho.docx"),
            "modelo_despacho.docx"
        ]
        caminho_template = next((c for c in candidatos_template if os.path.exists(c)), None)

        if not caminho_template:
            st.warning("Ficheiro `modelo_despacho.docx` não encontrado na pasta `templates`.")
        else:
            primeiro_nome_forn = fornecedor_nome.split()[0].replace("/", "_") if fornecedor_nome else ""
            nome_saida_opme = f"DESPACHO_{hospital_sigla}_OPME_{protocolo}_{primeiro_nome_forn}.docx"

            if st.button("📝 Gerar e Descarregar Despacho (OPME)", key="btn_exec_opme", type="primary"):
                with st.spinner("A gerar documento Word e a registar na folha de cálculo..."):
                    df_editado_formatado = df_editado.copy()
                    df_editado_formatado["data_cirurgia"] = df_editado_formatado["data_cirurgia"].apply(auto_formatar_data)

                    doc = DocxTemplate(caminho_template)
                    lista_nfs_context = df_editado_formatado.to_dict(orient="records")

                    contexto = {
                        "protocolo": protocolo, "hospital_nome": hospital_nome, "hospital_sigla": hospital_sigla,
                        "fornecedor_nome": fornecedor_nome, "cnpj": cnpj, "valor_total": valor_total_str,
                        "valor_extenso": valor_extenso_str, "competencia": competencia, "contrato": contrato,
                        "vigencia_inicio": vig_inicio, "vigencia_fim": vig_fim, "empenho": empenho,
                        "nfs": lista_nfs_context, "tem_inconformidade": (tem_inconformidade != "Não (Parecer Favorável)"),
                        "texto_inconformidade": texto_inconformidade, "assinante_elaborador": auditor_nome,
                        "cargo_elaborador": auditor_cargo, "exige_diretoria": exige_diretoria,
                    }

                    doc.render(contexto)
                    buffer = io.BytesIO()
                    doc.save(buffer)
                    buffer.seek(0)
                    docx_bytes = buffer.getvalue()

                    detalhes_pacientes = []
                    for nf in lista_nfs_context:
                        nome = nf.get('paciente', '').strip()
                        data_cir = nf.get('data_cirurgia', '').strip()
                        if nome or data_cir:
                            item_str = f"{nome} ({data_cir})" if data_cir else nome
                            detalhes_pacientes.append(item_str)

                    pacientes_str = " | ".join(detalhes_pacientes)
                    novo_registo = pd.DataFrame([{
                        "Data/Hora": datetime.now().strftime("%d/%m/%Y %H:%M"),
                        "Divisão (DAH)": "DAH",
                        "Tipo de Processo": "OPME",
                        "Nº Protocolo": protocolo,
                        "Unidade Hospitalar": hospital_sigla,
                        "Empresa / Fornecedor": primeiro_nome_forn,
                        "Especialidade": "OPME",
                        "Valor do Processo (R$)": total_calculado,
                        "Pacientes (nomes e datas das Cirurgias)": pacientes_str,
                        "Responsável": auditor_nome
                    }])

                    try:
                        df_existente = conn.read(ttl=0)
                        if df_existente is None or df_existente.empty:
                            df_atualizado = novo_registo
                        else:
                            df_atualizado = pd.concat([df_existente, novo_registo], ignore_index=True)
                        conn.update(data=df_atualizado)
                        st.success("✅ Registo concluído com sucesso na folha de cálculo!")
                    except Exception as e:
                        st.error(f"⚠️ Erro ao registar na Folha: {repr(e)}")

                    disparar_download_imediato(docx_bytes, nome_saida_opme)
                    st.info(f"O download do ficheiro **{nome_saida_opme}** foi iniciado diretamente.")

# MÓDULO PRODUÇÃO
elif st.session_state["modulo_ativo"] == "producao":
    st.subheader("Gerador de Despacho de Produção Médica")
    st.caption("Emissão de despacho com definição obrigatória de modalidade e especialidade médica.")

    arquivo_pdf_prod = st.file_uploader("Arraste ou selecione o PDF do eProtocolo:", type=["pdf"], key="up_prod")

    if arquivo_pdf_prod is not None:
        if "dados_extraidos_prod" not in st.session_state or st.session_state.get("nome_arquivo_prod") != arquivo_pdf_prod.name:
            with st.spinner("A extrair informações do processo..."):
                pdf_bytes_prod = arquivo_pdf_prod.read()
                st.session_state["dados_extraidos_prod"] = extrair_dados_producao_medica(pdf_bytes_prod)
                st.session_state["nome_arquivo_prod"] = arquivo_pdf_prod.name

        dados_p = st.session_state["dados_extraidos_prod"]
        st.success("Dados carregados! Preencha as definições obrigatórias e confira os campos abaixo:")

        st.markdown("### 🔍 Identificação Obrigatória do Serviço")
        col_tipo, col_esp = st.columns(2)
        with col_tipo:
            tipo_servico_selecionado = st.radio(
                "Qual a modalidade deste processo? *",
                options=["Produção Médica", "Escala Médica"],
                index=0, key="p_tipo_servico"
            )
        with col_esp:
            prod_especialidade = st.text_input(
                "Qual a Especialidade Médica? *",
                value=dados_p.get("especialidade", ""),
                placeholder="Ex: Urologia, Ginecologia e Obstetrícia, Ortopedia...",
                key="p_espc"
            )

        st.markdown("---")
        st.markdown("### 📑 Dados do Processo e Contrato")

        col1, col2, col3 = st.columns(3)
        with col1:
            prod_protocolo = st.text_input("Protocolo nº", value=dados_p["protocolo"], key="p_prot")
            prod_hospital_sigla = st.text_input("Sigla da Unidade", value=dados_p["hospital_sigla"], key="p_hsig")
            prod_hospital_nome = st.text_input("Nome do Hospital", value=dados_p.get("hospital_nome", ""), key="p_hnom")
        with col2:
            prod_fornecedor = st.text_input("Fornecedor / Empresa", value=dados_p["fornecedor_nome"], key="p_forn")
            prod_cnpj = st.text_input("CNPJ", value=dados_p["cnpj"], key="p_cnpj")
            prod_competencia = st.text_input("Competência", value=dados_p["competencia"], key="p_comp")
        with col3:
            prod_contrato = st.text_input("Contrato nº", value=dados_p["contrato"], key="p_cont")
            prod_empenho = st.text_input("Nota de Empenho", value=dados_p["empenho"], key="p_emp")
            col_v1, col_v2 = st.columns(2)
            with col_v1:
                prod_vig_inicio = st.text_input("Vigência Início", value=dados_p.get("vigencia_inicio", ""), key="p_vini")
            with col_v2:
                prod_vig_fim = st.text_input("Vigência Fim", value=dados_p.get("vigencia_fim", ""), key="p_vfim")

        st.subheader("Relação de Notas Fiscais")
        df_nfs_prod = pd.DataFrame(dados_p["nfs"])
        if df_nfs_prod.empty:
            df_nfs_prod = pd.DataFrame(columns=["numero", "data_emissao", "valor"])

        df_editado_prod = st.data_editor(
            df_nfs_prod, num_rows="dynamic", use_container_width=True,
            column_config={"numero": "Nº NF", "data_emissao": "Data Emissão", "valor": "Valor (R$)"},
            key="editor_prod"
        )

        total_prod = 0.0
        for _, row in df_editado_prod.iterrows():
            try:
                v = str(row["valor"]).replace(".", "").replace(",", ".").replace("R$", "").strip()
                total_prod += float(v)
            except Exception:
                pass

        valor_total_str_p = formatar_valor_reais(total_prod)
        try:
            valor_extenso_str_p = num2words(total_prod, lang="pt_BR", to="currency").lower()
        except Exception:
            valor_extenso_str_p = ""

        exige_diretoria_p = total_prod > 20000.0
        st.markdown(f"**Valor Total Consolidado:** R$ {valor_total_str_p} (*{valor_extenso_str_p}*)")

        if exige_diretoria_p:
            st.warning("⚠️ **Alçada Superior (> R$ 20.000,00):** O despacho incluirá a assinatura da Diretora Técnica (Dra. Acácia Nasr).")
        else:
            st.info("ℹ️ **Alçada Padrão (≤ R$ 20.000,00):** O despacho será assinado pelo Analista e pela Chefia da Divisão.")

        st.subheader("Parecer da Auditoria")
        tem_inconformidade_p = st.radio(
            "Foram detetadas inconformidades ou glosas no processo?",
            options=["Não (Parecer Favorável)", "Sim (Retorno à Unidade de Origem)"],
            index=0, key="radio_prod"
        )

        texto_inconformidade_p = ""
        if tem_inconformidade_p == "Sim (Retorno à Unidade de Origem)":
            texto_inconformidade_p = st.text_area("Digite a inconsistência detetada:", height=120, key="txt_inc_prod")

        st.subheader("Geração do Despacho")
        pastas_base = [
            os.path.abspath(os.path.join(os.path.dirname(__file__), "templates")),
            os.path.abspath(os.path.join(os.getcwd(), "templates")),
            os.path.abspath(os.path.dirname(__file__)),
            os.path.abspath(os.getcwd()),
            "templates"
        ]
        nomes_ficheiro = [
            "modelo_despacho_producao_medica.docx",
            "modelo_despacho_producao_medica.docx.docx",
            "modelo_despacho_producao_medica"
        ]
        caminho_template_prod = None
        for p in pastas_base:
            for n in nomes_ficheiro:
                possivel = os.path.join(p, n)
                if os.path.exists(possivel):
                    caminho_template_prod = possivel
                    break
            if caminho_template_prod:
                break

        if not caminho_template_prod:
            st.warning("O modelo Word de produção não foi localizado na pasta `templates`.")
        else:
            if not prod_especialidade.strip():
                st.error("🛑 **Atenção:** É obrigatório informar a **Especialidade Médica** para poder gerar o despacho.")
            else:
                tipo_slug = "ESCALA" if tipo_servico_selecionado == "Escala Médica" else "PRODUCAO"
                primeiro_nome_forn_p = prod_fornecedor.split()[0].replace("/", "_") if prod_fornecedor else "Empresa"
                nome_saida_prod = f"DESPACHO_{prod_hospital_sigla}_{tipo_slug}_{prod_protocolo}_{primeiro_nome_forn_p}.docx"

                if st.button(f"📝 Gerar e Descarregar Despacho ({tipo_servico_selecionado})", key="btn_exec_prod", type="primary"):
                    with st.spinner("A gerar documento Word e a registar na folha de cálculo..."):
                        doc_p = DocxTemplate(caminho_template_prod)
                        lista_nfs_p = df_editado_prod.to_dict(orient="records")
                        termo_servico = "escala médica" if tipo_servico_selecionado == "Escala Médica" else "produção médica"

                        contexto_p = {
                            "protocolo": prod_protocolo,
                            "hospital_nome": prod_hospital_nome if prod_hospital_nome else prod_hospital_sigla,
                            "hospital_sigla": prod_hospital_sigla,
                            "fornecedor_nome": prod_fornecedor,
                            "cnpj": prod_cnpj,
                            "valor_total": valor_total_str_p,
                            "valor_extenso": valor_extenso_str_p,
                            "competencia": prod_competencia,
                            "contrato": prod_contrato,
                            "vigencia_inicio": prod_vig_inicio,
                            "vigencia_fim": prod_vig_fim,
                            "empenho": prod_empenho,
                            "especialidade": prod_especialidade.strip(),
                            "tipo_servico_texto": termo_servico,
                            "tipo_servico": termo_servico,
                            "tipo_producao": termo_servico,
                            "escala_medica": termo_servico,
                            "nfs": lista_nfs_p,
                            "tem_inconformidade": (tem_inconformidade_p != "Não (Parecer Favorável)"),
                            "texto_inconformidade": texto_inconformidade_p,
                            "assinante_elaborador": auditor_nome,
                            "cargo_elaborador": auditor_cargo,
                            "exige_diretoria": exige_diretoria_p,
                        }

                        try:
                            doc_p.render(contexto_p)
                            buffer_p = io.BytesIO()
                            doc_p.save(buffer_p)
                            buffer_p.seek(0)
                            docx_bytes_p = buffer_p.getvalue()

                            novo_registo_prod = pd.DataFrame([{
                                "Data/Hora": datetime.now().strftime("%d/%m/%Y %H:%M"),
                                "Divisão (DAH)": "DAH",
                                "Tipo de Processo": tipo_servico_selecionado,
                                "Nº Protocolo": prod_protocolo,
                                "Unidade Hospitalar": prod_hospital_sigla,
                                "Empresa / Fornecedor": primeiro_nome_forn_p,
                                "Especialidade": prod_especialidade.strip(),
                                "Valor do Processo (R$)": total_prod,
                                "Pacientes (nomes e datas das Cirurgias)": "-",
                                "Responsável": auditor_nome
                            }])

                            df_existente = conn.read(ttl=0)
                            if df_existente is None or df_existente.empty:
                                df_atualizado = novo_registo_prod
                            else:
                                df_atualizado = pd.concat([df_existente, novo_registo_prod], ignore_index=True)
                            conn.update(data=df_atualizado)
                            st.success("✅ Registo concluído com sucesso na folha de cálculo!")

                            disparar_download_imediato(docx_bytes_p, nome_saida_prod)
                            st.info(f"O download do ficheiro **{nome_saida_prod}** foi iniciado diretamente.")
                        except Exception as e:
                            st.error(f"⚠️ Erro ao processar ou registar na Folha: {repr(e)}")

# Rodapé
st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: #888888; font-size: 0.85rem; padding: 10px 0;">
        Desenvolvido por <strong>Evandro Freire</strong>
    </div>
    """,
    unsafe_allow_html=True
)
