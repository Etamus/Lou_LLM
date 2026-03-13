# Lou LLM

Inteligência artificial com personalidade customizável, executando localmente com LLM (Large Language Model), projetada para diálogos naturais, interações contextuais profundas e memória a longo prazo.

---

## Funcionalidades Principais

### Frontend Web Neve
- **Interface Moderna:** Chat web responsivo com design limpo, timestamps, separadores de data e balões de conversa ajustáveis.
- **Gerenciamento de Servidores e Canais:** Crie, renomeie e personalize servidores (grupos) e canais de chat com ícones customizáveis.
- **Personalização de Perfil:** Altere nome de usuário e foto de perfil (PNG/JPG/GIF/WebP até 2MB), com upload direto via navegador.
- **Suporte a GIFs:** A IA pode enviar GIFs animados armazenados localmente em `assets/gifs` para expressar emoções.
- **Layout Inteligente:** Balões de chat se ajustam para otimizar leitura, com tratamento especial para mensagens com GIFs.

### Chat Contextual e Inteligente
- **Respostas em Tempo Real:** Diálogos naturais com o LLM local, processados via backend HTTP.
- **Sistema de Resposta:** Responda a mensagens específicas com indicadores visuais.
- **Debouncing de Mensagens:** Aguarda múltiplas mensagens em sequência para responder como um pensamento único.
- **Fala Proativa:** Reengaja conversas inativas de forma contextual, com limites para evitar spam.

---

## Comportamento da Lou

### Personalidade Profunda e Customizável
- **Ficha de Personagem Externa:** Toda a personalidade (identidade, traços, psicologia, medos, hobbies, etc.) é carregada de `data/personality_prompt.json`, permitindo customização total sem alterar código.
- **Noção de Tempo e Espaço:** Sabe data/hora atuais para interações contextuais sobre períodos do dia, datas especiais e feriados.
- **Raciocínio Transparente:** Logs no terminal mostram traços de personalidade usados para formular respostas.

### Memória e Aprendizado Contínuo
- **Memória Unificada:** Após cada interação, extrai fatos importantes (`data/memory_bank.json`) para consistência a longo prazo.
- **Interação Natural:** Respostas gramaticalmente corretas, com pontuação adequada e adaptação ao estilo do usuário.

---

## Estrutura Técnica

### Arquitetura Modular em Python
- **Backend HTTP:** Servidor puro Python (stdlib) em `neve-frontend/backend/server.py`, rodando na porta 8765.
- **LLM Local:** Integração com llama-cpp-python para execução local de modelos GGUF, com suporte a CUDA/GPU.
- **Serviço de IA:** Módulo `lou_service/ai.py` constrói prompts e gerencia respostas do LLM.
- **Formatação de Texto:** `LouFormatter.py` pós-processa outputs do LLM para correção gramatical e splitting em balões de chat.
- **Configuração:** `lou_service/config.py` gerencia caminhos de arquivos de dados.
- **Frontend Web:** HTML/CSS/JS em `neve-frontend/`, com auto-ajuste do campo de digitação e cache-busting.

### Robustez e Tratamento de Erros
- **Parser Inteligente:** Resiliente a variações no output do LLM, extraindo mensagens corretamente.
- **Gerenciamento de Recursos:** GIFs otimizados, threads seguras para evitar race conditions.
- **Validação Automática:** Após mudanças, roda testes básicos e linters automaticamente.

---

## Como Executar

### Pré-requisitos
- Python 3.11+
- GPU NVIDIA com CUDA 12.4+ (recomendado para performance)
- Modelo GGUF compatível (ex.: Llama 3.1 8B Instruct)

### Instalação
1. **Clone/baixe o projeto** e navegue para a pasta raiz.

2. **Crie ambiente virtual:**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   ```

3. **Instale dependências:**
   ```bash
   pip install llama-cpp-python[server]==0.3.4
   ```

4. **Baixe um modelo GGUF:**
   - Recomendado: [Llama 3.1 8B Instruct Q4_K_M](https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF)
   - Salve em `models/` (crie a pasta) como `llama-3.1-8b-instruct-q5_k_m.gguf`

### Configuração
- **Personalidade:** Edite `data/personality_prompt.json` com a ficha da Lou.
- **Modelo:** Em `lou_service/config.py`, ajuste `model_path` para o caminho do seu modelo GGUF.
- **Parâmetros LLM:** Em `lou_service/ai.py`, configure temperatura, top_p, etc. (padrão: temp=0.9, top_p=0.92, n_ctx=8192, max_tokens=512).
- **Assets:** Adicione avatares em `assets/avatars/` e GIFs em `assets/gifs/`.

### Execução
1. **Ative o ambiente virtual:**
   ```bash
   .venv\Scripts\activate
   ```

2. **Execute o frontend Neve:**
   ```bash
   python run_neve_frontend.py
   ```
   - Sobe o backend em `http://127.0.0.1:8765` e abre janela Qt com o frontend.
   - Para rodar apenas o servidor: `python neve-frontend/backend/server.py`

3. **Teste:**
   - Abra o chat no navegador.
   - Envie mensagens; a Lou responderá via LLM local.

### Dependências Extras (Opcional)
- Para janela Qt: `pip install PySide6 PySide6-QtWebEngine`
- Para desenvolvimento: `pip install pytest` (para testes)

---

## Desenvolvimento e Contribuição

- **Testes:** Rode `python -m pytest` para validar mudanças.
- **Logs:** Verifique terminal para debug de personalidade e formatação.
- **Estrutura de Arquivos:**
  - `LouFormatter.py`: Pós-processamento de texto.
  - `lou_service/`: Lógica de IA e dados.
  - `neve-frontend/`: Interface web e backend HTTP.
  - `data/`: JSONs de personalidade, memória e chat.
  - `assets/`: Avatares e GIFs.

Para dúvidas ou issues, consulte os logs ou edite os arquivos de configuração.
