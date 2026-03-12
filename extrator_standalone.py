import os
import sys
import time
import json
import threading
import subprocess
import requests
import fitz  # PyMuPDF
import pandas as pd
import customtkinter as ctk
import ctypes  # << Necessário para forçar o ícone na barra de tarefas do Windows
import concurrent.futures  # Multi-threading de alta performance
import tkinter as tk
from tkinter import filedialog, messagebox

# ==========================================
# CONFIGURAÇÕES DO SUPABASE / SEGURANÇA
# ==========================================
SUPABASE_URL = "https://qhjyvdywvdcbdgicwjzu.supabase.co/rest/v1"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFoanl2ZHl3dmRjYmRnaWN3anp1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzE1MzU4NDUsImV4cCI6MjA4NzExMTg0NX0.d9wzf3laY6suarJh_InWij_JjOUcqCW-5mpDAKJuC68"

# ==========================================
# ARQUIVO LOCAL DE CONFIGURAÇÃO (SALVAR CHAVES)
# ==========================================
CONFIG_FILE = "config_extrator.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {"gemini_api_key": "", "license_key": ""}

def save_config(config_data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config_data, f)

# ==========================================
# FUNÇÕES DE HARDWARE ID E SEGURANÇA
# ==========================================
def get_hardware_id():
    """Gera um identificador único baseada na placa-mãe/processador (Apenas Windows)"""
    try:
        # Tenta PowerShell primeiro (recomendado para Windows 11 que depreciou o wmic nativo)
        cmd = ['powershell', '-NoProfile', '-Command', '(Get-CimInstance -Class Win32_ComputerSystemProduct).UUID']
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        if output:
            return output
    except Exception:
        pass
        
    try:
        # Fallback de segurança CMD antigo, mas sem poluir o console com mensagem vermelha
        output = subprocess.check_output('wmic csproduct get uuid', shell=True, stderr=subprocess.DEVNULL).decode().strip().split('\n')
        hwid = output[1].strip()
        if hwid:
            return hwid
    except Exception:
        pass
        
    # Ultimo recurso se todas as permissões do Windows falharem (Usa a Placa de Rede MAC)
    import uuid
    return str(uuid.getnode())

def validate_license(license_key):
    """Bate no Supabase, verifica se a licença é válida e casa com o Computador Atual."""
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    
    # 1. Busca a Licença
    resp = requests.get(f"{SUPABASE_URL}/licenses?license_key=eq.{license_key}", headers=headers)
    if resp.status_code != 200:
        return False, f"Erro de conexão com servidor de licenças. {resp.status_code}"
    
    data = resp.json()
    if not data:
        return False, "Licença não encontrada."
        
    lic = data[0]
    
    if not lic.get("is_active"):
        return False, "Sua licença foi desativada/bloqueada. Contate o suporte."
        
    current_hwid = get_hardware_id()
    db_hwid = lic.get("hardware_id")
    
    # Se a licença é "Virgem" (nunca ativada), casamos ela com a máquina de agora!
    if db_hwid is None or db_hwid.strip() == "":
        patch_resp = requests.patch(
            f"{SUPABASE_URL}/licenses?license_key=eq.{license_key}", 
            headers=headers, 
            json={"hardware_id": current_hwid}
        )
        if patch_resp.status_code == 200:
            return True, f"Licença ativada c/ Sucesso nesta máquina! Olá, {lic.get('client_name')}!"
        else:
            return False, "Falha ao vincular sua licença na primeira ativação."
            
    # Se a Licença já tem um PC cadastrado, checa se é igual ao dono...
    if db_hwid != current_hwid:
        return False, "Essa licença já foi ativada em outro computador.\nO acesso não é permitido em múltiplas máquinas."
        
    return True, f"Login Autorizado. Bem-vindo, {lic.get('client_name')}"


