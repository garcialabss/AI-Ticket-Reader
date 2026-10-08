# AI-Ticket-Reader

Leitor de tickets Freshservice para apoiar a triagem pelo Codex Cloud. O programa recolhe dados; o Codex analisa-os e apresenta recomendações na conversa. Não é um serviço autónomo de IA e não executa tarefas por agenda.

## Preparação

- Python 3.10 ou posterior, sem dependências externas.
- Utilizador Freshservice autorizado a ler tickets, conversas, workspaces, grupos e campos.
- Segredo `FRESHSERVICE_API_KEY` nas configurações seguras do ambiente Codex Cloud.
- Rede autorizada para `dnspt.freshservice.com` por HTTPS.

O cliente usa Basic Authentication da API Freshservice, com a chave como utilizador e `X` como palavra-passe. As credenciais são lidas do processo e nunca são guardadas pelo programa. Não coloque chaves no GitHub, em argumentos do terminal ou em mensagens. `.env.example` contém apenas configurações não secretas; o programa não carrega `.env` automaticamente.

## Executar

Na raiz do checkout existente:

```sh
python reader.py
```

A execução confirma o workspace ativo **Tech-Support**, consulta os grupos e o campo real **Sub-Fila**, e percorre todas as páginas de tickets desde a criação do workspace. Seleciona tickets por resolver: Open (2), Pending (3) e In Progress (6). Recolhe descrição e todas as conversas disponíveis. Se alguma consulta falhar, não publica uma recolha parcial nem avança o registo.

O resultado fica em `data/pending.json`. Use o Codex com as instruções de [TRIAGE.md](TRIAGE.md) para analisar esse ficheiro e apresentar os resultados na conversa. A recolha pode conter dados pessoais e URLs de anexos; mantenha-a no ambiente autorizado. Não a envie para o GitHub.

Depois de apresentar **todos** os tickets da recolha, registe a conclusão:

```sh
python reader.py --ack-report data/pending.json
```

Esta ação só altera `state/reviewed.json` localmente. Nunca a execute após uma análise parcial. Para análise parcial, mantenha o registo anterior e recolha novamente.

A próxima recolha inclui tickets por resolver ainda não registados e aqueles cujo conteúdo, metadados ou conversas mudaram. O histórico local não demonstra análises feitas por outras pessoas. Sem esse ficheiro, a primeira execução volta a incluir todos os tickets por resolver. A persistência depende de conservar o diretório `state`; publicar o ambiente não cria uma agenda nem garante a persistência entre máquinas sem validação.

## Segurança e limites

- O cliente só implementa GET e recusa redirecionamentos autenticados.
- Não altera grupo, Sub-Fila, agente, prioridade ou estado; não envia respostas, notas ou notificações.
- Category e Sub-Fila são campos diferentes; as opções são consultadas em cada execução.
- Não descarrega anexos nem segue ligações contidas nos tickets.
- Não inventa classificações; não usa regras de palavras-chave como diagnóstico.
- O inventário completo privilegia cobertura de tickets antigos; em ambientes grandes pode atingir limites da API. Ao receber HTTP 429, aguarde antes de repetir. Nenhum estado é avançado nesse erro.
- As impressões digitais evitam repetir conteúdos idênticos apenas neste registo local.

## Validação

```sh
python -m unittest discover -s tests -v
```

Os testes usam dados fictícios. A validação com o Freshservice real requer a credencial e as permissões referidas acima.

## O que fica no GitHub

Código, testes, documentação e instruções de triagem. `data/`, `reports/`, `state/`, `.env` e logs são ignorados. Nunca force a inclusão desses diretórios nem publique conteúdo de tickets, anexos ou chaves. O programa de recolha não cria relatórios automaticamente: as recomendações são produzidas pelo Codex na conversa.
