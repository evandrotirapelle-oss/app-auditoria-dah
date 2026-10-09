import io
import re
from num2words import num2words
import pdfplumber

CNPJ_FUNEAS = "21.059.213/0001-44"

MAPA_HOSPITAIS = {
    "HIWM": "Hospital Infantil Waldemar Monastier",
    "WALDEMAR MONASTIER": "Hospital Infantil Waldemar Monastier",
    "HRS": "Hospital Regional do Sudoeste Walter Alberto Pecoits",
    "SUDOESTE": "Hospital Regional do Sudoeste Walter Alberto Pecoits",
    "WALTER ALBERTO PECOITS": "Hospital Regional do Sudoeste Walter Alberto Pecoits",
    "HZNL": "Hospital Dr. Anísio Figueiredo - Zona Norte Londrina",
    "HZN": "Hospital Dr. Anísio Figueiredo - Zona Norte Londrina",
    "ANISIO FIGUEIREDO": "Hospital Dr. Anísio Figueiredo - Zona Norte Londrina",
    "HRL": "Hospital Regional do Litoral",
    "LITORAL": "Hospital Regional do Litoral",
    "HGG": "Hospital Regional de Guaraqueçaba",
    "HILP": "Hospital Infantil Lucian de Paula",
    "HMT": "Hospital Regional da Mata Atlântica",
}

def formatar_valor_reais(valor_float: float) -> str:
    return f"{valor_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def limpar_valor_nfe(v_str):
    v = v_str.replace("R$", "").strip()
    # O Portal da NF-e por vezes imprime com 3 casas decimais (ex: 669,780)
    if re.search(r",\d{2}0$", v):
        v = v[:-1]
    return v

