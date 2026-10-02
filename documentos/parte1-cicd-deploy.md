# Seu primeiro deploy de IA (Parte 1: CI/CD e Deploy)

Apostila do aluno do curso *Construindo seu Chat de IA Personalizado*, do Instituto NTA (Instituto Nacional de Tecnologia Aplicada). Prof. Thiago Azeredo Rodrigues.

Do chat personalizado à URL pública, com Git, GitHub Actions e Hugging Face Spaces. Encontro 1 de 2; no encontro 2, o assistente ganha uma base de conhecimento (RAG).

## 01 O que você vai construir hoje

Um assistente de IA com a sua cara: nome, cor, logo e especialidade escolhidos por você, publicado numa URL que qualquer pessoa abre no navegador. E, mais importante que o chat, um **processo automático de publicação**: toda vez que você alterar algo no repositório, o assistente é testado e republicado sozinho.

O chat é o pretexto. O assunto da aula é o caminho entre o seu arquivo e a URL pública: Git, CI/CD e deploy.

**O fluxo do projeto, passo a passo:**

1. **Você** edita o `config.yml` no site do GitHub e faz commit (push).
2. **GitHub Actions**, uma máquina Linux descartável: o job *testar* roda o `testes.py`; se passou, o job *publicar* envia os arquivos ao Space (usa o secret `HF_TOKEN`).
3. **Hugging Face Space** recebe os arquivos, instala e roda o `app.py` (usa o secret `ANTHROPIC_API_KEY`) e chama a API do modelo.
4. **API do modelo** recebe a conversa e devolve a resposta aos poucos (streaming).
5. **Qualquer pessoa** abre a URL do Space e conversa com o seu assistente.

**Portão:** se o `testes.py` falhar, o job publicar nem começa e nada é publicado.

### O que você precisa ter

|**Conta ou item**|**Para quê**|**Onde**|
|---|---|---|
|Conta no GitHub|Guardar o código e rodar a automação (Actions)|github.com|
|Conta no Hugging Face|Hospedar o assistente (Spaces)|huggingface.co|
|Chave da API Anthropic, com crédito|O assistente conversar com o modelo|console.anthropic.com|
|Um navegador|Todo o resto|Nada a instalar hoje|

### Não precisa instalar nada

Toda a aula acontece no navegador. O código não roda no seu computador: ele é testado numa máquina do GitHub e executado numa máquina do Hugging Face. Instalação local é opcional e está no apêndice.

## 02 O que é deploy

Enquanto um programa roda só no seu computador, ele existe só para você. Ele para quando você desliga a máquina, não tem endereço público e depende de tudo que está instalado ali.

**Deploy** (implantar, publicar, colocar no ar) é levar a aplicação para um ambiente onde outras pessoas conseguem usar: com endereço, ligada o tempo todo e independente do seu computador. Um deploy bem feito responde a três perguntas:

- **Onde a aplicação roda?** Numa máquina de um provedor (GitHub, Hugging Face, Render, Azure).

- **Como ela chega lá?** Manualmente (alguém sobe arquivos) ou automaticamente (um processo faz isso a cada mudança).

- **Onde ficam os segredos?** Chaves e senhas nunca vão junto com o código; ficam guardadas no ambiente que executa.

### A frase que resume o problema

"Na minha máquina funciona." Deploy é o conjunto de práticas que faz a aplicação funcionar também na máquina dos outros, do mesmo jeito, toda vez.

## 03 Tipos de deploy

Existem dezenas de serviços, mas eles se organizam em poucas categorias. O que muda de uma para outra é quanto controle você tem e quanto trabalho de infraestrutura fica com você.