# ==========================================
# CÓDIGO DO MOTOR DE EXTRAÇÃO E INTELIGÊNCIA
# ==========================================
SYSTEM_PROMPT = """
Você é um robô puramente extrativista e formatador de anais de congressos e periódicos acadêmicos em PDF. Sua única missão: extrair TÍTULO DO TRABALHO, NOME DOS AUTORES e E-MAIL de cada autor, e retornar EXCLUSIVAMENTE uma tabela Markdown.

=== PADRÃO DO DOCUMENTO (MUITO IMPORTANTE) ===
Os documentos seguem layouts variados. Procure em TODOS estes locais:
  1. TÍTULO DO TRABALHO: em MAIÚSCULAS e/ou negrito, centralizado no topo da 1ª página do artigo.
  2. AUTORES: logo abaixo do título, com números sobrescritos (ex: "Maria Silva¹, João Santos²").
  3. E-MAILS podem estar em QUALQUER um destes locais:
     a) RODAPÉ da mesma página (com sobrescritos: "¹ Mestranda, UEFS. maria@uefs.br")
     b) Bloco de AFILIAÇÃO logo após os nomes dos autores
     c) Seção "Corresponding author" ou "Autor correspondente" ou "E-mail:" ou "Contact:"
     d) Rodapé com asterisco (*) indicando autor de correspondência
     e) Linha com formato "Nome Sobrenome (email@dominio.br)"
     f) Blocos biográficos no final do artigo ("Sobre os autores")
     g) Cabeçalhos ou rodapés repetidos com informação de contato

=== REGRA DE OURO — UMA LINHA POR AUTOR ===
Se um trabalho tiver 4 autores, você DEVE gerar 4 linhas na tabela — uma para cada autor.
O título do trabalho deve ser REPETIDO em cada linha. NUNCA agrupe autores na mesma célula.
NUNCA OMITA UM AUTOR. Se há 5 nomes listados, devem haver 5 linhas.

=== CAÇA AO E-MAIL (OBSESSIVA) ===
1. Percorra CADA LINHA do texto procurando por padrões contendo "@".
2. Associe e-mails aos autores pelo índice numérico sobrescrito (¹²³⁴ ou 1.2.3.4 ou (1)(2) ou *).
3. Se um e-mail aparece isolado sem índice, associe-o ao autor mais próximo ou ao primeiro autor.
4. Se houver apenas 1 e-mail para múltiplos autores, coloque-o no primeiro autor e deixe os demais vazios.
5. Se o e-mail NÃO aparece neste trecho, deixe a célula VAZIA (não invente).

=== REGRAS OBRIGATÓRIAS DE FORMATAÇÃO ===
1. Cabeçalho EXATO: `| Títulos dos Trabalhos | Nomes dos Autores | E-mails dos Autores |`
2. Linha separadora EXATA: `|---|---|---|`
3. REMOVA quebras de linha (Enter) de dentro do TÍTULO. O título deve ser uma linha contínua.
4. LIMPEZA de nomes: remova números de afiliação (ex: "Maria Silva1" → "Maria Silva").
5. Ignore sumários, capas, referências bibliográficas e agradecimentos.
6. Sua resposta deve conter SOMENTE a tabela Markdown — sem texto antes ou depois.
"""

def extract_from_gemini(text_content, api_key):
    # Faz uma descoberta dinâmica do melhor modelo Flash disponível para esta Chave de API
    models_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    resp_models = requests.get(models_url)
    if resp_models.status_code != 200:
        raise Exception(f"Erro ao validar a chave da API do Gemini (HTTP {resp_models.status_code}): {resp_models.text}")
        
    available_models = [m.get('name') for m in resp_models.json().get('models', [])]
    
    # Busca pela preferência mais recente/moderna até versão fallback
    target_model = None
    for pref in ["models/gemini-2.5-flash", "models/gemini-flash-latest", "models/gemini-3-flash-preview", "models/gemini-2.0-flash-001"]:
        if pref in available_models:
            target_model = pref
            break
            
    if not target_model:
        flash_models = [m for m in available_models if 'flash' in m.lower()]
        if flash_models:
            target_model = flash_models[0]  # Pega o mais recente (não o último/mais antigo)
        else:
            raise Exception(f"Nenhum modelo 'Flash' encontrado na sua conta. Modelos disponíveis na chave: {available_models}")

    # Endpoint oficial dinâmico baseado no modelo encontrado
    url = f"https://generativelanguage.googleapis.com/v1beta/{target_model}:generateContent?key={api_key}"
    headers = {
        "Content-Type": "application/json"
    }
    
    payload = {
        "systemInstruction": {
            "parts": [{"text": SYSTEM_PROMPT}]
        },
        "contents": [{
            "parts": [{"text": f"Extraia os trabalhos deste texto:\n\n{text_content}"}]
        }],
        "generationConfig": {
            "temperature": 0.1
        }
    }
    
    response = requests.post(url, headers=headers, json=payload, timeout=120) # TIMEOUT INDUSTRIAL: Previne que o app trave infinitamente se a conexão da Google der DROP silencioso
    if response.status_code != 200:
        raise Exception(f"Erro da API do Gemini ({target_model}) (HTTP {response.status_code}): {response.text}")
        
    data = response.json()
    try:
        return data['candidates'][0]['content']['parts'][0]['text']
    except (KeyError, IndexError):
        raise Exception(f"Resposta inesperada do Gemini:\n{json.dumps(data, indent=2)}")

def extract_from_openai(text_content, api_key):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": f"Extraia os trabalhos deste texto:\n\n{text_content}"
            }
        ],
        "temperature": 0.1
    }
    
    response = requests.post(url, headers=headers, json=payload, timeout=120)
    if response.status_code != 200:
        raise Exception(f"Erro da API da OpenAI (HTTP {response.status_code}): {response.text}")
        
    data = response.json()
    try:
        return data['choices'][0]['message']['content']
    except (KeyError, IndexError):
        raise Exception(f"Resposta inesperada da OpenAI:\n{json.dumps(data, indent=2)}")

