import requests
import time
import json
import glob
import os

pdf_path = "chunks_temporarios/Medio (1)_paginas_1_a_40.pdf"
if not os.path.exists(pdf_path):
    print(f"Erro: Arquivo {pdf_path} não encontrado.")
    exit(1)

url_prod = "https://n8n.hsbmarketing.com.br/webhook/fatiador-api"

print(f"Testando PROD com {pdf_path}...")
start_time = time.time()
try:
    with open(pdf_path, 'rb') as f:
        resp = requests.post(url_prod, files={'input': ('test.pdf', f, 'application/pdf')}, timeout=120)
        print(f"Status Code: {resp.status_code}")
        with open("test_output.json", "w", encoding="utf-8") as out_f:
            if resp.status_code == 200:
                json.dump(resp.json(), out_f, indent=2, ensure_ascii=False)
            else:
                out_f.write(resp.text)
        print("Salvo em test_output.json")
except Exception as e:
    print("PROD ERRO:", e)
print(f"Tempo decorrido: {time.time() - start_time:.2f} segundos")