|**Tipo**|**O que o servidor faz**|**Exemplos**|**Bom para**|
|---|---|---|---|
|Site estático|Entrega arquivos prontos (HTML, CSS, JS). Não executa nada.|GitHub Pages, Netlify, Cloudflare Pages|Portfólio, documentação, painéis gerados antes|
|Plataforma de apps (PaaS)|Executa o seu código: você entrega o projeto, ela cuida da máquina.|Hugging Face Spaces, Render, Railway|Protótipos, demos de IA, APIs pequenas|
|Nuvem gerenciada|Executa o seu código com rede, identidade, escala e monitoramento corporativos.|Azure App Service, AWS, Google Cloud Run|Produção em empresa|
|Serverless|Executa uma função só quando é chamada; cobra por execução.|Azure Functions, AWS Lambda|Tarefas curtas e eventuais|

### A pergunta que decide

**A aplicação precisa executar código quando alguém acessa?** Se não, site estático resolve e é gratuito. Se sim, você precisa de um serviço que execute código. E há uma segunda pergunta, que costuma decidir sozinha: **a aplicação usa algum segredo?**

### Por que o nosso chat não pode ir para o GitHub Pages

Cada pergunta do usuário exige uma chamada à API do modelo, e essa chamada exige a chave da API. Num site estático, todo o código vai para o navegador do visitante. Se a chave estiver ali, qualquer pessoa abre o código-fonte da página e copia. É vazamento garantido.

Por isso o chat precisa de um servidor: o navegador manda a pergunta, o servidor (que guarda a chave) chama o modelo e devolve só a resposta.

### Por que Hugging Face Spaces hoje

- **Executa Python e guarda segredos**, o que o chat exige.

- **Gratuito para CPU básica**, suficiente para um chat que só repassa perguntas ao modelo.

- **Não puxa código do GitHub sozinho**: quem publica é o GitHub Actions. Isso torna a automação visível, que é o que queremos aprender.

- **Gradio é nativo**: a biblioteca de interface que usamos roda sem configuração extra.

**E o Render?** Também serviria, e é mais parecido com um serviço de nuvem corporativo. Duas diferenças: ele se conecta direto ao GitHub e publica sozinho (o Actions ficaria de enfeite, a menos que você desligue isso e use um Deploy Hook), e no plano gratuito o serviço dorme após cerca de 15 minutos sem acesso, levando perto de um minuto para acordar. O Space gratuito só hiberna depois de muito mais tempo parado. Limites de planos gratuitos mudam: confira na documentação antes de usar em algo sério.

## 04 Git e GitHub: o mínimo

**Git** é um programa que guarda o histórico de uma pasta. **GitHub** é um site que hospeda essas pastas e acrescenta coisas em volta, entre elas a capacidade de executar automações. Analogia: o Git é o controle de versões do documento; o GitHub é o Google Drive que guarda, compartilha e ainda faz coisas com o arquivo.

|**Termo**|**O que é**|
|---|---|
|Repositório|Uma pasta com histórico. "Repo", para os íntimos.|
|Commit|Uma fotografia do estado da pasta, com uma mensagem explicando o que mudou. O histórico é uma fila de commits. Quando você edita um arquivo no site e clica em **Commit changes**, está criando um.|
|Push|Enviar commits para um repositório remoto. É o verbo que dispara a automação. Editando pelo site, o commit já acontece no GitHub, e para o Actions isso conta como push.|
|Branch|Uma linha paralela de trabalho. Hoje usamos só a principal, a **main**.|

Merge, rebase, conflito e pull request são importantes em equipe e ficam para outra ocasião.

### Público ou privado

Repositório público: qualquer pessoa vê o código. Privado: só quem você autorizar. Para aprender, público funciona bem, desde que nunca exista senha, chave ou dado pessoal dentro dele. O arquivo de testes do projeto verifica isso por você.

## 05 Por que existe linha de comando

O terminal é uma forma de conversar com o computador escrevendo em vez de clicando. Tem três vantagens que a interface gráfica não tem:

1. **É repetível.** Um comando escrito pode ser guardado e executado de novo, igual, mil vezes.

2. **É automatizável.** Um robô não sabe clicar num botão, mas sabe executar um comando.

3. **É o que existe no servidor.** A máquina que roda seu código na nuvem não tem tela.