def parse_markdown_table_to_dicts(markdown_text):
    """Converte a string de tabela Markdown retornada pela LLM em JSON."""
    linhas = markdown_text.split('\n')
    linhas = [linha for linha in linhas if linha.strip() and '|' in linha]
    
    linhas_dados = [l for l in linhas if not l.replace(' ', '').replace('|', '').replace('-', '') == '']
    if not linhas_dados:
        return []
        
    chaves = ["Títulos dos Trabalhos", "Nomes dos Autores", "E-mails dos Autores"]
    linhas_conteudo = linhas_dados[1:]
    
    resultados = []
    for linha in linhas_conteudo:
        cols = [col.strip() for col in linha.split('|')][1:-1]
        
        if len(cols) >= 3:
            obj = {
                chaves[0]: cols[0],
                chaves[1]: cols[1],
                chaves[2]: cols[2]
            }
            resultados.append(obj)
            
    return resultados


# ==========================================
# FUNÇÕES DE PÓS-PROCESSAMENTO
# ==========================================
import re as _re

def consolidar_projetos(projetos):
    """
    Merge inteligente: une linhas com mesmo título+autor,
    priorizando o e-mail preenchido quando chunks diferentes
    capturam a mesma pessoa em momentos distintos.
    """
    mapa = {}
    chave_titulo = "Títulos dos Trabalhos"
    chave_autor  = "Nomes dos Autores"
    chave_email  = "E-mails dos Autores"
    
    for proj in projetos:
        titulo = (proj.get(chave_titulo) or "").strip()
        autor  = (proj.get(chave_autor)  or "").strip()
        email  = (proj.get(chave_email)  or "").strip()
        chave_composta = f"{titulo.lower()}|||{autor.lower()}"
        
        if chave_composta not in mapa:
            mapa[chave_composta] = {chave_titulo: titulo, chave_autor: autor, chave_email: email}
        else:
            if email and not mapa[chave_composta][chave_email]:
                mapa[chave_composta][chave_email] = email
    
    return list(mapa.values())


def expandir_por_autor(projetos):
    """
    Caso a IA retorne múltiplos autores agrupados numa célula
    (ex: 'Maria Silva, João Santos'), desdobra em linhas individuais.
    Remove números/símbolos sobrescritos dos nomes (¹²³⁴⁵⁶⁷⁸⁹⁰ e variantes).
    """
    chave_titulo = "Títulos dos Trabalhos"
    chave_autor  = "Nomes dos Autores"
    chave_email  = "E-mails dos Autores"
    sobrescritos = str.maketrans("", "", "¹²³⁴⁵⁶⁷⁸⁹⁰₁₂₃₄₅₆₇₈₉₀")
    
    expandido = []
    for proj in projetos:
        titulo  = (proj.get(chave_titulo) or "").strip()
        autores = (proj.get(chave_autor)  or "").strip()
        emails  = (proj.get(chave_email)  or "").strip()
        
        # Remove sobrescritos dos nomes
        autores_limpos = autores.translate(sobrescritos).strip()
        
        # Separa múltiplos autores (separados por vírgula ou ponto e vírgula)
        lista_autores = [a.strip() for a in _re.split(r"[;,]", autores_limpos) if a.strip()]
        # Separa múltiplos e-mails na mesma célula
        lista_emails  = [e.strip() for e in _re.split(r"[;,\s]+", emails) if "@" in e]
        
        if len(lista_autores) <= 1:
            # Já está no formato certo (1 autor por linha)
            expandido.append({
                chave_titulo: titulo,
                chave_autor:  autores_limpos or autores,
                chave_email:  emails
            })
        else:
            # Desdobra: um registro por autor
            for i, autor in enumerate(lista_autores):
                email_autor = lista_emails[i] if i < len(lista_emails) else ""
                expandido.append({
                    chave_titulo: titulo,
                    chave_autor:  autor,
                    chave_email:  email_autor
                })
    
    return expandido

# ==========================================
# FUNÇÃO DE SALVAMENTO COM FORMATAÇÃO
# ==========================================
def salvar_excel_formatado(projetos, filepath):
    """
    Salva a lista de projetos em Excel com:
    - Largura de coluna automática (ajusta ao conteúdo mais longo)
    - Cabeçalho em negrito
    - Fallback automático para arquivo de backup se o original estiver aberto
    Lança PermissionError com mensagem amigável se ambos falharem.
    """
    import openpyxl
    from openpyxl.styles import Font

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Resultados"

    colunas = ["Títulos dos Trabalhos", "Nomes dos Autores", "E-mails dos Autores"]

    # Cabeçalho em negrito
    for col_idx, nome_col in enumerate(colunas, start=1):
        cell = ws.cell(row=1, column=col_idx, value=nome_col)
        cell.font = Font(bold=True)

    # Dados
    for row_idx, proj in enumerate(projetos, start=2):
        ws.cell(row=row_idx, column=1, value=proj.get(colunas[0], ""))
        ws.cell(row=row_idx, column=2, value=proj.get(colunas[1], ""))
        ws.cell(row=row_idx, column=3, value=proj.get(colunas[2], ""))

    # Ajuste automático de largura de coluna
    for col in ws.columns:
        max_len = 0
        col_letter = col[0].column_letter
        for cell in col:
            try:
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max_len + 4, 80)

    # Tenta salvar no caminho original; fallback para _backup se aberto
    try:
        wb.save(filepath)
    except PermissionError:
        backup_path = filepath.replace(".xlsx", "_backup.xlsx")
        try:
            wb.save(backup_path)
            raise PermissionError(
                f"Arquivo Excel estava aberto. Dados salvos em:\n{backup_path}"
            )
        except Exception as e2:
            raise PermissionError(f"Não foi possível salvar o Excel: {e2}")

