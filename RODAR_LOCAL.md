# Razync no computador

Execute `INICIAR_RAZYNC.bat` e use http://127.0.0.1:8000/. O mesmo backend e a mesma interface do site são executados. O Railway e o Streamlit permanecem ativos e não são alterados.

Neste computador já existe um ambiente Python 3.12 compatível, reutilizado pelo atalho. Em outro computador instale Python 3.12 e execute `INSTALAR_RAZYNC.bat`. Para OCR Tesseract instale Tesseract com o idioma português. RapidOCR também permanece disponível.

O servidor escuta apenas no próprio computador. Feche com Ctrl+C. Celulares e outros computadores não acessam esse endereço.

Dados locais ficam em `.local/razync.db`. São separados dos dados do Railway. Bases aprendidas, empresas personalizadas, tarefas e certificados do servidor não são copiados automaticamente. Use as exportações/importações da Base Inteligente para transferir suas bases. Certificados precisam ser cadastrados novamente, pois o armazenamento local usa uma chave de criptografia própria. Guarde uma cópia da pasta `.local` em local privado; não a publique nem perca a chave de criptografia.

Para trazer as bases atuais das empresas com processadores, abra http://127.0.0.1:8000/local/bases e informe a chave administrativa do Railway na página local. O servidor baixa as bases sem alterar o Railway e cria um backup antes de importar. A chave não é gravada. Novos aprendizados locais são persistidos no SQLite; não são sincronizados automaticamente com o Railway. Não apague a pasta `.local`.

Após a primeira execução, configure as chaves de IA em `.local/config.json`, no computador, e reinicie. Não coloque chaves no JavaScript. Confirme que cada conta está no plano gratuito antes de alterar as confirmações de plano para `1`. A Groq também exige a configuração ZDR da conta e `GROQ_ZDR_CONFIRMED=1`. A análise fiscal sem IA continua disponível sem chaves. O conector Windows/eCAC continua dependendo da sua instalação local e pareamento.

O teste local não migra nem desliga a publicação. Só considere desligar o Railway depois de conferir seus arquivos reais, bases, IA e conector.