Por isso o arquivo de automação é uma lista de comandos. Quando você lê `python testes.py` dentro do YAML, está lendo o que você digitaria no terminal, só que quem digita é o GitHub. Automatizar é escrever o que você faria à mão.

## 06 CI/CD

A sigla junta duas ideias que andam juntas.

**CI, Integração Contínua.** Toda vez que o código muda, verificações automáticas rodam: os arquivos estão válidos? os testes passam? Serve para descobrir que algo quebrou em minutos, não em semanas.

**CD, Entrega ou Implantação Contínua.** Se as verificações passaram, o resultado segue para o ar sem ninguém subir arquivo à mão. A diferença entre as duas versões do CD é quem aperta o botão final:

|**Modalidade**|**Quem publica**|
|---|---|
|Entrega contínua (delivery)|Fica tudo pronto e testado; uma pessoa aprova a publicação.|
|Implantação contínua (deployment)|Publica sozinho, sem aprovação humana.|

### No projeto de hoje

|**Parte**|**No nosso projeto**|
|---|---|
|CI|O job **testar** roda o `testes.py`: config válido, campos preenchidos, tema existente, logo aceita, Python sem erro de sintaxe e nenhuma chave de API esquecida nos arquivos.|
|CD|O job **publicar** envia o repositório para o Space, que reconstrói e reinicia o assistente. É implantação contínua: passou no teste, vai para o ar.|

### Com IA no meio, a pergunta muda

Publicar sozinho um arquivo de configuração é tranquilo. Publicar sozinho algo que um modelo de IA gerou, e que pessoas vão ler, é uma decisão séria. O teste deixa de conferir "a resposta certa" (saída de modelo varia) e passa a conferir se a saída está dentro de critérios. Voltaremos a isso no encontro 2, quando o assistente passar a responder com base em documentos.

## 07 GitHub Actions: a máquina descartável

Este é o conceito que mais confunde e o que mais vale entender. Quando o processo dispara, o GitHub liga um computador novo, uma máquina virtual Linux limpa que não existia segundos antes. Ela:

1. baixa uma cópia do seu repositório;

2. executa, em ordem, os comandos que você escreveu no YAML;

3. entrega o resultado (no nosso caso, envia os arquivos ao Hugging Face);

4. é destruída.

Nada sobrevive entre uma execução e outra. Se o processo instalou o Python, a próxima execução instala de novo.

### O erro de raciocínio mais comum

Achar que o Actions roda no seu computador, ou que o GitHub "entende" seu Python. Ele liga um Linux vazio e digita seus comandos. Se o comando funciona num terminal, funciona ali; se não funciona, ali também não vai funcionar.

|**Termo**|**O que é**|
|---|---|
|Workflow|O processo inteiro, descrito num arquivo `.yml` dentro de `.github/workflows/`|
|Trigger (gatilho)|O que faz o processo começar|
|Job|Um bloco de trabalho, que roda numa máquina. Nosso workflow tem dois: testar e publicar|
|Step (passo)|Um comando ou uma ação dentro do job|
|Runner|A máquina descartável que executa tudo|
|Action|Um pedaço de automação pronto, feito por outra pessoa (ex.: `actions/checkout`)|

### Gatilhos

|**Gatilho**|**Quando dispara**|**Usamos hoje?**|
|---|---|---|
|`push`|Alguém enviou código novo (inclui editar e dar commit pelo site)|Sim|
|`workflow_dispatch`|Botão **Run workflow**, apertado por uma pessoa na aba Actions|Sim|
|`schedule`|Horário marcado, no formato cron. Ex.:`'0 11 * * *'` é todo dia às 11h UTC, ou seja, 8h de Brasília|Não; útil quando os dados mudam sozinhos|

Atenção ao fuso: o cron do GitHub usa UTC, três horas à frente de Brasília. É um tropeço clássico.

## 08 Segredos: onde fica cada chave

