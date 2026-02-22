# Como Gerar o Arquivo Executável (.exe)

O script `extrator_standalone.py` já contém toda a interface gráfica e a lógica de comunicação direta com a OpenAI para extrair os dados de PDFs, sem depender do N8N. 

Para transformar esse arquivo de código em um verdadeiro "Aplicativo de Windows" (um arquivo `.exe` que você pode mandar para o cliente e ele rodar clicando duas vezes, sem precisar instalar Python), usaremos uma biblioteca padrão do mercado chamada **PyInstaller**.

## Passo 1: Instalar o PyInstaller
No terminal do seu projeto onde está o ambiente virtual (`.venv`), execute o comando para instalar o empacotador:
```bash
pip install pyinstaller
```

## Passo 2: Gerar o Executável (.exe)
Ainda no mesmo terminal, execute a seguinte linha mágica:
```bash
pyinstaller --noconsole --onefile extrator_standalone.py
```

### O que esses comandos significam?
- `--noconsole`: Impede que aquela tela preta do prompt de comando (CMD) do Windows abra junto com a tela do aplicativo do cliente. Abre só a interface visual bonitinha.
- `--onefile`: Pega todas as dezenas de bibliotecas (Pandas, PyMuPDF, etc) e esmaga tudo dentro de um único arquivo monolítico `.exe`. Assim você não precisa mandar nenhuma pasta "lib" junto, só manda 1 arquivo pro cliente!

## Passo 3: Onde encontrar seu `.exe`
Depois que o comando rodar (ele demora uns 2 a 3 minutos compactando, é normal ler muita coisa amarela na tela), vão surgir algumas pastas geradas na raiz do seu projeto.

O seu produto final estará dentro da nova pasta chamada **`dist`** (abreviação de Distribution).

1. Abra a pasta `dist` pelo Windows Explorer.
2. Lá dentro tem o arquivo **`extrator_standalone.exe`**.
3. É só clicar duas vezes para testar. Você pode enviar *APENAS esse arquivo único* por e-mail, WhatsApp ou WeTransfer pro seu cliente.

> [!TIP]
> Se você renomear a foto `.ico` para o logo dele, você também poderia digitar `--icon=seu_logo.ico` na linha do comando para o app ficar com a cara da empresa dele!
