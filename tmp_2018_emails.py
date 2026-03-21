import fitz
import re

pdf_path = r"C:\Users\Cuper\OneDrive\Documents\Projetos Antigravity\Extrator de dados N8N\dist\TESTES\Anais_Agro Centro-Oeste Familiar 2018.pdf"
out_path = r"C:\Users\Cuper\OneDrive\Documents\Projetos Antigravity\Extrator de dados N8N\tmp_2018_emails.txt"

with open(out_path, "w", encoding="utf-8") as f:
    try:
        doc = fitz.open(pdf_path)
        all_emails = set()
        for i in range(len(doc)):
            page = doc[i]
            text = page.get_text("text")
            # find emails
            emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w{2,}', text)
            for e in emails:
                all_emails.add(e.lower())
                
        f.write(f"Total de emails únicos encontrados em todo o PDF 2018: {len(all_emails)}\n")
        f.write("Amostra (até 20):\n")
        for e in list(all_emails)[:20]:
            f.write(e + "\n")
            
    except Exception as e:
        f.write(f"Erro: {e}")