Chave de API nunca vai dentro do repositório. Neste projeto existem **duas** chaves, e cada uma fica num lugar diferente. A regra que explica tudo:

### O segredo fica com quem executa

Quem precisa usar a chave é a máquina que roda o comando. Então é ali que ela é cadastrada.

|**Chave**|**Quem usa**|**Onde cadastrar**|
|---|---|---|
|`ANTHROPIC_API_KEY`|O app.py, rodando no Space, a cada pergunta do usuário|Hugging Face: Space, **Settings**, **Variables and secrets**,**New secret**|
|`HF_TOKEN`|O runner do GitHub Actions, para enviar os arquivos ao Space|GitHub: repositório, **Settings**, **Secrets and variables**,**Actions**,**New repository secret**|

Nos dois serviços o valor fica cifrado, é injetado como variável de ambiente na hora da execução e não aparece em logs (se for impresso por acidente, aparece `***`). No código, a chave é lida assim:

```
CHAVE = os.environ.get("ANTHROPIC_API_KEY")
```

### Chave commitada por engano é chave vazada

Mesmo depois de apagada, ela continua no histórico do Git, e robôs varrem repositórios públicos o tempo todo atrás disso. Se acontecer, o certo é **revogar a chave** no painel do provedor e gerar outra. Tentar esconder não resolve.

## 09 YAML em cinco regras

YAML é um formato de arquivo de configuração. Não é linguagem de programação: é uma lista de coisas com nome. Neste projeto há dois arquivos YAML: o `config.yml ` (seu assistente) e o ` deploy.yml` (o processo).

**1. chave: valor.**

```
nome: Assistente do Agro
```

**2. A indentação define o que está dentro de quê.** Só espaços, nunca Tab. Tab é erro de sintaxe e é o tropeço número um.

```
jobs:
  testar:
    runs-on: ubuntu-latest
```

**3. O hífen cria item de lista.**

```
exemplos:
  - Como calcular a produtividade da soja?
  - O que é rotação de culturas?
```

**4. A barra vertical | guarda várias linhas.** É assim que o prompt de sistema cabe no config.

```
prompt_sistema: |
  Você é um assistente especializado em agronegócio.
  Responda em português do Brasil.
```

**5. # é comentário.** Os arquivos do projeto são cheios deles, de propósito.

### Confira antes de salvar

O editor do GitHub marca erro de sintaxe no arquivo de workflow. No config.yml, quem pega o erro é o portão: se o YAML estiver quebrado, o job testar fica vermelho e nada é publicado.

## 10 O projeto por dentro

```
assistente-ia/
├── .github/
│ └── workflows/
│ └── deploy.yml o processo: testar e publicar
├── app.py o chat (você quase nunca mexe)
├── config.yml SEU assistente: nome, cor, logo, prompt
├── logo.svg a logo
├── testes.py o portão
├── requirements.txt bibliotecas que o Space instala
└── README.md cabeçalho lido pelo Hugging Face
```

### config.yml: o único arquivo que você precisa editar

|**Campo**|**O que faz**|
|---|---|
|`nome ` e`descricao`|Título e subtítulo no topo da página|
|`tema`|Cor principal: azul, verde, vermelho, laranja, roxo ou grafite|
|`logo`|Um arquivo .svg no repositório ou um link https para uma imagem|
|`modelo ` e`max_tokens`|Qual modelo responde e o tamanho máximo da resposta|
|`prompt_sistema`|Quem é o assistente, com quem ele fala, como responde e o que ele não faz|
|`exemplos`|Perguntas prontas que aparecem como botões|

O prompt de sistema é onde está a inteligência do seu assistente. Um bom prompt define **papel** (especialista em quê), **público** (com quem fala), **formato** (tamanho, idioma, tom) e **limites** (o que não inventar, o que recusar).

### app.py em quatro ideias

1. **Lê o config.yml** e monta a interface com o Gradio: cabeçalho com logo, nome e descrição, e o chat embaixo.

