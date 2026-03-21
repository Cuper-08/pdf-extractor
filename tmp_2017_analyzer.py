import fitz
import re

pdf_path = r"C:\Users\Cuper\OneDrive\Documents\Projetos Antigravity\Extrator de dados N8N\dist\TESTES\Anais_Agrocentroeste_2017_1.pdf"
out_path = r"C:\Users\Cuper\OneDrive\Documents\Projetos Antigravity\Extrator de dados N8N\tmp_2017.txt"

with open(out_path, "w", encoding="utf-8") as f:
    try:
        doc = fitz.open(pdf_path)
        found_emails = False
        for i in range(len(doc)):
            page = doc[i]
            text = page.get_text("text")
            emails = re.findall(r'[\w\.-]+@[\w\.-]+', text)
            if emails:
                f.write(f"--- PÁGINA {i+1} ---\n")
                f.write(f"EMAILS ENCONTRADOS: {emails}\n")
                # print the end of the page (last 1000 chars) where footers usually are
                f.write("--- FINAL DA PÁGINA ---\n")
                f.write(text[-2000:])
                f.write("\n\n" + "="*50 + "\n\n")
                found_emails = True
                break # Just need one example
                
        if not found_emails:
            f.write("Nenhum email encontrado no PDF via texto puro.\n")
    except Exception as e:
        f.write(f"Erro: {e}")
