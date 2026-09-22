"""V3 evidence isolation and execution behavior."""
import json
import unittest
from unittest.mock import patch

from minesweeper import context_lab, server
from minesweeper.game import MinesweeperGame, parse_cell_label
from minesweeper.agents import ProviderError, jev_context_choose


class ContextLabTests(unittest.TestCase):
    def game(self):
        game = MinesweeperGame(30, 16, 99, 1)
        game.reveal(*game.opening_cell())
        return game

    def test_unguided_modes_do_not_call_solver_or_risk_ranker(self):
        game = self.game()
        with patch.object(game, 'deduce', side_effect=AssertionError('solver used')), patch.object(game, 'risk_score', side_effect=AssertionError('risk used')):
            raw = context_lab.request_for(game, 'clues', 'jev-1.13.0')
            equations = context_lab.request_for(game, 'equations', 'jev-1.13.0')
            context_lab.public_board(game, 20)
        self.assertNotIn('code_guidance', raw['state'])
        self.assertNotIn('code_guidance', equations['state'])
        self.assertEqual(raw['questions'], equations['questions'])
        without_equations = dict(equations['state'])
        without_equations.pop('equations')
        self.assertEqual(raw['state'], without_equations)

    def test_llm_receives_only_public_board_without_frontier_or_equations(self):
        game = self.game()
        with patch.object(game, 'frontier_hidden', side_effect=AssertionError('frontier used')):
            state = context_lab.build_input(game, 'llm')
        self.assertEqual(set(state), {'game', 'board', 'proposal_limit'})
        for r, row in enumerate(state['board']['rows']):
            for c, token in enumerate(row):
                self.assertEqual(token, str(game.adjacent_mines(r, c)) if (r, c) in game.revealed else '?')

    def test_equations_are_only_restatements_of_revealed_clues(self):
        game = self.game()
        state = context_lab.build_input(game, 'equations')
        for equation in state['equations']:
            cell = parse_cell_label(equation['clue'])
            self.assertIn(cell, game.revealed)
            expected = {n for n in game.neighbors(*cell) if n not in game.revealed}
            self.assertEqual({parse_cell_label(c) for c in equation['cells']}, expected)
            self.assertEqual(equation['mines'], game.adjacent_mines(*cell))
        self.assertNotIn('mine_cells', json.dumps(state))

    def test_bounded_context_reports_truncation(self):
        with patch.object(context_lab, 'MAX_CLUES', 1):
            state = context_lab.build_input(self.game(), 'equations')
        self.assertEqual(len(state['equations']), 1)
        self.assertTrue(state['context']['expansion_truncated'])

    def test_adapter_sends_exact_request_without_injecting_guidance(self):
        request = context_lab.request_for(self.game(), 'clues', 'jev-1.13.0')
        cell = next(iter(request['questions']['cell']['criteria']))
        with patch('minesweeper.agents._http_json', return_value={'answers': {'cell': {'choice': cell}}}) as http:
            jev_context_choose(request, 'test-key')
        self.assertEqual(http.call_args.args[1], request)
        with patch('minesweeper.agents._http_json', return_value={'answers': None}):
            with self.assertRaises(ProviderError):
                jev_context_choose(request, 'test-key')

    def test_provider_failure_and_invalid_choice_do_not_make_fallback_moves(self):
        for result in [ProviderError('test_failure'), ('r999c999', {})]:
            comparison = server.Comparison(server._default_v2_html_path())
            config = server._validate_start({'left_engine': 'none', 'right_engine': 'jev', 'context_mode': 'clues', 'width': 9, 'height': 9, 'mines': 10, 'seed': 1})
            options = {'side_effect': result} if isinstance(result, Exception) else {'return_value': result}
            with patch('minesweeper.server.jev_key', return_value='test-key'), patch('minesweeper.server.jev_context_choose', **options):
                comparison.start(config)
                for worker in comparison.threads:
                    worker.join(timeout=2)
                side = comparison.sides['right']
                self.assertEqual(side.game.moves, 1)
                self.assertEqual(side.status, 'ended')
                self.assertFalse(side.decisions)
                self.assertTrue(any(e['kind'] == 'decision_failed' for e in side.events))
                self.assertNotIn('Authorization', json.dumps(side.input_request))
                comparison.stop()

    def test_invalid_context_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            server._validate_start({'context_mode': 'unknown'})

    def test_v3_http_routes_use_an_independent_session_and_default_to_clues(self):
        import threading
        import urllib.request
        from http.server import ThreadingHTTPServer
        legacy = server.Comparison(server._default_v2_html_path())
        lab = server.Comparison(server._default_v2_html_path())
        handler = type('TestHandler', (server.Handler,), {'comparison': legacy, 'v3_comparison': lab,
                       'log_message': lambda *args: None})
        http = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        worker = threading.Thread(target=http.serve_forever, daemon=True)
        worker.start()
        base = f'http://127.0.0.1:{http.server_port}'
        try:
            with urllib.request.urlopen(base + '/v3/') as response:
                self.assertIn(b'contextMode', response.read())
            body = {'left_engine': 'none', 'right_engine': 'jev', 'seed': 1}
            with patch.object(server.Comparison, '_run_side'):
                for route in ['/v3/start', '/start']:
                    request = urllib.request.Request(base + route, data=json.dumps(body).encode(), headers={'Content-Type':'application/json'})
                    with urllib.request.urlopen(request) as response:
                        self.assertEqual(response.status, 200)
            from urllib.error import HTTPError
            invalid = urllib.request.Request(base + '/v3/start', data=b'{"context_mode":null}', headers={'Content-Type':'application/json'})
            with self.assertRaises(HTTPError) as failure:
                urllib.request.urlopen(invalid)
            self.assertEqual(failure.exception.code, 400)
            self.assertEqual(lab.config['context_mode'], 'clues')
            self.assertIsNone(legacy.config['context_mode'])
            self.assertIsNot(lab.sides['right'].game, legacy.sides['right'].game)
        finally:
            legacy.stop(); lab.stop(); http.shutdown(); http.server_close(); worker.join(timeout=2)

    def test_expired_response_is_not_applied(self):
        comparison = server.Comparison(server._default_v2_html_path())
        config = server._validate_start({'left_engine': 'none', 'right_engine': 'jev', 'context_mode': 'clues', 'width': 9, 'height': 9, 'mines': 10, 'seed': 1})
        real_clock = server.now_ms
        offset = [0]
        def expired(request, key, timeout):
            offset[0] = (config['duration_seconds'] + 1) * 1000
            return next(iter(request['questions']['cell']['criteria'])), {}
        with patch('minesweeper.server.now_ms', side_effect=lambda: real_clock() + offset[0]), patch('minesweeper.server.jev_key', return_value='test-key'), patch('minesweeper.server.jev_context_choose', side_effect=expired):
            comparison.start(config)
            for worker in comparison.threads:
                worker.join(timeout=2)
        self.assertEqual(comparison.sides['right'].game.moves, 1)
        self.assertEqual(comparison.sides['right'].status, 'time_limit')
        comparison.stop()


    def test_jev_receives_exactly_the_llm_proposals(self):
        comparison = server.Comparison(server._default_v2_html_path())
        config = server._validate_start({'left_engine': 'none', 'right_engine': 'jev', 'context_mode': 'llm', 'seed': 1})
        comparison.config = config
        comparison.timer = {'deadline_at_ms': server.now_ms() + 10000}
        side = comparison.sides['right']
        game = self.game()
        label = next(context_lab.cell_label(r,c) for r in range(game.height) for c in range(game.width) if (r,c) not in game.revealed)
        advice = {'model': config['model'], 'proposals': [{'cell': label, 'rationale': 'A test proposal.'}]}
        with patch.object(game, 'deduce', side_effect=AssertionError('solver used')), patch.object(game, 'risk_score', side_effect=AssertionError('risk used')), patch('minesweeper.server.jev_key', return_value='key'), patch('minesweeper.server.openrouter_key', return_value='key'), patch('minesweeper.server.llm_context_guidance', return_value=advice) as llm, patch('minesweeper.server.jev_context_choose', return_value=('r1c1', {})) as jev:
            result = comparison._decide(side, game, config, 1)
        self.assertIsNone(result[2])
        self.assertEqual(side.input_request['state']['llm_guidance'], advice)
        self.assertEqual(list(side.input_request['questions']['cell']['criteria']), [label])
        self.assertEqual(llm.call_args.args[0], context_lab.public_board(game, 20))
        self.assertNotIn('equations', side.input_request['state'])
        self.assertEqual(jev.call_args.args[0], side.input_request)

    def test_failed_or_expired_llm_never_calls_jev(self):
        for failure in [True, False]:
            comparison = server.Comparison(server._default_v2_html_path())
            config = server._validate_start({'left_engine': 'none', 'right_engine': 'jev', 'context_mode': 'llm', 'seed': 1})
            comparison.timer = {'deadline_at_ms': server.now_ms() + 10000}
            def guide(*args):
                if failure:
                    raise ProviderError('llm_failed')
                comparison.timer['deadline_at_ms'] = server.now_ms() - 1
                label = next(context_lab.cell_label(r,c) for r,row in enumerate(args[0]['board']['rows']) for c,token in enumerate(row) if token == '?')
                return {'proposals': [{'cell': label, 'rationale': 'late'}]}
            with patch('minesweeper.server.jev_key', return_value='key'), patch('minesweeper.server.openrouter_key', return_value='key'), patch('minesweeper.server.llm_context_guidance', side_effect=guide), patch('minesweeper.server.jev_context_choose') as jev:
                result = comparison._decide(comparison.sides['right'], self.game(), config, 1)
            self.assertEqual(result[2], 'llm_failed' if failure else 'decision_expired')
            jev.assert_not_called()

    def test_guidance_adapter_sends_public_state_and_rejects_empty_advice(self):
        from minesweeper.agents import llm_context_guidance
        state = context_lab.build_input(self.game(), 'llm')
        with patch('minesweeper.agents._http_json', return_value={'choices': [{'message': {'content': json.dumps({'proposals': [{'cell': 'r1c1', 'rationale': 'guess'}]})}}]}) as http:
            advice = llm_context_guidance(state, 'test/model', 'key', 3)
        self.assertEqual(advice['proposals'][0]['cell'], 'r1c1')
        self.assertEqual(json.loads(http.call_args.args[1]['messages'][1]['content']), state)
        self.assertEqual(http.call_args.args[3], 3)
        with patch('minesweeper.agents._http_json', return_value={'choices': []}):
            with self.assertRaises(ProviderError):
                llm_context_guidance(state, 'test/model', 'key', 3)


    def test_invalid_proposals_rejected_without_repair(self):
        game = self.game()
        evidence = context_lab.public_board(game, 4)
        legal = next(context_lab.cell_label(r,c) for r in range(game.height) for c in range(game.width) if (r,c) not in game.revealed)
        item = {'cell': legal, 'rationale': 'guess'}
        revealed = context_lab.cell_label(*next(iter(game.revealed)))
        for proposals in [[], [item, item], [item] * 5, [{'cell': revealed, 'rationale': 'bad'}], [{'cell': 'r999c999', 'rationale': 'bad'}], [{'cell': legal}], [None]]:
            with self.assertRaises(ValueError):
                context_lab.proposal_request(game, evidence, {'proposals': proposals}, 'jev')

    def test_runner_uses_llm_proposals_without_code_selection(self):
        comparison = server.Comparison(server._default_v2_html_path())
        config = server._validate_start({'left_engine': 'none', 'right_engine': 'jev', 'context_mode': 'llm', 'width': 9, 'height': 9, 'mines': 10, 'seed': 1})
        def propose(state, *args):
            for r, row in enumerate(state['board']['rows']):
                for c, token in enumerate(row):
                    if token == '?':
                        return {'proposals': [{'cell': context_lab.cell_label(r,c), 'rationale': 'test'}]}
        def choose(request, *args):
            comparison.sides['right'].paused = True
            return next(iter(request['questions']['cell']['criteria'])), {}
        with patch('minesweeper.context_lab.neutral_candidates', side_effect=AssertionError('code candidates used')), patch('minesweeper.server.jev_key', return_value='key'), patch('minesweeper.server.openrouter_key', return_value='key'), patch('minesweeper.server.llm_context_guidance', side_effect=propose), patch('minesweeper.server.jev_context_choose', side_effect=choose):
            comparison.start(config)
            import time
            deadline = time.monotonic() + 2
            while not comparison.sides['right'].decisions and time.monotonic() < deadline:
                time.sleep(.01)
            comparison.stop()
            for worker in comparison.threads:
                worker.join(timeout=2)
        self.assertEqual(len(comparison.sides['right'].decisions), 1)
        self.assertFalse(comparison.sides['right'].decisions[0]['fallback'])


    def test_system_two_has_reasoning_budget_bounded_by_game_deadline(self):
        from minesweeper.agents import llm_context_guidance
        response = {'choices': [{'message': {'content': '{"proposals":[{"cell":"r1c1","rationale":"guess"}]}'}}]}
        for remaining, expected in [(300, 120), (12, 12)]:
            with patch('minesweeper.agents._http_json', return_value=response) as http:
                llm_context_guidance({}, 'model', 'key', remaining)
            self.assertEqual(http.call_args.args[3], expected)


    def test_system_two_timeout_is_identified_and_does_not_call_jev(self):
        comparison = server.Comparison(server._default_v2_html_path())
        config = server._validate_start({'left_engine': 'none', 'right_engine': 'jev', 'context_mode': 'llm', 'seed': 22})
        comparison.timer = {'deadline_at_ms': server.now_ms() + 300000}
        side = comparison.sides['right']
        def timeout(*args):
            self.assertEqual(comparison._side_snapshot(side)['decision_stage'], 'system_2')
            raise ProviderError('provider_request_timeout')
        with patch('minesweeper.server.jev_key', return_value='key'), patch('minesweeper.server.openrouter_key', return_value='key'), patch('minesweeper.server.llm_context_guidance', side_effect=timeout), patch('minesweeper.server.jev_context_choose') as jev:
            result = comparison._decide(side, self.game(), config, 1)
        self.assertEqual(result[2], 'system_2_timeout')
        jev.assert_not_called()