def extrair_dados_processo(pdf_bytes: bytes) -> dict:
    paginas_texto = []
    texto_completo = ""

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for i, pag in enumerate(pdf.pages):
            txt = pag.extract_text() or ""
            paginas_texto.append((i + 1, txt))
            texto_completo += f"\n--- PAGINA {i+1} ---\n" + txt

    # 1. PROTOCOLO
    texto_folha1 = paginas_texto[0][1] if paginas_texto else ""
    m_proto = re.search(r"Protocolo:\s*([0-9]{2}\.[0-9]{3}\.[0-9]{3}-[0-9])", texto_folha1)
    if not m_proto:
        m_proto = re.search(r"\b([0-9]{2}\.[0-9]{3}\.[0-9]{3}-[0-9])\b", texto_completo)
    protocolo = m_proto.group(1).strip() if m_proto else ""

    # 2. LOCALIZAR TEXTOS-CHAVE
    texto_memo = ""
    texto_empenho = ""
    for _, txt in paginas_texto:
        if ("Memorando" in txt or "MEMORANDO" in txt) and ("notas fiscais" in txt or "encaminhar para pagamento" in txt):
            texto_memo = txt
        if "Nota de Despesa" in txt and "Itens do Empenho" in txt:
            texto_empenho = txt

    # 3. UNIDADE HOSPITALAR
    hospital_sigla = "HZN"
    hospital_nome = "Hospital Dr. Anísio Figueiredo - Zona Norte Londrina"
    contexto_unidade = texto_folha1 + "\n" + texto_memo
    for sigla, nome in MAPA_HOSPITAIS.items():
        if re.search(rf"\b{sigla}\b", contexto_unidade, re.IGNORECASE) or re.search(rf"{nome}", contexto_unidade, re.IGNORECASE):
            if sigla in ["HIWM", "HRS", "HZNL", "HZN", "HRL", "HGG", "HILP", "HMT"]:
                hospital_sigla = sigla
            elif "SUDOESTE" in sigla or "PECOITS" in sigla:
                hospital_sigla = "HRS"
            else:
                hospital_sigla = "HZN"
            hospital_nome = nome
            break

    # 4. FORNECEDOR E CNPJ
    fornecedor_nome = "HEXAGON DISTRIBUIÇÃO E LOGÍSTICA DE PRODUTOS"
    cnpj = ""
    cnpjs_bloqueados = [CNPJ_FUNEAS, "24.039.073/0001-55", "21059213000144", "24039073000155"]
    
    m_forn = re.search(r"Credor:\s*\d+\s*-\s*([A-Z0-9\.\s\-\–]+?)(?=\s*CNPJ|\n|Endereço)", texto_empenho)
    if m_forn:
        fornecedor_nome = m_forn.group(1).strip().replace("\n", " ")
        fornecedor_nome = re.sub(r"\s+", " ", fornecedor_nome)

    if texto_empenho:
        m_c = re.search(r"Credor:.*?(?:CNPJ[^\d]*([0-9]{2}\.[0-9]{3}\.[0-9]{3}/[0-9]{4}-[0-9]{2}))", texto_empenho, re.DOTALL)
        if m_c and m_c.group(1).strip() not in cnpjs_bloqueados:
            cnpj = m_c.group(1).strip()

    if not cnpj:
        todos_cnpjs = re.findall(r"([0-9]{2}\.[0-9]{3}\.[0-9]{3}/[0-9]{4}-[0-9]{2})", texto_completo)
        for c in todos_cnpjs:
            if c not in cnpjs_bloqueados:
                cnpj = c
                break

    # 5. CONTRATO E EMPENHO
    contrato = ""
    empenho = ""
    m_cont = re.search(r"Contrato:\s*([0-9]{1,4}/[0-9]{4})", texto_empenho) or re.search(r"CONTRATO\s*([0-9]{1,4}/[0-9]{4})", texto_folha1, re.IGNORECASE)
    if m_cont: contrato = m_cont.group(1).strip()
    
    m_emp = re.search(r"Número:\s*([0-9]{1,5}/[0-9]{4})", texto_empenho) or re.search(r"EMPENHO\s*([0-9]{1,5}/[0-9]{4})", texto_folha1, re.IGNORECASE)
    if m_emp: empenho = m_emp.group(1).strip()

    # 6. COMPETÊNCIA E VIGÊNCIA
    m_comp = re.search(r"COMPETÊNCIA:?\s*([0-9]{2}/[0-9]{4}|[A-Za-zçãéíóú]+/[0-9]{4})", texto_folha1, re.IGNORECASE)
    competencia = m_comp.group(1).strip() if m_comp else "SETEMBRO/2026"
    
    m_vig = re.search(r"Vigência:\s*([0-9]{2}/[0-9]{2}/[0-9]{4})\s*[a|à]\s*([0-9]{2}/[0-9]{2}/[0-9]{4})", texto_empenho, re.IGNORECASE)
    vigencia_inicio = m_vig.group(1) if m_vig else "26/03/2026"
    vigencia_fim = m_vig.group(2) if m_vig else "25/03/2028"

    # ==========================================================
    # 7. EXTRAÇÃO SEGURA DAS NOTAS FISCAIS (Fontes Nativas)
    # ==========================================================
    nfs_dict = {}

    # FONTE 1: Despacho Fiscal / Parecer da Contabilidade (Presente em todos os cadernos)
    for _, txt in paginas_texto:
        if "Despacho" in txt and ("aspectos fiscais" in txt or "Status Nota Fiscal" in txt):
            # Extrai blocos do formato: "221.732 17/09/2026 Produto 1899.79" ou "221.732 17/09/2026 Produto R$ 328,82"
            linhas_trib = re.findall(r"(\d{3}\.\d{3})\s+(\d{2}/\d{2}/\d{4})\s+[A-Za-zÀ-ÿ]+\s+(?:R\$\s*)?([\d\.,]+)", txt)
            for n_raw, d_raw, v_raw in linhas_trib:
                n_limpo = n_raw.replace(".", "").strip()
                v_limpo = limpar_valor_nfe(v_raw)
                if n_limpo not in nfs_dict:
                    nfs_dict[n_limpo] = {
                        "numero": n_limpo, "data_emissao": d_raw.strip(), "valor": v_limpo,
                        "paciente": "", "data_cirurgia": ""
                    }

    # FONTE 2: Espelhos Oficiais da NF-e (DANFE ou Portal SPED)
    for _, txt_pag in paginas_texto:
        is_danfe = "DANFE" in txt_pag or "DOCUMENTO AUXILIAR DA NOTA FISCAL" in txt_pag
        is_sped = "Portal da Nota Fiscal Eletrônica" in txt_pag

        if is_danfe or is_sped:
            m_num = re.search(r"Número(?:\s+NF-e)?\s*\n?(\d{5,6})", txt_pag)
            if not m_num: m_num = re.search(r"N[°º\.]*\s*000\.?(\d{3}\.?\d{3})", txt_pag)
            if not m_num: m_num = re.search(r"N[°º\.]*\s*(\d{5,6})", txt_pag)

            m_dt = re.search(r"Data de Emissão\s*\n?(\d{2}/\d{2}/\d{4})", txt_pag)
            if not m_dt: m_dt = re.search(r"DATA D[EA] EMISSÃO\s*\n?(\d{2}/\d{2}/\d{4})", txt_pag)

            m_val = re.search(r"Valor Total da Nota Fiscal\s*\n?([\d\.,]+)", txt_pag)
            if not m_val: m_val = re.search(r"VALOR TOTAL DA NOTA\s*\n?([\d\.,]+)", txt_pag)

            if m_num and m_dt and m_val:
                n_limpo = m_num.group(1).replace(".", "").strip()
                v_limpo = limpar_valor_nfe(m_val.group(1))
                if n_limpo not in nfs_dict:
                    nfs_dict[n_limpo] = {
                        "numero": n_limpo, "data_emissao": m_dt.group(1).strip(), "valor": v_limpo,
                        "paciente": "", "data_cirurgia": ""
                    }

    # FONTE 3: Capa do Protocolo - Campo Detalhamento (Se falharem os anteriores)
    if not nfs_dict and texto_folha1:
        m_det = re.search(r"NOTA(?:S)?\s+FISCA(?:L|IS)[:\s]*([0-9\-\s/]+?)\s+EMISS[ÃA]O\s+([0-9]{2}/[0-9]{2}/[0-9]{4})", texto_folha1, re.IGNORECASE)
        if m_det:
            bloco_nfs = m_det.group(1)
            data_capa = m_det.group(2).strip()
            nums_capa = re.findall(r"\b(\d{5,6})\b", bloco_nfs)

            for n_capa in nums_capa:
                m_val_solto = re.search(rf"{n_capa}[\s\S]{{1,600}}?VALOR TOTAL DA NOTA[^\d]*([\d\.,]+)", texto_completo, re.IGNORECASE)
                if not m_val_solto:
                    m_val_solto = re.search(rf"{n_capa}[\s\S]{{1,600}}?Valor Total da Nota Fiscal[^\d]*([\d\.,]+)", texto_completo, re.IGNORECASE)
                
                v_encontrado = limpar_valor_nfe(m_val_solto.group(1)) if m_val_solto else "0,00"
                if n_capa not in nfs_dict:
                    nfs_dict[n_capa] = {
                        "numero": n_capa, "data_emissao": data_capa, "valor": v_encontrado,
                        "paciente": "", "data_cirurgia": ""
                    }

    # Limpeza e Ordenação
    nfs_encontradas = []
    num_contrato_limpo = contrato.split("/")[0] if contrato else ""
    num_empenho_limpo = empenho.split("/")[0] if empenho else ""

    for n, dados in nfs_dict.items():
        # Ignora números que foram falsamente capturados (ex: número do empenho)
        if n not in [num_contrato_limpo, num_empenho_limpo]:
            nfs_encontradas.append(dados)

    nfs_encontradas = sorted(nfs_encontradas, key=lambda x: x["numero"])

    # 8. TOTAIS E EXTENSO
    total_reais = 0.0
    for nf in nfs_encontradas:
        v = nf["valor"].replace(".", "").replace(",", ".").replace("R$", "").strip()
        try:
            total_reais += float(v)
        except ValueError:
            pass

    valor_total_formatado = formatar_valor_reais(total_reais)
    try:
        valor_extenso = num2words(total_reais, lang="pt_BR", to="currency").lower()
    except Exception:
        valor_extenso = ""

    return {
        "protocolo": protocolo,
        "hospital_nome": hospital_nome,
        "hospital_sigla": hospital_sigla,
        "fornecedor_nome": fornecedor_nome,
        "cnpj": cnpj,
        "valor_total": valor_total_formatado,
        "valor_extenso": valor_extenso,
        "competencia": competencia,
        "contrato": contrato,
        "vigencia_inicio": vigencia_inicio,
        "vigencia_fim": vigencia_fim,
        "empenho": empenho,
        "nfs": nfs_encontradas
    }