# ==========================================
# BOTÃO 3D METÁLICO (Canvas-based)
# ==========================================
class MetalButton3D(tk.Canvas):
    """Botão com efeito 3D metálico usando Canvas do tkinter.
    Simula gradiente, relevo e texto prateado."""
    
    # Paleta de cores para cada estado
    _STATES = {
        "normal":   {"top": "#1de9a0", "mid": "#0ecf85", "bot": "#0a9460", "shadow": "#065c3c", "text": "#d0ffe8", "border": "#0a7a50"},
        "hover":    {"top": "#26ffb3", "mid": "#18e895", "bot": "#0db870", "shadow": "#086b42", "text": "#ffffff", "border": "#0db870"},
        "pressed":  {"top": "#0a9460", "mid": "#087a50", "bot": "#065c3c", "shadow": "#033520", "text": "#a0ffd4", "border": "#044d30"},
        "disabled": {"top": "#3a6655", "mid": "#2e5244", "bot": "#1e3a2f", "shadow": "#111f18", "text": "#6aad8e", "border": "#1e3a2f"},
    }
    
    def __init__(self, master, text="", command=None, height=52, **kwargs):
        super().__init__(master, height=height, bd=0, highlightthickness=0,
                         cursor="hand2", bg="#1a1a2e", **kwargs)
        self._text    = text
        self._command = command
        self._state   = "normal"
        self._height  = height
        self._shadow_h = 5  # espessura da sombra inferior (efeito Z)
        
        self.bind("<Configure>",    self._redraw)
        self.bind("<Enter>",        lambda e: self._set_hover(True))
        self.bind("<Leave>",        lambda e: self._set_hover(False))
        self.bind("<ButtonPress-1>",  lambda e: self._set_pressed(True))
        self.bind("<ButtonRelease-1>",self._on_release)
    
    def _palette(self):
        return self._STATES[self._state]
    
    def _redraw(self, event=None):
        self.delete("all")
        w = self.winfo_width()
        h = self._height
        r = 10  # raio do border-radius
        sh = self._shadow_h
        p = self._palette()
        
        # --- Camada de sombra (base inferior) ---
        self._rounded_rect(0, sh, w, h, r, fill=p["shadow"], outline="")
        
        # --- Corpo principal (simulando gradiente em 3 faixas horizontais) ---
        # Faixa superior (\u00e9 o reflexo de luz)
        self._rounded_rect(0, 0, w, h - sh, r, fill=p["top"], outline="")
        # Faixa m\u00e9dia
        band_y = int((h - sh) * 0.38)
        self._rounded_rect(0, band_y, w, h - sh, r, fill=p["mid"], outline="")
        # Faixa inferior escura (cria a profundidade)
        self._rounded_rect(0, int((h - sh) * 0.68), w, h - sh, r, fill=p["bot"], outline="")
        
        # --- Borda interna (realce 1px no topo) ---
        self._rounded_rect(1, 1, w - 1, h - sh - 1, r - 1, fill="",
                           outline="#3dffc0" if self._state not in ("disabled", "pressed") else p["border"],
                           width=1)
        
        # --- Linha de borda externa ---
        self._rounded_rect(0, 0, w, h - sh, r, fill="", outline=p["border"], width=1)
        
        # --- Texto met\u00e1lico com sombra ---
        cx, cy = w // 2, (h - sh) // 2
        # Sombra do texto
        self.create_text(cx + 1, cy + 2, text=self._text,
                         font=("Segoe UI", 13, "bold"),
                         fill="#003322", anchor="center")
        # Texto principal (cor prateada/metálica)
        self.create_text(cx, cy, text=self._text,
                         font=("Segoe UI", 13, "bold"),
                         fill=p["text"], anchor="center")
    
    def _rounded_rect(self, x1, y1, x2, y2, r, **kwargs):
        """Desenha um retângulo com cantos arredondados no Canvas."""
        pts = [
            x1+r, y1,   x2-r, y1,
            x2,   y1,   x2,   y1+r,
            x2,   y2-r, x2,   y2,
            x2-r, y2,   x1+r, y2,
            x1,   y2,   x1,   y2-r,
            x1,   y1+r, x1,   y1,
        ]
        return self.create_polygon(pts, smooth=True, **kwargs)
    
    def _set_hover(self, active):
        if self._state == "disabled": return
        self._state = "hover" if active else "normal"
        self._redraw()
    
    def _set_pressed(self, active):
        if self._state == "disabled": return
        self._state = "pressed" if active else "normal"
        self._redraw()
    
    def _on_release(self, event):
        if self._state == "disabled": return
        self._state = "hover"
        self._redraw()
        if self._command:
            self._command()
    
    def configure(self, state=None, text=None, **kwargs):
        """Compatível com .configure(state='disabled', text='...')"""
        if state == "disabled":
            self._state = "disabled"
            self["cursor"] = ""
        elif state == "normal":
            self._state = "normal"
            self["cursor"] = "hand2"
        if text is not None:
            self._text = text
        self._redraw()
    
    def cget(self, key):
        if key == "state": return self._state
        return super().cget(key)


