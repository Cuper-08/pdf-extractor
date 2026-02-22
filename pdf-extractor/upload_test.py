"""
Script simples de upload para teste rápido.
"""
import requests
import json
import os
import time

t0 = time.time()
PDF_PATH = os.path.join("tests", "Medio (1).pdf")
size_mb = os.path.getsize(PDF_PATH) / (1024 * 1024)
print(f"Enviando {size_mb:.1f} MB → http://localhost:8001/extract ...")

with open(PDF_PATH, "rb") as f:
    r = requests.post(
        "http://localhost:8001/extract",
        files={"file": (os.path.basename(PDF_PATH), f, "application/pdf")},
        timeout=600,
    )

elapsed = time.time() - t0
print(f"HTTP Status: {r.status_code} ({elapsed:.1f}s)")
try:
    data = r.json()
    print(json.dumps(data, indent=2, ensure_ascii=False))
except Exception:
    print(r.text[:1000])
