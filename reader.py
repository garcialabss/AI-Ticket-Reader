"""Freshservice collector for Codex triage. Only GET requests are supported."""
import argparse
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


class AccessError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AccessError("Redirecionamento recusado para proteger a autenticação.")


class Freshservice:
    def __init__(self, domain, key):
        if not re.fullmatch(r"[a-zA-Z0-9-]+\.freshservice\.com", domain):
            raise AccessError("Use o hostname do tenant Freshservice, sem URL ou caminho.")
        if not key:
            raise AccessError("Falta FRESHSERVICE_API_KEY nas configurações seguras.")
        self.base = f"https://{domain}/api/v2/"
        self.auth = "Basic " + base64.b64encode((key + ":X").encode()).decode()
        self.opener = urllib.request.build_opener(NoRedirect)

    def get(self, path, **params):
        if not re.fullmatch(r"[a-z_]+(?:/\d+(?:/[a-z_]+)?)?", path):
            raise AccessError("Caminho de API inválido.")
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={
            "Accept": "application/json", "Authorization": self.auth}, method="GET")
        try:
            with self.opener.open(request, timeout=30) as response:
                return json.load(response), response.headers.get("Link", "")
        except urllib.error.HTTPError as error:
            if error.code == 429:
                raise AccessError("Limite da API atingido. Aguarde e repita a consulta; o estado não foi avançado.") from None
            raise AccessError(f"API HTTP {error.code}; verifique acesso, permissões e rede.") from None
        except urllib.error.URLError:
            raise AccessError("Ligação falhou; verifique a rede e o proxy do ambiente.") from None

    def pages(self, path, key, **params):
        results = []
        for page in range(1, 301):
            data, link = self.get(path, per_page=100, page=page, **params)
            if key not in data or not isinstance(data[key], list):
                raise AccessError(f"Resposta inesperada para {path}; consulta incompleta.")
            batch = data[key]
            results.extend(batch)
            if not re.search(r'rel=["\']?next', link) and len(batch) < 100:
                return results
        raise AccessError("Limite de paginação atingido; consulta incompleta.")


def read_json(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def write_private(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temp.replace(path)


def fingerprint(ticket, conversations):
    payload = json.dumps({"ticket": ticket, "conversations": conversations}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def collect(client, domain, workspace_name, state):
    workspaces = client.pages("workspaces", "workspaces")
    matches = [w for w in workspaces if w["name"] == workspace_name and w.get("state") == "active"]
    if len(matches) != 1:
        raise AccessError("Workspace ativo não encontrado de forma inequívoca.")
    workspace = matches[0]
    scope = {"domain": domain, "workspace_id": workspace["id"]}
    if state and state.get("scope") != scope:
        raise AccessError("O registo anterior pertence a outro tenant ou workspace.")
    groups = client.pages("groups", "groups", workspace_id=workspace["id"])
    groups = [g for g in groups if g.get("workspace_id") == workspace["id"]]
    field_data, _ = client.get("ticket_form_fields", workspace_id=workspace["id"])
    fields = field_data["ticket_fields"]
    subqueues = [f for f in fields if f.get("label") == "Sub-Fila" and f.get("workspace_id") == workspace["id"]]
    if len(subqueues) != 1:
        raise AccessError("Campo Sub-Fila não encontrado de forma inequívoca.")
    tickets = client.pages("tickets", "tickets", workspace_id=workspace["id"],
                           updated_since=workspace["created_at"], order_by="created_at", order_type="asc")
    if any(t.get("workspace_id") != workspace["id"] for t in tickets):
        raise AccessError("A listagem incluiu tickets de outro workspace.")
    selected = []
    for listed in tickets:
        if listed["status"] not in (2, 3, 6):
            continue
        data, _ = client.get(f"tickets/{listed['id']}")
        ticket = data["ticket"]
        if ticket.get("workspace_id") != workspace["id"]:
            raise AccessError("O ticket mudou de workspace; consulta interrompida.")
        if ticket["status"] not in (2, 3, 6):
            continue
        conversations = client.pages(f"tickets/{ticket['id']}/conversations", "conversations")
        digest = fingerprint(ticket, conversations)
        if state.get("reviewed", {}).get(str(ticket["id"])) == digest:
            continue
        selected.append({"id": ticket["id"], "url": f"https://{domain}/a/tickets/{ticket['id']}",
                         "fingerprint": digest, "ticket": ticket, "conversations": conversations})
    return {"scope": scope, "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "workspace": workspace, "groups": groups, "subqueue_field": subqueues[0],
            "category_fields": [f for f in fields if f.get("name") == "category"],
            "inventory_count": len(tickets), "tickets": selected,
            "limitations": ["Anexos e imagens não descarregados.",
                            "Registo de análise local, sem informação sobre análises feitas por terceiros."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Recolha de leitura para triagem pelo Codex; não classifica nem escreve no Freshservice.")
    parser.add_argument("--domain", default=os.getenv("FRESHSERVICE_DOMAIN", "dnspt.freshservice.com"))
    parser.add_argument("--workspace", default=os.getenv("FRESHSERVICE_WORKSPACE", "Tech-Support"))
    parser.add_argument("--output", type=Path, default=Path("data/pending.json"))
    parser.add_argument("--state", type=Path, default=Path("state/reviewed.json"))
    parser.add_argument("--ack-report", type=Path, help="Registar como apresentados os tickets de uma recolha já analisada; ação apenas local.")
    args = parser.parse_args(argv)
    state = read_json(args.state, {})
    if args.ack_report:
        report = read_json(args.ack_report, {})
        if not report.get("scope") or "tickets" not in report:
            raise AccessError("Ficheiro de recolha inválido.")
        if state and state.get("scope") != report["scope"]:
            raise AccessError("O registo e a recolha pertencem a âmbitos diferentes.")
        state.setdefault("scope", report["scope"])
        reviewed = state.setdefault("reviewed", {})
        for item in report["tickets"]:
            reviewed[str(item["id"])] = item["fingerprint"]
        write_private(args.state, state)
        print(f"Registo local atualizado: {len(report['tickets'])} tickets. Freshservice não alterado.")
        return
    client = Freshservice(args.domain, os.getenv("FRESHSERVICE_API_KEY"))
    report = collect(client, args.domain, args.workspace, state)
    write_private(args.output, report)
    print(f"Acesso confirmado. {report['inventory_count']} tickets inventariados; {len(report['tickets'])} para análise.")
    print(f"Recolha local: {args.output}. Nenhum ticket alterado; registo de análise não avançado.")


if __name__ == "__main__":
    try:
        main()
    except (AccessError, OSError, ValueError, KeyError) as error:
        if isinstance(error, AccessError):
            print(str(error), file=sys.stderr)
        else:
            print("Falha na leitura dos dados ou ficheiros; o registo não foi avançado.", file=sys.stderr)
        sys.exit(1)