# ==========================================
# INTERFACE GRÁFICA (GUI CustomTkinter)
# ==========================================

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class AppExtratorPDF(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Apex Extractor Pro - Inteligência de Extração em Massa")
        self.geometry("650x550")
        self.resizable(False, False)
        
        # === Carga da Logo Personalizada (Titlebar + Barra de Tarefas) ===
        try:
            bundle_dir = getattr(sys, '_MEIPASS', os.path.abspath(os.path.dirname(__file__)))
            icon_path = os.path.join(bundle_dir, "logo_extrator.ico")
            self.iconbitmap(icon_path)
            
            # Força o Windows a entender que este App tem uma identidade única na Barra de Tarefas
            myappid = 'antigravity.apexextractor.pro.1.0'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            
        except Exception as e:
            pass # Se não achar o arquivo de ícone no ambiente local/empacotado, silencia
            
        self.config_data = load_config()
        self.is_running = False
        self.todos_projetos = []
        self._lock = threading.Lock()  # Lock para acesso thread-safe aos resultados
        self._rate_limit_event = threading.Event()  # Semáforo global para rate-limit
        self._rate_limit_event.set()  # Começa "liberado"
        
        self.mostrar_tela_login()

    # --- TELA DE LICENÇA (AUTENTICAÇÃO) ---
    def mostrar_tela_login(self):
        self.login_frame = ctk.CTkFrame(self, corner_radius=15)
        self.login_frame.pack(pady=80, padx=60, fill="both", expand=True)
        
        title_label = ctk.CTkLabel(self.login_frame, text="�️ Apex Extractor Pro", font=ctk.CTkFont(size=24, weight="bold"))
        title_label.pack(pady=(40, 20))
        
        subtitle = ctk.CTkLabel(self.login_frame, text="Para prosseguir, informe sua Licença Comercial.", font=ctk.CTkFont(size=12), text_color="gray")
        subtitle.pack(pady=(0, 30))
        
        self.lic_entry = ctk.CTkEntry(self.login_frame, placeholder_text="XXXXXXXXXXXXXXXX...", width=300, show="*")
        self.lic_entry.pack(pady=10)
        
        # Carrega licença antiga caso exista
        if self.config_data.get("license_key"):
            self.lic_entry.insert(0, self.config_data["license_key"])

        self.login_btn = ctk.CTkButton(self.login_frame, text="Autenticar", command=self.fazer_login, width=300, height=40)
        self.login_btn.pack(pady=20)
        
        self.login_status = ctk.CTkLabel(self.login_frame, text="", text_color="red")
        self.login_status.pack()

    def fazer_login(self):
        chave = self.lic_entry.get().strip()
        if not chave:
            self.login_status.configure(text="Por favor, digite a Chave de Licença.", text_color="red")
            return
            
        self.login_btn.configure(state="disabled", text="Validando...")
        self.update()
        
        sucesso, mensagem = validate_license(chave)
        
        self.login_btn.configure(state="normal", text="Autenticar")
        
        if sucesso:
            # Salva pra sempre na config e vai pra próxima tela
            self.config_data["license_key"] = chave
            save_config(self.config_data)
            
            messagebox.showinfo("Sucesso", mensagem)
            self.login_frame.destroy()
            self.mostrar_tela_principal()
        else:
            self.login_status.configure(text=mensagem, text_color="red")


    # --- TELA PRINCIPAL DO EXTRATOR ---
    def mostrar_tela_principal(self):
        # Frame de Configuração da API
        api_frame = ctk.CTkFrame(self, fg_color="transparent")
        api_frame.pack(fill="x", padx=20, pady=(20, 10))
        
        provider_frame = ctk.CTkFrame(api_frame, fg_color="transparent")
        provider_frame.pack(fill="x", pady=(0, 5))
        ctk.CTkLabel(provider_frame, text="🤖 Provedor de IA:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 10))
        
        self.provider_var = ctk.StringVar(value=self.config_data.get("ai_provider", "Gemini"))
        self.provider_menu = ctk.CTkOptionMenu(provider_frame, values=["Gemini", "OpenAI"], variable=self.provider_var, command=self.on_provider_change)
        self.provider_menu.pack(side="left")
        
        self.lbl_api = ctk.CTkLabel(api_frame, text="🔑 Chave de API:", font=ctk.CTkFont(weight="bold"))
        self.lbl_api.pack(anchor="w")
        
        key_container = ctk.CTkFrame(api_frame, fg_color="transparent")
        key_container.pack(fill="x", pady=(5, 0))
        
        self.api_entry = ctk.CTkEntry(key_container, show="*", width=480)
        self.api_entry.pack(side="left")
        
        self.btn_alterar_chave = ctk.CTkButton(key_container, text="Salvar Ativa", command=self.salvar_chave_api, width=100)
        self.btn_alterar_chave.pack(side="right")
        
        # Chamada inicial para preencher a chave correta
        self.on_provider_change(self.provider_var.get())

        # Frame PDF
        pdf_frame = ctk.CTkFrame(self, fg_color="transparent")
        pdf_frame.pack(fill="x", padx=20, pady=(10, 10))
        
        ctk.CTkLabel(pdf_frame, text="📄 PDF para Extração:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        
        pdf_container = ctk.CTkFrame(pdf_frame, fg_color="transparent")
        pdf_container.pack(fill="x", pady=(5, 0))
        
        self.pdf_path_var = ctk.StringVar()
        self.pdf_entry = ctk.CTkEntry(pdf_container, textvariable=self.pdf_path_var, width=480, state="disabled")
        self.pdf_entry.pack(side="left")
        
        ctk.CTkButton(pdf_container, text="Procurar...", command=self.escolher_pdf, width=100).pack(side="right")

        # Frame de Logs
        log_frame = ctk.CTkFrame(self)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(10, 20))
        
        self.progress_bar = ctk.CTkProgressBar(log_frame, mode="determinate")
        self.progress_bar.pack(fill="x", padx=10, pady=(10, 5))
        self.progress_bar.set(0)
        
        self.log_text = ctk.CTkTextbox(log_frame, state="disabled", fg_color="transparent")
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # Botão 3D Metálico
        self.start_btn = MetalButton3D(self, text="▶  INICIAR EXTRAÇÃO AUTOMÁTICA",
                                       command=self.iniciar_extracao_thread, height=54)
        self.start_btn.pack(fill="x", padx=20, pady=(0, 20))

    def on_provider_change(self, choice):
        self.config_data["ai_provider"] = choice
        save_config(self.config_data)
        
        self.lbl_api.configure(text=f"🔑 {choice} API Key:")
        
        self.api_entry.configure(state="normal")
        self.api_entry.delete(0, "end")
        
        key_name = "gemini_api_key" if choice == "Gemini" else "openai_api_key"
        saved_key = self.config_data.get(key_name, "")
        
        if saved_key:
            self.api_entry.insert(0, saved_key)
            self.api_entry.configure(state="disabled")
            self.btn_alterar_chave.configure(text="Alterar", fg_color="gray", hover_color="darkgray")
        else:
            self.btn_alterar_chave.configure(text="Salvar Ativa", fg_color=["#3a7ebf", "#1f538d"], hover_color=["#325882", "#14375e"])

    def salvar_chave_api(self):
        estado_atual = self.api_entry.cget("state")
        if estado_atual == "disabled":
            self.api_entry.configure(state="normal")
            self.btn_alterar_chave.configure(text="Salvar", fg_color="#3b82f6", hover_color="#2563eb")
        else:
            nova_chave = self.api_entry.get().strip()
            if nova_chave:
                provider = self.provider_var.get()
                key_name = "gemini_api_key" if provider == "Gemini" else "openai_api_key"
                self.config_data[key_name] = nova_chave
                save_config(self.config_data)
                self.api_entry.configure(state="disabled")
                self.btn_alterar_chave.configure(text="Alterar", fg_color="gray", hover_color="darkgray")
                messagebox.showinfo("Salvo", f"Chave da {provider} salva com sucesso!")
            else:
                messagebox.showerror("Erro", "A chave não pode estar vazia.")

    def log(self, message):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        self.update_idletasks()
        
    def escolher_pdf(self):
        filepath = filedialog.askopenfilename(
            title="Selecione um PDF",
            filetypes=[("PDF Files", "*.pdf")]
        )
        if filepath:
            self.pdf_path_var.set(filepath)

    def iniciar_extracao_thread(self):
        if self.api_entry.cget("state") == "normal":
             messagebox.showwarning("Aviso", "Por favor, Salve sua Chave de API clicando no botão ao lado antes de continuar.")
             return
             
        provider = self.provider_var.get()
        key_name = "gemini_api_key" if provider == "Gemini" else "openai_api_key"
        api_key_salva = self.config_data.get(key_name, "").strip()
        
        if not api_key_salva:
            messagebox.showwarning("Aviso", f"Por favor, insira a Chave de API da {provider}.")
            return
            
        if not self.pdf_path_var.get().strip():
            messagebox.showwarning("Aviso", "Por favor, selecione um arquivo PDF.")
            return

        # === Trava Militar Anti-Malandragem ===
        # Revalida silenciosamente a licença antes de cada extração pro caso do admin ter cancelado
        self.start_btn.configure(state="disabled", text="🛡️ Verificando Licença Criptografada...")
        self.update()
        
        chave_licenca = self.config_data.get("license_key", "")
        sucesso, msg_licenca = validate_license(chave_licenca)
        if not sucesso:
            messagebox.showerror("Acesso Revogado", f"Acesso Negado: Sua licença foi cancelada, suspensa ou não existe mais no servidor.\nO aplicativo será encerrado de forma forçada imediatamente.\n\nMotivo do Banco de Dados: {msg_licenca}")
            sys.exit(0)  # Mata a aplicação instantaneamente
            
        self.start_btn.configure(state="disabled", text="⏳ EXTRAINDO DADOS...")
        self.is_running = True
        
        self.log_text.configure(state="normal")
        self.log_text.delete("0.0", "end")
        self.log_text.configure(state="disabled")
        
        self.progress_bar.set(0)
        self.todos_projetos = []
        
        # Thread para IA
        t = threading.Thread(target=self.processar_pdf, args=(api_key_salva, provider))
        t.daemon = True
        t.start()

    def _worker_fatia(self, fatia_idx, total_fatias, start_com_overlap, end_page, pdf_path, api_key, provider):
        """Worker thread: extrai dados de uma fatia do PDF com retry e backoff.
        Cada thread abre seu próprio handle do PDF (segurança PyMuPDF).
        Respeita semáforo global de rate-limit."""
        try:
            doc = fitz.open(pdf_path)
            texto_fatia = ""
            for page_num in range(start_com_overlap, end_page + 1):
                page = doc.load_page(page_num)
                texto_fatia += page.get_text("text") + "\n\n"
            doc.close()
            
            if not texto_fatia.strip():
                self.log(f"  [Bloco {fatia_idx}/{total_fatias}] Págs {start_com_overlap+1}-{end_page+1}: vazio, pulando.")
                return (fatia_idx, [])
            
            max_retries = 5
            for tentativa in range(max_retries):
                if not self.is_running:
                    return (fatia_idx, [])
                
                # Aguarda semáforo global de rate-limit (se outro worker detectou 429, todos pausam)
                self._rate_limit_event.wait()
                
                try:
                    self.log(f"  [Bloco {fatia_idx}/{total_fatias}] Págs {start_com_overlap+1}-{end_page+1} → {provider} (tentativa {tentativa+1}/{max_retries})...")
                    if provider == "Gemini":
                        tabela_markdown = extract_from_gemini(texto_fatia, api_key)
                    else:
                        tabela_markdown = extract_from_openai(texto_fatia, api_key)
                    
                    novos_projetos = parse_markdown_table_to_dicts(tabela_markdown)
                    if novos_projetos:
                        expandidos = expandir_por_autor(novos_projetos)
                        self.log(f"  [Bloco {fatia_idx}/{total_fatias}] ✅ {len(novos_projetos)} trabalhos → {len(expandidos)} linhas")
                        return (fatia_idx, expandidos)
                    else:
                        self.log(f"  [Bloco {fatia_idx}/{total_fatias}] Sem resultados neste trecho.")
                        return (fatia_idx, [])
                    
                except Exception as e:
                    erro_msg = str(e)
                    if tentativa < max_retries - 1:
                        is_rate_limit = ("429" in erro_msg or "quota" in erro_msg.lower() or 
                                        "too many requests" in erro_msg.lower() or 
                                        "rate_limit_exceeded" in erro_msg.lower() or
                                        "insufficient_quota" in erro_msg.lower())
                        if is_rate_limit:
                            wait_time = 60
                            import re
                            match = re.search(r"retry in ([\d\.]+)s", erro_msg)
                            if match:
                                wait_time = int(float(match.group(1))) + 5
                            else:
                                match_json = re.search(r'"retryDelay":\s*"(\d+)s"', erro_msg)
                                if match_json:
                                    wait_time = int(match_json.group(1)) + 5
                                else:
                                    match_openai = re.search(r"Please try again in (\d+(\.\d+)?)s", erro_msg)
                                    if match_openai:
                                        wait_time = int(float(match_openai.group(1))) + 5
                            
                            # TRAVA GLOBAL: pausa TODOS os workers para não saturar a API
                            self.log(f"  [Bloco {fatia_idx}] ⚠️ Rate-limit 429! Travando TODOS os workers por {wait_time}s...")
                            self._rate_limit_event.clear()  # Bloqueia todos
                            time.sleep(wait_time)
                            self._rate_limit_event.set()  # Libera todos
                        else:
                            self.log(f"  [Bloco {fatia_idx}] Erro API (tentativa {tentativa+1}): {erro_msg[:120]}")
                            time.sleep(5)
                    else:
                        self.log(f"  [Bloco {fatia_idx}/{total_fatias}] ❌ FALHA APÓS {max_retries} TENTATIVAS: {erro_msg[:120]}")
            
            return (fatia_idx, None)  # None = falha definitiva (diferente de [] = sem dados)
        except Exception as e:
            self.log(f"  [Bloco {fatia_idx}] ERRO WORKER: {str(e)[:120]}")
            return (fatia_idx, None)

    def processar_pdf(self, api_key, provider):
        try:
            pdf_path = self.pdf_path_var.get()
            chunk_size  = 30  # Janela expandida para menos cortes de artigo
            overlap     = 5   # Sobreposição: evita cortar rodapé de e-mails
            
            self.log(f"Abrindo arquivo PDF...")
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            doc.close()  # Fecha o handle principal; cada worker abrirá o seu
            
            # Calcula todas as fatias antecipadamente
            fatias = []
            for start_page in range(0, total_pages, chunk_size):
                start_com_overlap = max(0, start_page - overlap)
                end_page = min(start_page + chunk_size, total_pages) - 1
                fatias.append((start_com_overlap, end_page))
            
            total_fatias = len(fatias)
            
            self.log(f"⚡ MODO TURBO PARALELO ATIVADO")
            self.log(f"Total de Páginas: {total_pages} | {total_fatias} blocos | 3 workers simultâneos | Motor: {provider}")
            
            base_name = os.path.splitext(os.path.basename(pdf_path))[0]
            base_dir = os.path.dirname(pdf_path)
            excel_filename = os.path.join(base_dir, f"{base_name}_Extraido.xlsx")
            
            # ========== FASE 1: Disparo paralelo ==========
            concluidas = 0
            fatias_falhadas = []  # Re-queue das que falharam
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                futures = {}
                for i, (s, e) in enumerate(fatias):
                    f = executor.submit(self._worker_fatia, i+1, total_fatias, s, e, pdf_path, api_key, provider)
                    futures[f] = (i + 1, s, e)
                
                for future in concurrent.futures.as_completed(futures):
                    if not self.is_running:
                        self.log("Processo cancelado!")
                        break
                    
                    fatia_num, s, e = futures[future]
                    fatia_idx, resultados_fatia = future.result()
                    concluidas += 1
                    
                    if resultados_fatia is None:
                        # Falha definitiva → salva para segunda passada
                        fatias_falhadas.append((fatia_idx, s, e))
                    elif resultados_fatia:
                        with self._lock:
                            self.todos_projetos.extend(resultados_fatia)
                            self.todos_projetos = consolidar_projetos(self.todos_projetos)
                            
                            try:
                                salvar_excel_formatado(self.todos_projetos, excel_filename)
                            except PermissionError as pe:
                                self.log(f"  -> AVISO: {str(pe)}")
                            except Exception as ee:
                                self.log(f"  -> ERRO ao salvar Excel: {str(ee)}")
                    
                    self.progress_bar.set(concluidas / float(total_fatias))
            
            # ========== FASE 2: Retentativa sequencial das fatias que falharam ==========
            if fatias_falhadas and self.is_running:
                self.log(f"\n🔄 FASE 2: Retentando {len(fatias_falhadas)} blocos que falharam (modo sequencial)...")
                for fatia_idx, s, e in fatias_falhadas:
                    if not self.is_running:
                        break
                    self.log(f"  Re-processando bloco {fatia_idx} (págs {s+1}-{e+1})...")
                    _, resultados = self._worker_fatia(fatia_idx, total_fatias, s, e, pdf_path, api_key, provider)
                    if resultados:
                        with self._lock:
                            self.todos_projetos.extend(resultados)
                            self.todos_projetos = consolidar_projetos(self.todos_projetos)
                            self.log(f"  [Bloco {fatia_idx}] 🔁 Recuperado! +{len(resultados)} linhas. Total: {len(self.todos_projetos)}")
                            try:
                                salvar_excel_formatado(self.todos_projetos, excel_filename)
                            except Exception:
                                pass
                    elif resultados is None:
                        self.log(f"  [Bloco {fatia_idx}] ❌ Falha definitiva mesmo na retentativa.")
            
            # ========== Salvamento final e relatório ==========
            if self.is_running:
                # Relatório de cobertura
                emails_extraidos = sum(1 for p in self.todos_projetos if p.get('E-mails dos Autores', '').strip())
                self.log(f"\n🎉 PROCESSO CONCLUÍDO 100%!")
                self.log(f"📊 Relatório: {len(self.todos_projetos)} linhas totais | {emails_extraidos} com e-mail")
                if fatias_falhadas:
                    self.log(f"⚠️ {len(fatias_falhadas)} blocos tiveram problemas (retentados na Fase 2).")
                self.log(f"Planilha finalizada salva em:\n{excel_filename}")
                messagebox.showinfo("Sucesso", f"Extração concluída!\n\nForam encontrados {len(self.todos_projetos)} itens no total.\n{emails_extraidos} com e-mail associado.\nO arquivo Excel foi criado/atualizado com sucesso.")
            
        except Exception as e:
            self.log(f"\nERRO FATAL: {str(e)}")
            messagebox.showerror("Erro Crítico", f"Ocorreu um erro extremo:\n\n{str(e)}")
        finally:
            self.start_btn.configure(state="normal", text="▶ INICIAR EXTRAÇÃO AUTOMÁTICA")
            self.is_running = False

# Inicialização
if __name__ == "__main__":
    app = AppExtratorPDF()
    app.mainloop()
