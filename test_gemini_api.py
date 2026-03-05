import requests
import json

def test_gemini_api(api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{
            "parts": [{"text": "Oi, você está funcionando? Responda apenas 'SIM' ou o motivo do erro."}]
        }]
    }

    print(f"--- Testando API do Gemini ---")
    try:
        response = requests.post(url, headers=headers, json=payload)
        status_code = response.status_code
        print(f"Status Code: {status_code}")
        
        if status_code == 200:
            data = response.json()
            try:
                text_response = data['candidates'][0]['content']['parts'][0]['text']
                print(f"Resposta do Gemini: {text_response.strip()}")
            except (KeyError, IndexError):
                print(f"Erro ao processar JSON: {json.dumps(data, indent=2)}")
        elif status_code == 429:
            print("ERRO: Cota excedida (Resource Exhausted / No Credits).")
            print(f"Detalhes: {response.text}")
        elif status_code == 400:
            print("ERRO: Requisição inválida ou Chave expirada/inválida.")
            print(f"Detalhes: {response.text}")
        else:
            print(f"ERRO DESCONHECIDO (HTTP {status_code}):")
            print(response.text)
            
    except Exception as e:
        print(f"Erro na conexão: {e}")

if __name__ == "__main__":
    with open("config_extrator.json", "r") as f:
        config = json.load(f)
    
    api_key = config.get("gemini_api_key")
    if api_key:
        test_gemini_api(api_key)
    else:
        print("Chave Gemini não encontrada no config_extrator.json")
