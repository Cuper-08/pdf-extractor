import fitz

pdf_path = r"C:\Users\Cuper\OneDrive\Documents\Projetos Antigravity\Extrator de dados N8N\dist\TESTES\Anais_Agro Centro-Oeste Familiar 2018.pdf"
out_path = r"C:\Users\Cuper\OneDrive\Documents\Projetos Antigravity\Extrator de dados N8N\tmp_page24.txt"

with open(out_path, "w", encoding="utf-8") as f:
    try:
        doc = fitz.open(pdf_path)
        page = doc[23] # 0-indexed, so page 24 is index 23
        text = page.get_text("text")
        f.write("--- GET_TEXT('text') ---\n")
        f.write(text)
        f.write("\n\n--- GET_TEXT('blocks') ---\n")
        blocks = page.get_text("blocks")
        for b in blocks:
            f.write(str(b) + "\n")
            
        f.write("\n\n--- GET_TEXT('dict') lines ---\n")
        d = page.get_text("dict")
        for block in d.get("blocks", []):
            if block.get("type") == 0:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        f.write(span.get("text", "") + " ")
                    f.write("\n")
    except Exception as e:
        f.write(f"Erro: {e}")