2. **Pega a chave do ambiente**, nunca do código. Sem chave, o chat avisa como configurar, em vez de quebrar.

3. **Reenvia a conversa inteira a cada pergunta.** O modelo não tem memória própria: quem lembra é o app, que junta o histórico da sessão e manda tudo de novo.

4. **Responde aos poucos (streaming)**, como os chats comerciais, em vez de esperar a resposta completa.

```
with cliente.messages.stream(
    model=CONFIG["modelo"],
    system=CONFIG["prompt_sistema"], # quem é o assistente
    messages=mensagens, # a conversa inteira
    max_tokens=...,
) as fluxo:
    for pedaco in fluxo.text_stream:
        texto += pedaco
        yield texto # a tela atualiza a cada pedaço
```

O Gradio é uma biblioteca Python da mesma família do Streamlit: gera a página web sem você escrever HTML. A diferença é o foco. O Streamlit nasceu para painéis de dados; o Gradio, para demonstrar modelos de IA, e tem o componente `gr.ChatInterface` que monta um chat completo em poucas linhas.

### testes.py: o portão

Roda no GitHub Actions antes de qualquer publicação. Se uma verificação falhar, o processo para com a lista de problemas e a versão que já estava no ar continua funcionando.

|**Verifica**|**Por quê**|
|---|---|
|config.yml é YAML válido|Um espaço fora do lugar quebraria o app no Space|
|Campos obrigatórios preenchidos|Sem nome ou prompt, a página sai incompleta|
|Tema está na lista|Evita cor inexistente|
|Prompt com conteúdo real|Prompt de uma linha gera assistente genérico|
|Logo existe e é .svg ou link|O Hugging Face recusa .png e .jpg enviados sem configuração extra|
|app.py sem erro de sintaxe|Erro descoberto em segundos, não depois do build|
|Nenhuma chave de API nos arquivos|Barra o vazamento antes de ele chegar ao público|

### deploy.yml: o processo, bloco a bloco

```
# versão resumida: no arquivo real, cada passo tem um nome
env:
  HF_USUARIO: seu-usuario # EDITE: seu usuário no Hugging Face
  HF_SPACE: meu-assistente # EDITE: nome exato do Space
on:
  push:
    branches: [main] # todo commit na main dispara
  workflow_dispatch: # botão Run workflow
jobs:
  testar: # job 1: o portão
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install pyyaml
      - run: python testes.py
  publicar: # job 2: só roda se o testar passou
    needs: testar
    runs-on: ubuntu-latest # outra máquina, nova e limpa
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0 # histórico completo, exigido pelo HF
      - env:
          HF_TOKEN: ${{ secrets.HF_TOKEN }}
        run: |
          REPO="huggingface.co/spaces/${HF_USUARIO}/${HF_SPACE}"
          git push --force "https://${HF_USUARIO}:${HF_TOKEN}@${REPO}" HEAD:main
```

Repare em `needs: testar`: é essa linha que transforma o teste em portão. E repare que o job publicar começa numa máquina nova: ele baixa o repositório de novo, porque nada sobrevive entre máquinas.

O README.md também tem função técnica: o cabeçalho entre as linhas `---` diz ao Hugging Face que o Space é Gradio, qual versão usar e qual arquivo executar. Se apagar esse cabeçalho, o Space não sabe como rodar o app.

## 11 Passo a passo da aula

### A. Seu repositório no GitHub

1. Abra o repositório modelo compartilhado pelo professor e clique em **Use this template**, depois **Create a new repository**. Dê um nome (ex.: `assistente-ia`), deixe **Public** e crie.

2. Alternativa, se recebeu os arquivos em .zip: crie um repositório vazio, clique em **Add file**, **Upload files** e arraste o conteúdo. Confira se a pasta `.github/workflows` subiu (veja os erros comuns).

### B. O Space no Hugging Face

1. Em huggingface.co, clique em **New**, **Space**.

