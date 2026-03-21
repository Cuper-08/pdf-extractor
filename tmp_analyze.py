import pandas as pd
import fitz

excel_path = r"C:\Users\Cuper\OneDrive\Documents\Projetos Antigravity\Extrator de dados N8N\dist\TESTES\Anais_Agro Centro-Oeste Familiar 2018_Extraido.xlsx"
pdf_path = r"C:\Users\Cuper\OneDrive\Documents\Projetos Antigravity\Extrator de dados N8N\dist\TESTES\Anais_Agro Centro-Oeste Familiar 2018.pdf"

print("--- ANALISANDO EXCEL ---")
try:
    df = pd.read_excel(excel_path)
    print(f"Total de linhas: {len(df)}")
    print(f"Colunas: {df.columns.tolist()}")
    print("Amostra dos dados (primeiras 5 linhas):")
    print(df.head())
    
    # Check emails
    if 'E-Mail' in df.columns:
        empty_emails = df['E-Mail'].isna().sum()
        print(f"E-mails vazios: {empty_emails} de {len(df)}")
except Exception as e:
    print(f"Erro ao ler excel: {e}")

print("\n--- ANALISANDO PDF (Páginas 20 a 25) ---")
try:
    doc = fitz.open(pdf_path)
    for i in range(20, min(25, len(doc))):
        page = doc[i]
        text = page.get_text("text")
        print(f"--- PÁGINA {i+1} ---")
        print(text[:1000]) # Primeiros 1000 caracteres
        print("...")
        # look for emails
        import re
        emails = re.findall(r'[\w\.-]+@[\w\.-]+', text)
        print(f"Emails encontrados na página {i+1}: {emails}")
        
except Exception as e:
    print(f"Erro ao ler PDF: {e}")
