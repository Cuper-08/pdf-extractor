import pandas as pd
import fitz
import sys

out_path = r"C:\Users\Cuper\OneDrive\Documents\Projetos Antigravity\Extrator de dados N8N\tmp_output.txt"
with open(out_path, "w", encoding="utf-8") as f:
    excel_path = r"C:\Users\Cuper\OneDrive\Documents\Projetos Antigravity\Extrator de dados N8N\dist\TESTES\Anais_Agro Centro-Oeste Familiar 2018_Extraido.xlsx"
    pdf_path = r"C:\Users\Cuper\OneDrive\Documents\Projetos Antigravity\Extrator de dados N8N\dist\TESTES\Anais_Agro Centro-Oeste Familiar 2018.pdf"

    f.write("--- ANALISANDO EXCEL ---\n")
    try:
        df = pd.read_excel(excel_path)
        f.write(f"Total de linhas: {len(df)}\n")
        f.write(f"Colunas: {df.columns.tolist()}\n")
        f.write("Amostra dos dados (primeiras 5 linhas):\n")
        f.write(df.head().to_string() + "\n")
        
        # Check emails
        if 'E-mail dos Autores' in df.columns:
            empty_emails = df['E-mail dos Autores'].isna().sum()
            f.write(f"E-mails vazios (E-mail dos Autores): {empty_emails} de {len(df)}\n")
        elif 'E-Mail' in df.columns:
            empty_emails = df['E-Mail'].isna().sum()
            f.write(f"E-mails vazios (E-Mail): {empty_emails} de {len(df)}\n")
        else:
            f.write("Nenhuma coluna de email encontrada.\n")
            
        f.write("Amostras com email vazio:\n")
        f.write(df[df.iloc[:, 2].isna()].head().to_string() + "\n")
            
    except Exception as e:
        f.write(f"Erro ao ler excel: {e}\n")

    f.write("\n--- ANALISANDO PDF (Páginas 20 a 25) ---\n")
    try:
        doc = fitz.open(pdf_path)
        for i in range(20, min(25, len(doc))):
            page = doc[i]
            text = page.get_text("text")
            f.write(f"\n--- PÁGINA {i+1} ---\n")
            f.write(text[:1000] + "\n")
            f.write("...\n")
            # look for emails
            import re
            emails = re.findall(r'[\w\.-]+@[\w\.-]+', text)
            f.write(f"Emails encontrados na página {i+1}: {emails}\n")
            
    except Exception as e:
        f.write(f"Erro ao ler PDF: {e}\n")