2. Escolha um nome (ex.: `meu-assistente`), SDK **Gradio**, template **Blank**, hardware **CPU basic** (gratuito) e visibilidade **Public**. Crie.

3. No Space, abra **Settings**, **Variables and secrets**, **New secret**. Nome: `ANTHROPIC_API_KEY`. Valor: sua chave da Anthropic.

### C. A ponte entre os dois

1. No Hugging Face, abra seu perfil, **Settings**, **Access Tokens**, **Create new token**. Tipo **Write**. Copie o valor (começa com `hf_`).

2. No GitHub, no seu repositório: **Settings**, **Secrets and variables**, **Actions**, **New repository secret**. Nome: `HF_TOKEN`. Cole o valor.

3. Abra `.github/workflows/deploy.yml `, clique no lápis e troque ` seu-usuario ` e ` meu-assistente` pelos seus dados, exatamente como aparecem na URL do Space. Clique em **Commit changes**.

### D. O primeiro deploy

1. O commit do passo anterior já disparou o processo. Abra a aba **Actions** e clique na execução em andamento.

2. Acompanhe os dois jobs. Verde nos dois: os arquivos chegaram ao Space.

3. Volte ao Space. Ele mostra **Building** por um ou dois minutos e depois **Running**. Converse com o assistente.

### E. Personalize

1. Edite o `config.yml` pelo lápis: nome, descrição, tema, prompt de sistema e exemplos do **seu** domínio. Commit.

2. Acompanhe o novo deploy na aba Actions e confira o resultado no Space.

3. Para trocar a logo: suba um `.svg ` ou use um link ` https ` de imagem no campo ` logo`.

### F. Veja o portão funcionando

1. No `config.yml `, troque o tema para ` rosa` (que não existe) e faça commit.

2. Na aba Actions: o job **testar** fica vermelho, o **publicar** nem começa. Abra o passo vermelho e leia a mensagem.

3. Abra o Space: a versão anterior continua no ar, intacta. É isso que o portão protege.

4. Corrija o tema, faça commit e veja o verde voltar.

## 12 Por que o chat esquece

Teste: converse, feche a aba e abra de novo. A conversa sumiu. Não é defeito; são dois tipos diferentes de memória.

|**Tipo**|**Como funciona**|**Precisa de banco?**|
|---|---|---|
|Memória da conversa|Enquanto a aba está aberta, o app guarda o histórico da sessão e reenvia tudo ao modelo a cada pergunta.|Não. É o que temos hoje.|
|Histórico salvo|A conversa sobrevive ao fechamento da aba, ou você consegue ler depois o que os visitantes perguntaram.|Sim.|

E não adianta gravar num arquivo dentro do Space: o disco do Space gratuito é apagado a cada reinício ou novo deploy, pelo mesmo motivo que o runner do Actions é descartável. **Tudo que precisa sobreviver vai para fora da máquina**, num banco de dados como o Supabase, com a chave dele também guardada como secret.

### Guardar conversa é tratar dado pessoal

Se um dia você salvar o que os visitantes digitam, isso entra na LGPD: é preciso avisar na página o que é guardado, para quê e por quanto tempo. Decida isso antes de ligar o banco, não depois.

### No encontro 2

O assistente ganha uma base de conhecimento. Você coloca documentos do seu domínio numa pasta, e a cada push o Actions reconstrói o índice de busca, roda perguntas de teste para conferir se o trecho certo é encontrado e só então publica. É o mesmo portão de hoje, agora avaliando a qualidade das respostas.

## 13 Erros comuns na primeira vez

