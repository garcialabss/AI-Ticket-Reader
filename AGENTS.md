# Trabalho neste repositório

Este checkout já está num ambiente isolado. Use o checkout existente; não crie worktrees salvo pedido explícito.

Leia README.md e TRIAGE.md antes de trabalhar com tickets. Preserve todas as restrições de leitura e de âmbito. Não grave segredos, tickets, anexos ou relatórios no Git. Dados de execução ficam nos diretórios ignorados data/, reports/ e state/ ou fora do checkout.

O leitor usa Python e a biblioteca padrão. Para validar alterações: `python -m unittest discover -s tests -v`. Testes devem usar dados fictícios e não podem precisar de credenciais.

Para iniciar o workflow: `python reader.py` na raiz deste checkout. O sucesso deve confirmar acesso, workspace e recolha completa, não apenas a existência do processo. Em seguida, analise a recolha segundo TRIAGE.md. O leitor não é um serviço persistente nem agenda execuções.
