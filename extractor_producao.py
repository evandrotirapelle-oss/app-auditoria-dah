import io
import pdfplumber
import re

def extrair_dados_producao_medica(pdf_bytes):
    """
    Extrator estrito para produção médica da FUNEAS.
    Foca exclusivamente na tabela de resumo do Memorando inicial para recolher 
    apenas os dados oficiais de Contrato, Empenho, Notas Fiscais e Valores.
    """
    dados = {
        "protocolo": "",
        "hospital_sigla": "",
        "fornecedor_nome": "",
        "cnpj": "",
        "contrato": "",
        "empenho": "",
        "competencia": "",
        "especialidade": "",
        "nfs": []
    }

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            total_paginas = len(pdf.pages)
            texto_capa = pdf.pages[0].extract_text() if total_paginas > 0 else ""

            texto_geral = ""
            for pagina in pdf.pages:
                t = pagina.extract_text()
                if t:
                    texto_geral += t + "\n"

            texto_limpo = texto_geral.replace(" | ", " ").replace("\r", "")

            # 1. Protocolo
            match_prot = re.search(r"Protocolo[:\s]*([\d]{2}\.[\d]{3}\.[\d]{3}-\d)", texto_capa, re.IGNORECASE)
            if not match_prot:
                match_prot = re.search(r"([\d]{2}\.[\d]{3}\.[\d]{3}-\d)", texto_limpo)
            if match_prot:
                dados["protocolo"] = match_prot.group(1).strip()

            # 2. Sigla do Hospital
            match_orgao = re.search(r"Órgão Cadastro[:\s]*SESA/([A-Z]{3,6})", texto_capa, re.IGNORECASE)
            if not match_orgao:
                match_orgao = re.search(r"\b([A-Z]{3,6})\s*-\s*PAGAMENTO", texto_limpo, re.IGNORECASE)
            if match_orgao:
                dados["hospital_sigla"] = match_orgao.group(1).strip()

            # 3. CNPJ do Fornecedor (ignora o da FUNEAS)
            cnpjs = re.findall(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b", texto_limpo)
            for cnpj in cnpjs:
                if "24.039.073" not in cnpj:
                    dados["cnpj"] = cnpj
                    break

            # 4. Fornecedor
            match_forn = re.search(r"FORNECEDOR[:\s]*([^\n]+)", texto_limpo, re.IGNORECASE)
            if match_forn:
                f_txt = match_forn.group(1).strip()
                if "TIPO" not in f_txt and len(f_txt) > 3:
                    dados["fornecedor_nome"] = f_txt

            # 5. Contrato e Empenho globais do Memorando
            match_cont = re.search(r"Contrato[^\d]*([\d/]+)", texto_limpo, re.IGNORECASE)
            if match_cont:
                dados["contrato"] = match_cont.group(1).strip()

            match_emp = re.search(r"(?:Empenho|Nota de Despesa)[^\d]*([\d/]+)", texto_limpo, re.IGNORECASE)
            if match_emp:
                dados["empenho"] = match_emp.group(1).strip()

            # 6. Competência
            match_comp = re.search(r"(?:COMPETÊNCIA|COMPETENCIA|MÊS)[:\s]*([A-Za-zÇç/0-9\s]+)", texto_limpo, re.IGNORECASE)
            if match_comp:
                dados["competencia"] = match_comp.group(1).strip().split("\n")[0][:30]

            # 7. Extração rigorosa baseada na Tabela do Memorando (Páginas 1 e 2)
            # Vamos procurar especificamente nas tabelas das primeiras páginas onde consta o resumo de pagamento
            nfs_encontradas = []
            for i in range(min(3, total_paginas)):
                tabelas = pdf.pages[i].extract_tables()
                for tabela in tabelas:
                    for linha in tabela:
                        # Limpa células vazias ou nulas
                        celulas = [str(c).strip() for c in linha if c and str(c).strip() != ""]
                        if not celulas:
                            continue
                        
                        # Uma linha válida de nota no memorando da FUNEAS costuma ter pelo menos 4 a 6 colunas 
                        # contendo o número do item, contrato, empenho, número da nota, data e valor monetário.
                        linha_unida = " ".join(celulas)
                        
                        # Procura explicitamente por uma estrutura de Nota Fiscal na tabela do memorando:
                        # Exemplo: Número da Nota (1 a 5 dígitos), Data (DD/MM/AAAA) e Valor com vírgula ou formato monetário
                        match_tabela_nf = re.search(r"\b(\d{1,5})\b\s+(\d{2}/\d{2}/\d{4})\s+(R\$\s*)?([\d\.]+,\d{2})", linha_unida)
                        if match_tabela_nf:
                            num_nf = match_tabela_nf.group(1)
                            data_nf = match_tabela_nf.group(2)
                            val_nf = match_tabela_nf.group(4).replace("R$", "").strip()
                            
                            # Validação estrita: evita apanhar o número do item da linha (geralmente 1 ou 2 isolados se não tiver data associada na mesma lógica)
                            if int(num_nf) > 0 and not any(n["numero"] == num_nf for n in nfs_encontradas):
                                nfs_encontradas.append({
                                    "numero": num_nf,
                                    "data_emissao": data_nf,
                                    "valor": val_nf
                                })

            if nfs_encontradas:
                dados["nfs"] = nfs_encontradas
            else:
                dados["nfs"] = [{"numero": "", "data_emissao": "", "valor": ""}]

    except Exception as e:
        print(f"Erro na extração de produção: {e}")

    return dados