|**Sintoma**|**Causa provável**|**Conserto**|
|---|---|---|
|Job testar vermelho|O portão encontrou um problema|Abra o passo "Rodar o portão" e leia a lista impressa|
|O workflow não aparece na aba Actions|O arquivo não está em `.github/workflows/`. O upload pelo navegador às vezes ignora pastas que começam com ponto|Add file, Create new file, digite o caminho completo `.github/workflows/deploy.yml` e cole o conteúdo|
|Publicar falha com Authentication failed ou 403|`HF_TOKEN` ausente, com nome diferente ou do tipo Read|Gere um token Write e cadastre de novo com o nome exato|
|Repository not found|`HF_USUARIO ` ou`HF_SPACE` diferente do Space criado|Copie exatamente da URL do Space|
|Push rejeitado por arquivo binário|Imagem .png ou .jpg no repositório|Use logo .svg ou link https e apague a imagem|
|did not find expected key|Tab ou indentação desalinhada no YAML|Só espaços; confira a linha citada|
|Space em Build error|Cabeçalho do README.md apagado ou alterado|Abra a aba Logs do Space e restaure o cabeçalho|
|Chat responde que a chave|Secret ausente no Space ou com|Cadastre `ANTHROPIC_API_KEY` no|
|não foi configurada|outro nome|Space e reinicie (Settings, Restart)|
|Erro de autenticação ou de crédito na resposta|Chave inválida, revogada ou conta sem crédito|Confira no console da Anthropic|
|Actions verde, Space com versão antiga|O Space ainda está reconstruindo|Espere o status Running e recarregue|
|Space mostra Sleeping|Ficou muito tempo sem acesso|Abra a página; ele acorda em instantes|

### Aviso não é erro

Mensagens amarelas sobre versão do Node ou migração do Ubuntu são avisos de manutenção futura. O que importa é a marca do job: verde passou, vermelho falhou.

## 14 Apêndice: rodar na sua máquina

Opcional. Serve para quando você quiser testar mudanças antes de subir.

- **Windows:** instale o Git for Windows (git-scm.com), que traz o Git Bash, e o Python (python.org). No instalador do Python, marque **Add Python to PATH**.

- **macOS:** no Terminal, `git --version ` oferece instalar as ferramentas. Python atual em python.org ou ` brew install python git`.

- **Linux:** `sudo apt install git python3 python3-pip` (Debian e Ubuntu).

```
git clone https://github.com/<usuario>/<repositorio>.git
cd <repositorio>
pip install gradio==5.49.1 anthropic pyyaml
python testes.py # o mesmo portão do Actions
export ANTHROPIC_API_KEY=sua-chave # Windows (PowerShell): $env:ANTHROPIC_API_KEY="sua-chave"
python app.py # abra http://localhost:7860
```

A chave vai na variável de ambiente do terminal, nunca num arquivo do repositório.

## 15 Glossário

**Action**: automação pronta de terceiros, reaproveitada no workflow.

**Branch**: linha paralela de desenvolvimento.

**Build**: etapa em que o serviço instala dependências e prepara a aplicação para rodar.

**CD**: entrega ou implantação contínua.

**CI**: integração contínua.

**Commit**: fotografia do estado do repositório, com mensagem.

**Cron**: formato para marcar horário de execução recorrente, em UTC no GitHub.

**Deploy**: colocar a aplicação no ar para outras pessoas usarem.

**Gradio**: biblioteca Python que gera interfaces web para modelos de IA.

**Job**: bloco de trabalho dentro de um workflow, executado numa máquina.

**PaaS**: plataforma que executa seu código cuidando da infraestrutura.

**Portão**: etapa de teste que precisa passar para a publicação acontecer.

**Prompt de sistema**: instrução fixa que define papel, público, formato e limites do assistente.

**Push**: enviar commits para o repositório remoto.

**Repositório**: pasta com histórico.

**Runner**: máquina descartável que executa o workflow.

**Secret**: valor sensível guardado cifrado e injetado na execução.

**Site estático**: site de arquivos prontos, sem código executado no servidor.

**Space**: aplicação hospedada no Hugging Face.

**Streaming**: resposta entregue em pedaços, à medida que o modelo gera.

**Token**: credencial de acesso; também a unidade de texto que o modelo processa.

**Workflow**: o processo automatizado, descrito em YAML.

**YAML**: formato de arquivo de configuração, sensível a indentação.
