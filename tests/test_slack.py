import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock

from reader import AccessError
from slack_notify import publish, render


def example():
    return {'workspace': 'Tech-Support', 'reviewed': True, 'tickets': [{
        'id': 1, 'url': 'https://dnspt.freshservice.com/a/tickets/1',
        'summary': '<!channel> mensagem fictícia', 'group': 'DevOPS', 'subqueue': 'SIGA',
        'justification': 'Exemplo fictício', 'confidence': 'Baixa; exemplo',
        'suggested_reply': 'Pode esclarecer?', 'missing_information': 'Detalhes'}]}


class SlackTests(unittest.TestCase):
    def test_mentions_escaped(self):
        text = render(example())
        self.assertNotIn('<!channel>', text)
        self.assertIn('&lt;!channel&gt;', text)

    def test_unreviewed_report_rejected(self):
        report = example()
        report['reviewed'] = False
        with self.assertRaises(AccessError):
            render(report)

    def test_external_ticket_link_rejected(self):
        report = example()
        report['tickets'][0]['url'] = 'https://other.example/1'
        with self.assertRaises(AccessError):
            render(report)

    def test_success_not_repeated(self):
        client = Mock()
        client.call.return_value = {'ok': True, 'channel': 'C123', 'ts': '1.2'}
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / 'receipt.json'
            publish(client, 'C123', render(example()), receipt)
            publish(client, 'C123', render(example()), receipt)
            self.assertEqual(client.call.call_count, 1)
            payload = client.call.call_args.args[1]
            self.assertFalse(payload['unfurl_links'])
            self.assertFalse(payload['link_names'])

    def test_uncertain_submission_not_retried(self):
        client = Mock()
        client.call.side_effect = AccessError('Resultado incerto')
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / 'receipt.json'
            with self.assertRaises(AccessError):
                publish(client, 'C123', render(example()), receipt)
            with self.assertRaises(AccessError):
                publish(client, 'C123', render(example()), receipt)
            self.assertEqual(client.call.call_count, 1)
