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
Você é um robô especialista em extração de dados de anais de congressos e periódicos acadêmicos em PDF.
Sua missão: extrair TÍTULO, NOME DO AUTOR e E-MAIL de cada trabalho acadêmico e retornar EXCLUSIVAMENTE uma tabela Markdown.

=== PADRÃO DO DOCUMENTO (MUITO IMPORTANTE) ===
Os documentos seguem este layout típico:
  1. TÍTULO DO TRABALHO: em MAIÚSCULAS e/ou negrito, centralizado no topo da 1ª página do artigo.
  2. AUTORES: logo abaixo do título, com números sobrescritos (ex: "Maria Silva¹, João Santos²").
  3. E-MAILS: no RODAPÉ da mesma página (ou rodapé de página posterior do mesmo artigo).
     O rodapé começa com o número sobrescrito seguido da afiliação e termina com o e-mail:
     Exemplo de rodapé: "¹ Mestranda em Educação, UEFS. maria.silva@uefs.br"
     Exemplo de rodapé: "2. Doutorando em Economia, UFBA. joao@ufba.br"

=== REGRA DE OURO — UMA LINHA POR AUTOR ===
Se um trabalho tiver 4 autores, você DEVE gerar 4 linhas na tabela — uma para cada autor.
O título do trabalho deve ser REPETIDO em cada linha. NUNCA agrupe autores na mesma célula.

