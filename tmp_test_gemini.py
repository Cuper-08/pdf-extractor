import sys
import os

# Append project dir to path so we can import from extrator_standalone
sys.path.append(r"C:\Users\Cuper\OneDrive\Documents\Projetos Antigravity\Extrator de dados N8N")

import extrator_standalone as ex
import fitz

pdf_path = r"C:\Users\Cuper\OneDrive\Documents\Projetos Antigravity\Extrator de dados N8N\dist\TESTES\Anais_Agrocentroeste_2017_1.pdf"

# Make sure we have the config loaded
config = ex.load_config()
api_key = config.get("gemini_api_key", "")

if not api_key:
    print("API KEY NOT FOUND IN CONFIG!")
    sys.exit(1)

doc = fitz.open(pdf_path)
page_text = doc[13].get_text("text") # Page 14

print("=== TEXTO DA PÁGINA 14 ===")
print(page_text)
print("\n=== SOLICITANDO AO GEMINI ===")

try:
    markdown = ex.extract_from_gemini(page_text, api_key)
    print(markdown)
    print("\n=== PARSEO ===")
    parsed = ex.parse_markdown_table_to_dicts(markdown)
    for row in parsed:
        print(row)
        
except Exception as e:
    print(f"ERRO: {e}")
