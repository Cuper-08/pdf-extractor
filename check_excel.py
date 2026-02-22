import pandas as pd
import glob

# Encontrar a planilha gerada
xlsx_files = glob.glob('*.xlsx')
xlsx_files = [f for f in xlsx_files if 'copia_temporaria' not in f]

if not xlsx_files:
    print("Nenhuma planilha encontrada.")
    exit(1)

planilha = xlsx_files[0]
print(f"Lendo: {planilha}")

df = pd.read_excel(planilha)

total_rows = len(df)
print(f"Total de linhas extraidas: {total_rows}")

# Cleanup the email column
df['E-mails dos Autores'] = df['E-mails dos Autores'].astype(str).str.strip().str.lower()
df['E-mails dos Autores'] = df['E-mails dos Autores'].replace('nan', '')

linhas_ativas = df[df['E-mails dos Autores'] != '']
print(f"Linhas com algum texto na coluna de email: {len(linhas_ativas)}")

com_arroba = df[df['E-mails dos Autores'].str.contains('@')]
print(f"Ocorrencias de '@' na coluna de e-mail: {len(com_arroba)}")

# Check duplicates of @
emails_unicos = com_arroba['E-mails dos Autores'].nunique()
print(f"E-mails UNICOS com '@': {emails_unicos}")
print(f"E-mails REPETIDOS: {len(com_arroba) - emails_unicos}")

# Linhas totalmente sem e-mail
linhas_sem_email = total_rows - len(linhas_ativas)
print(f"Linhas totalmente sem email repassado: {linhas_sem_email}")
