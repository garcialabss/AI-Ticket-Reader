# Executar a triagem pelo Slack

## Funcionamento

Um utilizador autorizado escreve `/triagem` no canal configurado. O processo recebe o comando por Socket Mode, confirma a identidade Slack, consulta apenas o workspace Tech-Support, lê os tickets por resolver novos ou alterados e exemplos históricos, e pede recomendações à API OpenAI. Publica uma mensagem por ticket no mesmo canal. Não altera tickets nem escreve notas ou respostas no Freshservice.

As recomendações são de IA, sem revisão humana prévia. O comando autoriza esta publicação e pode gerar notificações. O bot não responde a mensagens comuns ou menções. Use `/triagem ajuda` para instruções. Não há agenda automática.

## Configurar a Slack App

1. Abra a aplicação AI-Ticket-Reader em https://api.slack.com/apps.
2. Em **Socket Mode**, ative **Enable Socket Mode**.
3. Em **Basic Information → App-Level Tokens**, crie um token com o nome `triagem-socket` e o scope **connections:write**. Guarde o token `xapp-…` como segredo **SLACK_APP_TOKEN**, autorizado para `slack.com`.
4. Em **Slash Commands → Create New Command**, crie **/triagem** com a descrição “Analisar tickets Tech-Support” e Usage Hint `[ajuda]`. Com Socket Mode ativo não precisa de um endpoint público de Request URL.
5. Mantenha **Bot Token Scopes → chat:write**. Se o Slack pedir reinstalação após alterar a app, conclua **Reinstall to Workspace → Allow**. Confirme o token bot nas configurações seguras.
6. O bot deve continuar adicionado ao canal autorizado. Não são necessárias permissões de leitura do histórico Slack para receber o comando.

## Credenciais e variáveis no ambiente

| Nome | Tipo | Finalidade |
| --- | --- | --- |
| FRESHSERVICE_API_KEY | Segredo | Leitura de dnspt.freshservice.com |
| SLACK_BOT_TOKEN | Segredo | Autenticação e publicação em slack.com |
| SLACK_APP_TOKEN | Segredo | Socket Mode em slack.com |
| TRIAGE_MODEL_API_KEY | Segredo | API OpenAI em api.openai.com |
| SLACK_CHANNEL_ID | Variável | C0C8K754PU0 |
| SLACK_ALLOWED_USER_IDS | Variável | U0C299E761E; IDs adicionais separados por vírgulas |
| TRIAGE_MODEL | Variável | gpt-4.1, modelo com Structured Outputs |

A chave OpenAI é separada da subscrição ChatGPT/Codex e usa faturação da API. Crie-a num projeto autorizado em https://platform.openai.com/api-keys. Os assuntos, descrições e conversas dos tickets e de até quatro exemplos históricos são enviados a essa API para análise; anexos não são descarregados. `store: false` desativa o armazenamento de respostas na API, mas não é uma garantia geral de retenção zero. Utilize este modo apenas com um projeto autorizado pela organização para esses dados. Nunca envie chaves pela conversa ou pelo Slack.

A rede precisa de permitir dnspt.freshservice.com, api.openai.com, slack.com e ligações WebSocket HTTPS aos hosts Slack (por exemplo wss-primary.slack.com e wss-backup.slack.com). Preserve TLS e os proxies do ambiente; não desative verificação de certificados. Se o ambiente não suportar o WebSocket, use um host de execução compatível.

## Instalar e iniciar

Na raiz do checkout:

```sh
python -m venv /workspace/.ticket-reader-venv
/workspace/.ticket-reader-venv/bin/python -m pip install -r requirements.txt
/workspace/.ticket-reader-venv/bin/python -m unittest discover -s tests -v
/workspace/.ticket-reader-venv/bin/python slack_bot.py
```

O recetor mantém-se em primeiro plano. Com o processo ativo, escreva `/triagem ajuda` no canal; só uma resposta a esse comando confirma a receção funcional. Depois execute `/triagem`. Um PID ou a mensagem de arranque não prova que Socket Mode esteja ligado.

Para disponibilidade permanente, execute num servidor ou serviço da organização que permaneça ativo, com armazenamento persistente de `state/` e credenciais seguras. A instalação neste ambiente Codex Cloud não garante execução 24/7; suspensão ou encerramento da tarefa interrompe o recetor. Não há infraestrutura de alojamento externo provisionada neste repositório.

## Estado, falhas e duplicados

`state/slack-reviewed.json` acompanha somente análises entregues por este modo; não importa automaticamente análises anteriores da conversa Codex. A primeira execução inclui todos os tickets por resolver. `state/slack-pending.json` conserva exatamente os resultados preparados, permitindo terminar um lote parcialmente publicado sem gerar textos diferentes. `state/slack-receipts.json` impede repetição do mesmo conteúdo e bloqueia submissões incertas. `state/slack-jobs.json` impede repetir o mesmo pedido Slack.

Só depois de todas as mensagens confirmadas se avança o registo. Uma falha não demonstra que nenhuma mensagem tenha sido publicada: consulte recibos e o canal. Não apague recibos para repetir e não repita submissões incertas sem confirmar o ocorrido. Não há reconciliação automática. Uma nova execução pode concluir uma publicação parcial com os conteúdos guardados; a execução seguinte recolhe mudanças posteriores.

Permissões e canal são verificados antes de aceitar o comando. Só uma análise corre de cada vez. Texto livre não é tratado como instrução. Grupos e Sub-Filas são validados contra opções reais, e IDs gerados contra os tickets selecionados. Isso limita erros de formato e âmbito, mas não garante correção factual das recomendações. Verifique justificações e limitações antes de atuar.
