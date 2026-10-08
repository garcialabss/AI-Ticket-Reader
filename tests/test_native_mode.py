import unittest
from unittest.mock import patch

from reader import AccessError
from slack_bot import main


class NativeModeTests(unittest.TestCase):
    def test_paid_api_receiver_disabled_by_default(self):
        with patch('slack_bot.create_socket_app', side_effect=AssertionError('Unexpected network startup')):
            with self.assertRaises(AccessError) as result:
                main([])
        self.assertIn('desativado', str(result.exception))
        self.assertIn('NATIVE_SLACK.md', str(result.exception))
