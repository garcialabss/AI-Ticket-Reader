import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import urllib.request

from reader import AccessError, Freshservice, NoRedirect, collect, main, read_json, write_private


class FixtureClient:
    def __init__(self, outside=False):
        self.outside = outside
    def pages(self, path, key, **params):
        if path == 'workspaces':
            return [{'id': 13, 'name': 'Tech-Support', 'state': 'active', 'created_at': '2026-01-01T00:00:00Z'}]
        if path == 'groups':
            return [{'id': 1, 'workspace_id': 13}, {'id': 2, 'workspace_id': 2}]
        if path == 'tickets':
            return [{'id': 7, 'workspace_id': 2 if self.outside else 13, 'status': 2},
                    {'id': 8, 'workspace_id': 13, 'status': 5}]
        return [{'id': 10, 'body_text': 'Mensagem fictícia'}]
    def get(self, path, **params):
        if path == 'ticket_form_fields':
            return {'ticket_fields': [{'label': 'Sub-Fila', 'workspace_id': 13, 'name': 'componentes', 'choices': []}]}, ''
        return {'ticket': {'id': 7, 'workspace_id': 13, 'status': 2, 'subject': 'Fictício'}}, ''


class ReaderTests(unittest.TestCase):
    def test_scope_guard(self):
        with self.assertRaises(AccessError):
            collect(FixtureClient(outside=True), 'example.freshservice.com', 'Tech-Support', {})

    def test_reviewed_unchanged_excluded_changed_included(self):
        report = collect(FixtureClient(), 'example.freshservice.com', 'Tech-Support', {})
        self.assertEqual(len(report['tickets']), 1)
        self.assertEqual(len(report['groups']), 1)
        state = {'scope': report['scope'], 'reviewed': {'7': report['tickets'][0]['fingerprint']}}
        self.assertEqual(collect(FixtureClient(), 'example.freshservice.com', 'Tech-Support', state)['tickets'], [])
        state['reviewed']['7'] = 'old fingerprint'
        self.assertEqual(len(collect(FixtureClient(), 'example.freshservice.com', 'Tech-Support', state)['tickets']), 1)

    def test_pagination_follows_next(self):
        client = Freshservice('example.freshservice.com', 'fictional-key')
        with patch.object(client, 'get', side_effect=[({'tickets': [{'id': 1}]}, '<https://example.freshservice.com/api/v2/tickets?page=2>; rel="next"'), ({'tickets': [{'id': 2}]}, '')]):
            self.assertEqual([t['id'] for t in client.pages('tickets', 'tickets')], [1, 2])

    def test_authenticated_redirect_rejected(self):
        with self.assertRaises(AccessError):
            NoRedirect().redirect_request(urllib.request.Request('https://example.freshservice.com'), None, 302, '', {}, 'https://other.example')

    def test_acknowledgement_is_explicit_and_local(self):
        report = collect(FixtureClient(), 'example.freshservice.com', 'Tech-Support', {})
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'report.json'
            state = Path(directory) / 'state.json'
            write_private(output, report)
            self.assertFalse(state.exists())
            with patch.object(Freshservice, 'get', side_effect=AssertionError('Unexpected network call')):
                main(['--ack-report', str(output), '--state', str(state)])
            self.assertEqual(read_json(state, {})['reviewed']['7'], report['tickets'][0]['fingerprint'])

    def test_reject_other_tenant_state(self):
        with self.assertRaises(AccessError):
            collect(FixtureClient(), 'example.freshservice.com', 'Tech-Support', {'scope': {'domain': 'other.freshservice.com', 'workspace_id': 13}})


if __name__ == '__main__':
    unittest.main()