=== REGRAS OBRIGATÓRIAS DE FORMATAÇÃO ===
1. Cabeçalho EXATO: `| Títulos dos Trabalhos | Nomes dos Autores | E-mails dos Autores |`
2. Linha separadora EXATA: `|---|---|---|`
3. REMOVA quebras de linha (Enter) de dentro do TÍTULO. O título deve ser uma linha contínua.
4. Associe e-mails aos autores pelo índice numérico sobrescrito (¹²³⁴ ou 1.2.3.4 ou (1)(2)).
5. Se o e-mail NÃO aparece neste trecho, deixe a célula vazia (não invente).
6. Ignore sumários, capas, referências bibliográficas e agradecimentos.
7. Sua resposta deve conter SOMENTE a tabela Markdown — sem texto antes ou depois.
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
        
        # Botão Ação Inicial
        self.start_btn = ctk.CTkButton(self, text="▶ INICIAR EXTRAÇÃO AUTOMÁTICA", command=self.iniciar_extracao_thread, height=50, font=ctk.CTkFont(size=14, weight="bold"), fg_color="#10b981", hover_color="#059669")
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

    def processar_pdf(self, api_key, provider):
        try:
            pdf_path = self.pdf_path_var.get()
            chunk_size  = 30  # Reduzido de 40 → mais preciso por artigo
            overlap     = 5   # Sobreposição: evita cortar rodapé de e-mails
            
            self.log(f"Abrindo arquivo PDF...")
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            
            total_fatias = (total_pages + chunk_size - 1) // chunk_size
            
            self.log(f"Total de Páginas: {total_pages} | Serão enviadas {total_fatias} fatias para {provider}.")
            
            base_name = os.path.splitext(os.path.basename(pdf_path))[0]
            base_dir = os.path.dirname(pdf_path)
            excel_filename = os.path.join(base_dir, f"{base_name}_Extraido.xlsx")
            
            fatia_atual = 0
            
            for start_page in range(0, total_pages, chunk_size):
                if not self.is_running:
                    self.log("Processo cancelado!")
                    break
                
                # Início com overlap: volta 'overlap' páginas para pegar rodapés do chunk anterior
                start_com_overlap = max(0, start_page - overlap)
                end_page = min(start_page + chunk_size, total_pages) - 1
                fatia_atual += 1
                self.log(f"\n[{fatia_atual}/{total_fatias}] Lendo páginas {start_com_overlap+1} até {end_page+1}...")
                
                texto_fatia = ""
                for page_num in range(start_com_overlap, end_page + 1):
                    page = doc.load_page(page_num)
                    texto_fatia += page.get_text("text") + "\n\n"
                    
                if not texto_fatia.strip():
                    self.log(f"  -> Nenhuma palavra encontrada nestas páginas. Pulando...")
                    # Update progress UI
                    progresso = fatia_atual / float(total_fatias)
                    self.progress_bar.set(progresso)
                    continue
                
                max_retries = 5 # Escalado de 3 para 5 retentativas para dar fôlego em documentos colossais (ex: 5000 págs)
                sucesso_fatia = False
                
                for tentativa in range(max_retries):
                    try:
                        self.log(f"  -> Chamando a inteligência {provider} (tentativa {tentativa+1}/{max_retries})...")
                        if provider == "Gemini":
                            tabela_markdown = extract_from_gemini(texto_fatia, api_key)
                        else:
                            tabela_markdown = extract_from_openai(texto_fatia, api_key)
                        
                        novos_projetos = parse_markdown_table_to_dicts(tabela_markdown)
                        
                        if novos_projetos:
                            # Etapa 1: expande células com múltiplos autores em linhas individuais
                            novos_expandidos = expandir_por_autor(novos_projetos)
                            self.todos_projetos.extend(novos_expandidos)
                            # Etapa 2: consolida duplicados (mesmo autor em chunks diferentes)
                            self.todos_projetos = consolidar_projetos(self.todos_projetos)
                            self.log(f"  -> SUCESSO! {len(novos_projetos)} trabalhos → {len(novos_expandidos)} linhas. Total: {len(self.todos_projetos)} (após deduplicação)")
                            
                            try:
                                salvar_excel_formatado(self.todos_projetos, excel_filename)
                            except PermissionError as pe:
                                self.log(f"  -> AVISO: {str(pe)}")
                            except Exception as ee:
                                self.log(f"  -> ERRO ao salvar Excel: {str(ee)}")
                                
                        else:
                            self.log(f"  -> A IA analisou e não encontrou resultados com esse formato aqui.")
                            
                        sucesso_fatia = True
                        break
                        
                    except Exception as e:
                        erro_msg = str(e)
                        self.log(f"  -> ERRO API: {erro_msg}")
                        if tentativa < max_retries - 1:
                            # Tática de recuo dinâmico: se a API bloqueou por excesso de velocidade (Rate Limiting), extrai o tempo exato de espera retornado pela API.
                            if "429" in erro_msg or "quota" in erro_msg.lower() or "too many requests" in erro_msg.lower() or "rate_limit_exceeded" in erro_msg.lower() or "insufficient_quota" in erro_msg.lower():
                                wait_time = 60 # Tempo padrão de recuo (1 minuto) se não conseguir ler do erro
                                import re
                                match = re.search(r"retry in ([\d\.]+)s", erro_msg)
                                if match:
                                    wait_time = int(float(match.group(1))) + 2 # Pega o tempo do log e adiciona 2s de segurança
                                else:
                                    # Fallback para o campo JSON
                                    match_json = re.search(r'"retryDelay":\s*"(\d+)s"', erro_msg)
                                    if match_json:
                                        wait_time = int(match_json.group(1)) + 2
                                    else:
                                        # Fallback para OpenAI Limit Try again em xs
                                        match_openai = re.search(r"Please try again in (\d+(\.\d+)?)s", erro_msg)
                                        if match_openai:
                                            wait_time = int(float(match_openai.group(1))) + 2

                                self.log(f"  -> Limite de Frequência da API (429) detectado! Pausando por {wait_time} segundos conforme exigido...")
                                time.sleep(wait_time)
                            else:
                                self.log("  -> Aguardando 5 segundos para tentar novamente...")
                                time.sleep(5)
                
                if not sucesso_fatia:
                    self.log(f"  -> ATENÇÃO: Falha persistente na fatia {fatia_atual}.")
                    
                self.progress_bar.set(fatia_atual / float(total_fatias))
                
            doc.close()
            
            if self.is_running:
                self.log(f"\n🎉 PROCESSO CONCLUÍDO 100%!")
                self.log(f"Planilha finalizada salva em:\n{excel_filename}")
                messagebox.showinfo("Sucesso", f"Extração concluída!\n\nForam encontrados {len(self.todos_projetos)} itens no total.\nO arquivo Excel foi criado/atualizado com sucesso.")
            
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
