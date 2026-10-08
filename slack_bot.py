"""Authorized /triagem commands over Slack Socket Mode."""
import json
import argparse
import hashlib
import logging
import os
from pathlib import Path
import re
import threading

from reader import AccessError, Freshservice, collect, read_json, write_private
from slack_notify import Slack, publish, render
from triage_ai import analyze


ROOT = Path(__file__).parent
STATE = ROOT / 'state'


def allowed(command, team, channel, users):
    return (command.get('team_id') == team and command.get('channel_id') == channel
            and command.get('user_id') in users)


def historical_examples(client, collection):
    workspace = collection['workspace']
    inventory = client.pages('tickets', 'tickets', workspace_id=workspace['id'],
                             updated_since=workspace['created_at'], order_by='created_at', order_type='desc')
    wanted = {t['ticket'].get('custom_fields', {}).get('componentes') for t in collection['tickets']}
    chosen, seen = [], set()
    for ticket in inventory:
        subqueue = ticket.get('custom_fields', {}).get('componentes')
        if ticket.get('workspace_id') != workspace['id']:
            raise AccessError('Exemplo fora do workspace; análise interrompida.')
        if ticket['status'] not in (4, 5) or subqueue not in wanted or subqueue in seen:
            continue
        data, _ = client.get(f"tickets/{ticket['id']}")
        if data['ticket'].get('workspace_id') != workspace['id']:
            raise AccessError('Exemplo mudou de workspace.')
        conversations = client.pages(f"tickets/{ticket['id']}/conversations", 'conversations')
        chosen.append({'ticket': data['ticket'], 'conversations': conversations})
        seen.add(subqueue)
        if len(chosen) == 4:
            break
    return chosen


def run_job(slack, channel, client, model_key):
    state_path = STATE / 'slack-reviewed.json'
    pending_path = STATE / 'slack-pending.json'
    pending = read_json(pending_path, {})
    if pending:
        if pending.get('channel') != channel:
            raise AccessError('Existe uma publicação pendente para outro canal; não reenviada.')
    else:
        previous = read_json(state_path, {})
        collection = collect(client, 'dnspt.freshservice.com', 'Tech-Support', previous)
        if not collection['tickets']:
            return {'analyzed': 0, 'scope': collection['scope']}
        examples = historical_examples(client, collection)
        recommendations = analyze(collection, examples, key=model_key)
        # Prepare all messages before sending any; retain exact content across partial failures.
        messages = [render({'workspace': 'Tech-Support', 'reviewed': True, 'tickets': [r]}) for r in recommendations]
        state = {'scope': collection['scope'], 'reviewed': dict(previous.get('reviewed', {}))}
        for ticket in collection['tickets']:
            state['reviewed'][str(ticket['id'])] = ticket['fingerprint']
        pending = {'channel': channel, 'messages': messages, 'state': state,
                   'analyzed': len(recommendations)}
        write_private(pending_path, pending)
    for message in pending['messages']:
        publish(slack, channel, message, STATE / 'slack-receipts.json')
    write_private(state_path, pending['state'])
    pending_path.unlink()
    return {'analyzed': pending['analyzed'], 'scope': pending['state']['scope']}


def create_socket_app(token):
    from slack_bolt import App
    # Socket Mode authenticates the WebSocket with the app token and TLS.
    # HTTP request signatures do not apply (the SDK skips them for socket_mode).
    app = App(token=token, request_verification_enabled=False)

    @app.middleware
    def socket_only(req, resp, next):
        if req.mode != 'socket_mode':
            resp.status = 403
            resp.body = 'HTTP ingress is not supported.'
            return resp
        return next()

    return app


