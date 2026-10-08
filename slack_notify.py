"""Publish reviewed triage reports to Slack, only through explicit --send."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

from reader import AccessError, NoRedirect, read_json, write_private


class Slack:
    def __init__(self, token):
        if not token:
            raise AccessError('Falta SLACK_BOT_TOKEN nas configurações seguras.')
        self.token = token
        self.opener = urllib.request.build_opener(NoRedirect)

    def call(self, method, payload):
        if method not in ('auth.test', 'chat.postMessage'):
            raise AccessError('Método Slack não permitido pelo cliente.')
        req = urllib.request.Request('https://slack.com/api/' + method,
                                     data=json.dumps(payload).encode(), method='POST',
                                     headers={'Authorization': 'Bearer ' + self.token,
                                              'Content-Type': 'application/json; charset=utf-8'})
        try:
            with self.opener.open(req, timeout=30) as response:
                result = json.load(response)
        except (urllib.error.URLError, AccessError, ValueError):
            raise AccessError('Não foi possível confirmar o resultado da chamada Slack.') from None
        if not result.get('ok'):
            # Only expose known error identifiers, never response contents or credentials.
            error = result.get('error', 'unknown_error')
            if not re.fullmatch(r'[a-z_]+', str(error)):
                error = 'unknown_error'
            raise AccessError('Slack recusou a operação: ' + error)
        return result


def escape(text):
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def render(report):
    if report.get('workspace') != 'Tech-Support' or not report.get('reviewed'):
        raise AccessError('Use um relatório revisto do workspace Tech-Support.')
    tickets = report.get('tickets')
    if not isinstance(tickets, list) or not tickets:
        raise AccessError('Relatório sem tickets revistos.')
    sections = ['Triagem Tech-Support — recomendações; tickets não alterados.']
    labels = [('summary', 'Resumo'), ('group', 'Grupo recomendado'),
              ('subqueue', 'Sub-Fila recomendada'), ('justification', 'Justificação'),
              ('confidence', 'Confiança e limitações'), ('suggested_reply', 'Resposta sugerida'),
              ('missing_information', 'Informação em falta')]
    seen = set()
    for ticket in tickets:
        ident = ticket.get('id')
        if type(ident) is not int or ident <= 0 or ident in seen:
            raise AccessError('IDs inválidos ou duplicados no relatório.')
        seen.add(ident)
        url = ticket.get('url', '')
        if url != f'https://dnspt.freshservice.com/a/tickets/{ident}':
            raise AccessError('Ligação fora do tenant ou incoerente com o ticket.')
        lines = [f'<{url}|Ticket #{ident}>']
        for field, label in labels:
            value = ticket.get(field)
            if not isinstance(value, str) or not value.strip():
                raise AccessError('Campo obrigatório ausente: ' + field)
            lines.append(label + ': ' + escape(value))
        sections.append('\n'.join(lines))
    text = '\n\n'.join(sections)
    if len(text) > 35000:
        raise AccessError('Relatório demasiado grande. Divida-o em lotes revistos antes de publicar.')
    return text


def publish(client, channel, text, receipt):
    if not re.fullmatch(r'[CG][A-Z0-9]+', channel or ''):
        raise AccessError('Defina SLACK_CHANNEL_ID com o ID do canal autorizado.')
    digest = hashlib.sha256((channel + '\n' + text).encode()).hexdigest()
    journal = read_json(receipt, {})
    if digest in journal:
        entry = journal[digest]
        if entry.get('status') == 'sent':
            return 'Relatório já publicado; envio não repetido.'
        raise AccessError('Há uma submissão com resultado incerto. Verifique o Slack antes de qualquer novo envio; não apague o registo para repetir.')
    journal[digest] = {'status': 'uncertain', 'channel': channel}
    write_private(receipt, journal)
    result = client.call('chat.postMessage', {'channel': channel, 'text': text,
                        'unfurl_links': False, 'unfurl_media': False, 'link_names': False,
                        'parse': 'none'})
    if result.get('channel') != channel or not result.get('ts'):
        raise AccessError('Resultado Slack incompleto. Não repita sem verificar.')
    journal[digest] = {'status': 'sent', 'channel': channel, 'ts': result['ts']}
    write_private(receipt, journal)
    return 'Publicação confirmada pelo Slack; recibo local guardado.'


def main(argv=None):
    parser = argparse.ArgumentParser(description='Pré-visualizar ou publicar triagem revista no Slack.')
    parser.add_argument('--check', action='store_true', help='Testar a identidade Slack sem publicar mensagens.')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--send', action='store_true', help='Publicar explicitamente no canal configurado.')
    parser.add_argument('--receipt', type=Path, default=Path('state/slack-receipts.json'))
    args = parser.parse_args(argv)
    if args.check:
        if args.send or args.report:
            raise AccessError('Use --check separadamente da publicação.')
        result = Slack(os.getenv('SLACK_BOT_TOKEN')).call('auth.test', {})
        print('Autenticação Slack confirmada; user_id=' + str(result.get('user_id')) + '; team_id=' + str(result.get('team_id')))
        return
    if not args.report:
        raise AccessError('Indique --report com o JSON de recomendações revistas.')
    text = render(read_json(args.report, {}))
    if not args.send:
        print(text)
        print('\nPré-visualização local: nenhuma mensagem enviada.')
        return
    client = Slack(os.getenv('SLACK_BOT_TOKEN'))
    client.call('auth.test', {})
    print(publish(client, os.getenv('SLACK_CHANNEL_ID'), text, args.receipt))


if __name__ == '__main__':
    try:
        main()
    except (AccessError, OSError, ValueError, KeyError) as error:
        print(str(error) if isinstance(error, AccessError) else 'Falha na leitura ou gravação local.', file=sys.stderr)
        sys.exit(1)
