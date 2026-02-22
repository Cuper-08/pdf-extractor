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
        # Comando CMD que extrai o UUID (Número Único da Placa Mãe)
        output = subprocess.check_output('wmic csproduct get uuid', shell=True).decode().strip().split('\n')
        hwid = output[1].strip()
        return hwid
    except Exception:
        # Fallback de segurança se houver falha de leitura (ex: não for administrador)
        return "UNKNOWN_HWID_FALLBACK"

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
SYSTEM_PROMPT = """Você é um especialista em extração de dados acadêmicos de PDFs.
Sua única tarefa é extrair os seguintes 3 dados exatos e organizá-los OBRIGATORIAMENTE em uma única tabela Markdown:
- Título do Trabalho
- Nome do Autor (Separado, 1 por linha - verifique bem os números sobrescritos e ordens)
- E-mail do Autor (Encontre o e-mail correspondente ao autor no rodapé ou bloco de contatos, usando a proximidade ou número sobrescrito idêntico)

REGRAS ESTRITAS DE FORMATAÇÃO DA TABELA (LEIA COM ATENÇÃO):
1. A tabela DEVE obrigatoriamente ter a linha divisória com os pipes e traços exatos: `|---|---|---|`
2. O cabeçalho deve ser EXATAMENTE: `| Títulos dos Trabalhos | Nomes dos Autores | E-mails dos Autores |`
3. Se um trabalho tiver 4 autores, mas apenas 2 e-mails na página, você DEVE repetir o Título em 4 linhas, colocar os 4 nomes na segunda coluna, e deixar o campo E-mail VAZIO para os autores que não possuem e-mail listado. Nunca agrupe múltiplos autores ou e-mails.
4. ATENÇÃO AOS SOBRESCRITOS: É crucial que você vincule o e-mail correto ao autor correto! Frequentemente os autores possuem números (ex: Maria², Pedro³). Você DEVE procurar no texto os e-mails associados a esses mesmos números (ex: 2 maria@email.com, 3 pedro@email.com) e pareá-los perfeitamente na tabela, mesmo se o e-mail estiver no fim da página!
5. NUNCA invente e-mails ou nomes. Extraia apenas o que está no texto fornecido.
6. Se for apenas um sumário (índice), ou capa, ignore-o.
7. A sua resposta DEVE conter APENAS a tabela markdown, sem introduções, aspas soltas ou saudações. NUNCA quebre a estrutura da tabela.
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
            target_model = flash_models[-1]
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
        
        # === Carga da Logo Personalizada ===
        try:
            # Resolve o path para quando rodar via script OU via .exe (PyInstaller)
            bundle_dir = getattr(sys, '_MEIPASS', os.path.abspath(os.path.dirname(__file__)))
            icon_path = os.path.join(bundle_dir, "logo_extrator.ico")
            self.iconbitmap(icon_path)
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
        # Frame de Configuração da API Gemini
        api_frame = ctk.CTkFrame(self, fg_color="transparent")
        api_frame.pack(fill="x", padx=20, pady=(20, 10))
        
        ctk.CTkLabel(api_frame, text="🔑 Google Gemini API Key:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        
        key_container = ctk.CTkFrame(api_frame, fg_color="transparent")
        key_container.pack(fill="x", pady=(5, 0))
        
        self.api_entry = ctk.CTkEntry(key_container, show="*", width=480)
        self.api_entry.pack(side="left")
        
        self.btn_alterar_chave = ctk.CTkButton(key_container, text="Salvar Ativa", command=self.salvar_chave_gemini, width=100)
        self.btn_alterar_chave.pack(side="right")
        
        # Preenche com chave salva e trava para facilitar se já existir
        saved_key = self.config_data.get("gemini_api_key", "")
        if saved_key:
            self.api_entry.insert(0, saved_key)
            self.api_entry.configure(state="disabled")
            self.btn_alterar_chave.configure(text="Alterar", fg_color="gray", hover_color="darkgray")

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

    def salvar_chave_gemini(self):
        estado_atual = self.api_entry.cget("state")
        if estado_atual == "disabled":
            # Botão "Alterar" foi clicado
            self.api_entry.configure(state="normal")
            self.btn_alterar_chave.configure(text="Salvar", fg_color="#3b82f6", hover_color="#2563eb")
        else:
            # Botão "Salvar" foi clicado
            nova_chave = self.api_entry.get().strip()
            if nova_chave:
                self.config_data["gemini_api_key"] = nova_chave
                save_config(self.config_data)
                self.api_entry.configure(state="disabled")
                self.btn_alterar_chave.configure(text="Alterar", fg_color="gray", hover_color="darkgray")
                messagebox.showinfo("Salvo", "Chave do Gemini salva com sucesso!")
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
             
        api_key_salva = self.config_data.get("gemini_api_key", "").strip()
        if not api_key_salva:
            messagebox.showwarning("Aviso", "Por favor, insira a Chave de API do Gemini (Começa com AIza...).")
            return
            
        if not self.pdf_path_var.get().strip():
            messagebox.showwarning("Aviso", "Por favor, selecione um arquivo PDF.")
            return

        self.start_btn.configure(state="disabled", text="⏳ EXTUINDO DADOS...")
        self.is_running = True
        
        self.log_text.configure(state="normal")
        self.log_text.delete("0.0", "end")
        self.log_text.configure(state="disabled")
        
        self.progress_bar.set(0)
        self.todos_projetos = []
        
        # Thread para IA
        t = threading.Thread(target=self.processar_pdf, args=(api_key_salva,))
        t.daemon = True
        t.start()

    def processar_pdf(self, api_key):
        try:
            pdf_path = self.pdf_path_var.get()
            chunk_size = 40
            
            self.log(f"Abrindo arquivo PDF...")
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            
            total_fatias = (total_pages + chunk_size - 1) // chunk_size
            
            self.log(f"Total de Páginas: {total_pages} | Serão enviadas {total_fatias} fatias para o Gemini Flash.")
            
            base_name = os.path.splitext(os.path.basename(pdf_path))[0]
            base_dir = os.path.dirname(pdf_path)
            excel_filename = os.path.join(base_dir, f"{base_name}_Extraido.xlsx")
            
            fatia_atual = 0
            
            for start_page in range(0, total_pages, chunk_size):
                if not self.is_running:
                    self.log("Processo cancelado!")
                    break
                    
                end_page = min(start_page + chunk_size, total_pages) - 1
                fatia_atual += 1
                self.log(f"\n[{fatia_atual}/{total_fatias}] Lendo páginas {start_page+1} até {end_page+1}...")
                
                texto_fatia = ""
                for page_num in range(start_page, end_page + 1):
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
                        self.log(f"  -> Chamando a inteligência Gemini Flash (tentativa {tentativa+1}/{max_retries})...")
                        tabela_markdown = extract_from_gemini(texto_fatia, api_key)
                        
                        novos_projetos = parse_markdown_table_to_dicts(tabela_markdown)
                        
                        if novos_projetos:
                            self.todos_projetos.extend(novos_projetos)
                            self.log(f"  -> SUCESSO! {len(novos_projetos)} trabalhos identificados.")
                            
                            df = pd.DataFrame(self.todos_projetos)
                            try:
                                df.to_excel(excel_filename, index=False)
                            except PermissionError:
                                self.log(f"  -> AVISO: Excel aberto. Salvando num arquivo alternativo...")
                                temp_filename = excel_filename.replace('.xlsx', '_copia_seguranca.xlsx')
                                df.to_excel(temp_filename, index=False)
                                
                        else:
                            self.log(f"  -> A IA analisou e não encontrou resultados com esse formato aqui.")
                            
                        sucesso_fatia = True
                        break
                        
                    except Exception as e:
                        erro_msg = str(e)
                        self.log(f"  -> ERRO API: {erro_msg}")
                        if tentativa < max_retries - 1:
                            # Tática industrial de recuo: se a API bloqueou por excesso de velocidade (Rate Limiting), paramos por vitais 15-20 segundos.
                            if "429" in erro_msg or "quota" in erro_msg.lower() or "too many requests" in erro_msg.lower():
                                self.log("  -> Limite de Frequência do Google (429) detectado. Pausa de resfriamento de 15s...")
                                time.sleep(15)
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
