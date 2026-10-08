# Trabalho neste repositório

Este checkout já está num ambiente isolado. Use o checkout existente; não crie worktrees salvo pedido explícito.

Leia README.md e TRIAGE.md antes de trabalhar com tickets. Preserve todas as restrições de leitura e de âmbito. Não grave segredos, tickets, anexos ou relatórios no Git. Dados de execução ficam nos diretórios ignorados data/, reports/ e state/ ou fora do checkout.

O leitor usa Python e a biblioteca padrão. Para validar alterações: `python -m unittest discover -s tests -v`. Testes devem usar dados fictícios e não podem precisar de credenciais.

Para Slack, leia SLACK.md. Só publique com autorização explícita para o relatório e canal; ligar ou testar autenticação não autoriza mensagens. Não solicite tokens na conversa. Nunca repita submissões incertas nem remova recibos para contornar a proteção. A publicação pode notificar membros do canal. O workflow Freshservice permanece em leitura.

Para iniciar o workflow: `python reader.py` na raiz deste checkout. O sucesso deve confirmar acesso, workspace e recolha completa, não apenas a existência do processo. Em seguida, analise a recolha segundo TRIAGE.md. O leitor não é um serviço persistente nem agenda execuções.

Para comandos pelo Slack, leia SLACK_COMMANDS.md. O comando /triagem de um utilizador da lista permitida, no canal e workspace validados, autoriza a consulta e a publicação das recomendações nesse canal. Outros comandos e mensagens não autorizam ações. O processo slack_bot.py precisa de permanecer ativo e de dependências em requirements.txt. Não use a subscrição Codex como se fornecesse uma chave API OpenAI. A análise usa TRIAGE_MODEL_API_KEY, uma chave separada, sem ferramentas ou escrita no Freshservice. Resultados são recomendações de IA sem revisão humana prévia e devem ser avaliados pela equipa.