def main(argv=None):
    parser = argparse.ArgumentParser(description='Modo opcional com API de IA faturada separadamente.')
    parser.add_argument('--enable-api-mode', action='store_true')
    args = parser.parse_args(argv)
    if not args.enable_api_mode:
        raise AccessError('O bot /triagem com API adicional está desativado. Use @ChatGPT com delegação Codex Cloud; consulte NATIVE_SLACK.md. Reativação exige autorização e --enable-api-mode.')
    from slack_bolt.adapter.socket_mode.websocket_client import SocketModeHandler

    # SDK transport exceptions can contain signed connection URLs; keep logs sanitized.
    logging.disable(logging.CRITICAL)
    required = ['SLACK_BOT_TOKEN', 'SLACK_APP_TOKEN', 'SLACK_CHANNEL_ID',
                'SLACK_ALLOWED_USER_IDS', 'FRESHSERVICE_API_KEY', 'TRIAGE_MODEL_API_KEY']
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise AccessError('Configuração em falta: ' + ', '.join(missing))
    channel = os.environ['SLACK_CHANNEL_ID']
    users = {user.strip() for user in os.environ['SLACK_ALLOWED_USER_IDS'].split(',')}
    if not re.fullmatch(r'[CG][A-Z0-9]+', channel) or any(not re.fullmatch(r'U[A-Z0-9]+', u) for u in users):
        raise AccessError('IDs do canal ou dos utilizadores inválidos.')
    slack = Slack(os.environ['SLACK_BOT_TOKEN'])
    identity = slack.call('auth.test', {})
    team = identity['team_id']
    app = create_socket_app(os.environ['SLACK_BOT_TOKEN'])
    lock = threading.Lock()

    def worker(command, job_id):
        path = STATE / 'slack-jobs.json'
        try:
            client = Freshservice('dnspt.freshservice.com', os.environ['FRESHSERVICE_API_KEY'])
            result = run_job(slack, channel, client, os.environ['TRIAGE_MODEL_API_KEY'])
            if not result['analyzed']:
                # Request-specific receipt permits one response per distinct empty request.
                publish(slack, channel, 'Nenhum ticket por resolver novo ou alterado desde a última análise Slack.\nPedido: ' + hashlib.sha256(job_id.encode()).hexdigest()[:12],
                        STATE / 'slack-receipts.json')
            else:
                publish(slack, channel,
                        f"Triagem concluída: {result['analyzed']} tickets analisados.\n"
                        'Factos verificados: workspace Tech-Support, opções reais e conteúdo disponível na API.\n'
                        'Recomendações: resultados de IA; a equipa deve rever justificações e incertezas.\n'
                        'Ações executadas: consultas e publicação no Slack; nenhum ticket Freshservice alterado.\n'
                        'Verificações pendentes: anexos/imagens não consultados e informação em falta indicada em cada ticket.\n'
                        'Pedido: ' + hashlib.sha256(job_id.encode()).hexdigest()[:12],
                        STATE / 'slack-receipts.json')
            jobs = read_json(path, {})
            jobs[job_id] = {'status': 'completed', 'analyzed': result['analyzed']}
            write_private(path, jobs)
        except Exception as error:
            # Never log raw API payloads, model inputs, commands, credentials or response URLs.
            try:
                detail = str(error) if isinstance(error, AccessError) else 'Verifique a configuração e os recibos locais antes de repetir.'
                jobs = read_json(path, {})
                jobs[job_id] = {'status': 'failed', 'error': detail}
                write_private(path, jobs)
                publish(slack, channel, 'A triagem não foi concluída. ' + detail + '\n'
                        'Nenhum ticket Freshservice foi alterado.\nPedido: ' + hashlib.sha256(job_id.encode()).hexdigest()[:12],
                        STATE / 'slack-receipts.json')
            except Exception:
                pass
            print(str(error) if isinstance(error, AccessError) else 'Triagem incompleta; consulte recibos locais. Não repetir automaticamente.', flush=True)
        finally:
            lock.release()

    @app.command('/triagem')
    def triage(ack, command):
        if not allowed(command, team, channel, users):
            ack('Este utilizador ou canal não está autorizado para a triagem.')
            return
        if command.get('text', '').strip() not in ('', 'agora', 'ajuda'):
            ack('Use /triagem ou /triagem ajuda. Não são aceites instruções livres.')
            return
        if command.get('text', '').strip() == 'ajuda':
            ack('Use /triagem para analisar tickets por resolver novos ou alterados do Tech-Support e publicar recomendações neste canal. Freshservice apenas em leitura. As mensagens podem notificar membros.')
            return
        if not lock.acquire(blocking=False):
            ack('Já existe uma triagem em curso; aguarde a conclusão.')
            return
        try:
            job_id = command.get('trigger_id')
            if not job_id or not re.fullmatch(r'[A-Za-z0-9._-]+', job_id):
                ack('Pedido sem identificador válido; não executado.')
                lock.release()
                return
            path = STATE / 'slack-jobs.json'
            jobs = read_json(path, {})
            if job_id in jobs:
                ack('Pedido já recebido; não será repetido. Verifique o resultado no canal.')
                lock.release()
                return
            jobs[job_id] = {'status': 'running'}
            write_private(path, jobs)
            ack('Pedido aceite. Vou consultar os tickets e publicar recomendações neste canal, sem alterar o Freshservice.')
            threading.Thread(target=worker, args=(command, job_id), daemon=True).start()
        except Exception:
            lock.release()
            ack('Não foi possível registar o pedido; não executado.')

    handler = SocketModeHandler(app, os.environ['SLACK_APP_TOKEN'])
    ready = threading.Event()

    def hello(ws, message):
        try:
            if json.loads(message).get('type') == 'hello':
                ready.set()
        except (ValueError, AttributeError):
            pass

    handler.client.on_message_listeners.append(hello)
    handler.connect()
    if not ready.wait(timeout=30):
        handler.close()
        raise AccessError('Socket Mode sem confirmação de ligação; verifique rede e permissões.')
    print('Socket Mode ligado: evento hello recebido. Pronto para /triagem ajuda.', flush=True)
    try:
        threading.Event().wait()
    finally:
        handler.close()


if __name__ == '__main__':
    try:
        main()
    except AccessError as error:
        print(str(error))
        raise SystemExit(1)
    except Exception:
        print('Recetor não iniciado. Verifique permissões, rede e configuração segura.')
        raise SystemExit(1)
