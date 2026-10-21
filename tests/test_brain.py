import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error

from ostrov.brain import BrainError, BrainLoop, DeepSeekClient, Settings, apply_actions, context
from ostrov.engine import Creature, World
from ostrov.storage import load, save


def result(kind='wait', **fields):
    return {'actions': [{'creature_id': 'rosmontis', 'type': kind, **fields}]}


class BrainTests(unittest.TestCase):
    def test_transport_contract_and_secret_not_in_body(self):
        reply = {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(result())}}]}
        with patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(reply).encode())) as request:
            self.assertEqual(DeepSeekClient().decide(Settings(api_key='test-secret'), context(World())), result())
        args, kwargs = request.call_args
        self.assertEqual(args[0].full_url, 'https://api.deepseek.com/chat/completions')
        payload = json.loads(args[0].data)
        self.assertEqual(payload['response_format'], {'type': 'json_object'})
        self.assertIn('JSON', payload['messages'][0]['content'])
        self.assertNotIn('test-secret', args[0].data.decode())
        self.assertEqual(kwargs['timeout'], 30)
        self.assertNotIn('test-secret', repr(Settings(api_key='test-secret')))

    def test_transport_errors_are_safe(self):
        errors = [urllib.error.HTTPError('https://api.deepseek.com', 401, 'secret', {}, None),
                  urllib.error.URLError('secret'), TimeoutError('secret')]
        for error in errors:
            with self.subTest(error=type(error)), patch('urllib.request.urlopen', side_effect=error):
                with self.assertRaises(BrainError) as caught:
                    DeepSeekClient().decide(Settings(api_key='secret'), {})
                self.assertNotIn('secret', str(caught.exception))
        for reply in [b'bad JSON', b'{}', json.dumps({'choices': [{'finish_reason': 'length'}]}).encode()]:
            with patch('urllib.request.urlopen', return_value=io.BytesIO(reply)):
                with self.assertRaises(BrainError):
                    DeepSeekClient().decide(Settings(api_key='secret'), {})

    def test_invalid_batches_are_atomic(self):
        world = World()
        world.add_creature(Creature('guest', 'Гость'))
        before = world.snapshot()
        for invalid in [result('move', dx=10, dy=0), result('move', dx=True, dy=0),
                        result('move', dx=float('nan'), dy=0), result('move', dx=10**400, dy=0),
                        result('kill'), result('wait', health=100),
                        {'actions': [result('move', dx=1, dy=0)['actions'][0], {'creature_id': 'guest', 'type': 'say', 'text': ''}]}]:
            with self.assertRaises(BrainError):
                apply_actions(world, invalid)
            self.assertEqual(world.snapshot(), before)

    def test_movement_speech_and_world_rules(self):
        world = World()
        world.add_creature(Creature('near', 'Рядом', 2, 0))
        world.add_creature(Creature('far', 'Далеко', 50, 0))
        apply_actions(world, {'actions': [result('say', text='Привет')['actions'][0],
                                       {'creature_id': 'near', 'type': 'move', 'dx': 1, 'dy': 0},
                                       {'creature_id': 'far', 'type': 'wait'}]})
        self.assertEqual(world.creatures['near'].x, 3)
        self.assertEqual(world.creatures['near'].memory, ['Росмонтис: Привет'])
        self.assertFalse(world.creatures['far'].memory)
        self.assertFalse(world.creatures['near'].knows_safe_zone)
        cliff = World()
        cliff.move('rosmontis', cliff.radius_at(0)-.1, 0)
        apply_actions(cliff, result('move', dx=2, dy=0))
        self.assertTrue(cliff.ended)
        self.assertEqual(cliff.creatures['rosmontis'].status, 'dead')

    def test_async_wait_freezes_time_and_error_pauses(self):
        started, release = threading.Event(), threading.Event()

        class Client:
            def decide(self, settings, observation):
                started.set()
                release.wait(2)
                raise BrainError('API недоступен')

        loop, world = BrainLoop(Client()), World()
        loop.configure(Settings('secret', interval=10, enabled=True))
        try:
            loop.step(world, 0, 0)
            self.assertTrue(started.wait(1))
            loop.step(world, 100, 100)
            self.assertTrue(loop.pending)
            self.assertEqual(world.time, 0)
        finally:
            release.set()
        response = loop.results.get(timeout=2)
        loop.results.put(response)
        loop.step(world, 101, 1)
        self.assertTrue(world.paused)
        self.assertEqual(world.time, 0)
        self.assertIn('API', loop.error)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'history.sqlite3'
            save(world, path)
            restored = load(path)
            self.assertEqual(restored.brain_history, world.brain_history)
            self.assertNotIn('secret', json.dumps(restored.snapshot()))

    def test_real_interval_stale_response_and_pause(self):
        loop, world = BrainLoop(), World()
        loop.configure(Settings('secret', interval=10, enabled=True))
        loop.pending = True
        loop.observation = context(world)
        world.paused = True
        loop.results.put((loop.epoch, result('move', dx=1, dy=0), None))
        loop.step(world, 1, 1)
        self.assertEqual(world.creatures['rosmontis'].x, 0)
        world.paused = False
        loop.step(world, 2, 1)
        self.assertEqual(world.creatures['rosmontis'].x, 1)
        self.assertEqual(world.time, 0)
        world.speed = 100
        loop.step(world, 3, 1)
        self.assertEqual(world.time, 100)
        self.assertFalse(loop.pending)
        previous_epoch = loop.epoch
        loop.reset()
        loop.settings = Settings(enabled=False)
        loop.results.put((previous_epoch, result('move', dx=1, dy=0), None))
        loop.step(world, 4, 0)
        self.assertEqual(world.creatures['rosmontis'].x, 1)

    def test_settings_require_key_and_valid_interval(self):
        for settings in [Settings(enabled=True), Settings(interval=float('nan')), Settings(interval=0), Settings(model='bad')]:
            with self.assertRaises(ValueError):
                settings.validate()


if __name__ == '__main__':
    unittest.main()
