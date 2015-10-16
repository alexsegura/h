# -*- coding: utf-8 -*-
"""Defines unit tests for h.streamer."""

import unittest

from collections import namedtuple
import json

import pytest
from mock import ANY
from mock import MagicMock, Mock
from mock import patch
from pyramid.testing import DummyRequest

from h import streamer
from h.streamer import FilterToElasticFilter
from h.streamer import WebSocket
from h.streamer import should_send_annotation_event
from h.streamer import websocket
from h.streamer import ANNOTATIONS_TOPIC


FakeMessage = namedtuple('FakeMessage', 'body')


class FakeSocket(object):
    client_id = None
    filter = None
    request = None
    terminated = None

    def __init__(self, client_id):
        self.client_id = client_id
        self.terminated = False
        self.filter = MagicMock()
        self.request = MagicMock()
        self.send = MagicMock()


def has_ordered_sublist(lst, sublist):
    """
    Determines whether the passed list contains, in the specified order, all
    the elements in sublist.
    """
    sub_idx = 0
    max_idx = len(sublist) - 1
    for x in lst:
        if x == sublist[sub_idx]:
            sub_idx += 1
        if sub_idx > max_idx:
            return True
    return sub_idx > max_idx


class ObjectIncluding(object):
    def __init__(self, include):
        self.include = include

    def __eq__(self, other):
        try:
            for k, v in self.include.items():
                if other[k] != v:
                    return False
        except (KeyError, TypeError):
            return False
        else:
            return True


# Tests for the FilterToElasticFilter class
# this class needs a python request, and a filter json object as the input
def test_zero_clauses():
    """No condition is given so a match_all query should be generated
    """
    request = DummyRequest()
    filter_json = {
        'clauses': [],
    }

    fef = FilterToElasticFilter(filter_json, request)
    assert fef.query['query']['filtered']['query'] == {"match_all": {}}


def test_policy_include_any():
    request = DummyRequest()
    filter_json = {
        'match_policy': 'include_any',
        'clauses': [{
            'field': 'text',
            'operator': 'equals',
            'value': 'foo',
            'options': {}
        }, {
            'field': 'tag',
            'operator': 'equals',
            'value': 'bar',
            'options': {}
        }],
    }

    fef = FilterToElasticFilter(filter_json, request)
    assert 'should' in fef.query['query']['filtered']['query']['bool']


def test_policy_include_all():
    request = DummyRequest()
    filter_json = {
        'match_policy': 'include_all',
        'clauses': [{
            'field': 'text',
            'operator': 'equals',
            'value': 'foo',
            'options': {}
        }, {
            'field': 'tag',
            'operator': 'equals',
            'value': 'bar',
            'options': {}
        }],
    }

    fef = FilterToElasticFilter(filter_json, request)
    assert 'must' in fef.query['query']['filtered']['query']['bool']


def test_policy_exclude_any():
    request = DummyRequest()
    filter_json = {
        'match_policy': 'exclude_any',
        'clauses': [{
            'field': 'text',
            'operator': 'equals',
            'value': 'foo',
            'options': {}
        }, {
            'field': 'tag',
            'operator': 'equals',
            'value': 'bar',
            'options': {}
        }],
    }

    fef = FilterToElasticFilter(filter_json, request)
    assert 'must_not' in fef.query['query']['filtered']['query']['bool']


def test_policy_exclude_all():
    request = DummyRequest()
    filter_json = {
        'match_policy': 'exclude_all',
        'clauses': [{
            'field': 'text',
            'operator': 'equals',
            'value': 'foo',
            'options': {}
        }, {
            'field': 'tag',
            'operator': 'equals',
            'value': 'bar',
            'options': {}
        }],
    }

    fef = FilterToElasticFilter(filter_json, request)
    assert 'must' in (
        fef.query['query']['filtered']['query']['bool']['must_not']['bool'])


def test_operator_call():
    request = DummyRequest()

    filter_json = {
        'match_policy': 'include_all',
        'clauses': [{
            'field': '/text',
            'operator': 'equals',
            'value': 'foo bar',
            'options': {
                'es': {
                    'query_type': 'simple'
                }
            }
        }],
    }

    generated = FilterToElasticFilter(filter_json, request)
    query = generated.query['query']['filtered']['query']['bool']['must'][0]
    expected = 'foo bar'

    assert query['term']['text'] == expected


def test_websocket_bad_origin(config):
    config.registry.settings.update({'origins': 'http://good'})
    config.include('h.streamer')
    req = DummyRequest(headers={'Origin': 'http://bad'})
    res = websocket(req)
    assert res.code == 403


def test_websocket_good_origin(config):
    config.registry.settings.update({'origins': 'http://good'})
    config.include('h.streamer')
    req = DummyRequest(headers={'Origin': 'http://good'})
    req.get_response = MagicMock()
    res = websocket(req)
    assert res.code != 403


def test_websocket_same_origin(config):
    config.include('h.streamer')
    # example.com is the dummy request default host URL
    req = DummyRequest(headers={'Origin': 'http://example.com'})
    req.get_response = MagicMock()
    res = websocket(req)
    assert res.code != 403


class TestWebSocket(unittest.TestCase):
    def setUp(self):
        fake_request = MagicMock()
        fake_socket = MagicMock()

        self.s = WebSocket(fake_socket)
        self.s.request = fake_request

    def test_filter_message_with_uri_gets_expanded(self):
        filter_message = json.dumps({
            'filter': {
                'actions': {},
                'match_policy': 'include_all',
                'clauses': [{
                    'field': '/uri',
                    'operator': 'equals',
                    'value': 'http://example.com',
                }],
            }
        })

        with patch('h.api.uri.expand') as expand:
            expand.return_value = ['http://example.com',
                                   'http://example.com/alter',
                                   'http://example.com/print']
            msg = MagicMock()
            msg.data = filter_message

            self.s.received_message(msg)

            uri_filter = self.s.filter.filter['clauses'][0]
            uri_values = uri_filter['value']
            assert len(uri_values) == 3
            assert 'http://example.com' in uri_values
            assert 'http://example.com/alter' in uri_values
            assert 'http://example.com/print' in uri_values


class TestBroadcastAnnotationEvent(unittest.TestCase):
    def setUp(self):
        self.message = {
            'annotation': {'id': 1},
            'action': 'delete',
            'src_client_id': 'pigeon',
        }

        self.should_patcher = patch('h.streamer.should_send_annotation_event')
        self.should = self.should_patcher.start()

    def tearDown(self):
        self.should_patcher.stop()

    def test_send_when_socket_should_receive_event(self):
        self.should.return_value = True
        sock = FakeSocket('giraffe')
        streamer.broadcast_annotation_message(self.message, [sock])
        assert sock.send.called

    def test_no_send_when_socket_should_not_receive_event(self):
        self.should.return_value = False
        sock = FakeSocket('pigeon')
        streamer.broadcast_annotation_message(self.message, [sock])
        assert sock.send.called is False

    def test_terminated_socket_does_not_receive_event(self):
        self.should.return_value = True
        sock = FakeSocket('giraffe')
        sock.terminated = True
        streamer.broadcast_annotation_message(self.message, [sock])
        assert sock.send.called is False


class TestBroadcastSessionChangeEvent(unittest.TestCase):
    def test_should_send_session_change_when_joining_or_leaving_group(self):
        session_model_patcher = patch('h.session.model')
        session_model = session_model_patcher.start()
        session_model.return_value = {'groups': [{'id': 'someid'}]}

        message = {
            'type': 'group-join',
            'userid': 'amy',
            'group': 'groupid',
        }

        sock = FakeSocket('clientid')
        sock.request.authenticated_userid = 'amy'

        streamer.broadcast_session_change_message(message, [sock])
        sock.send.assert_called_with(json.dumps({
            'type': 'session-change',
            'action': 'group-join',
            'model': session_model.return_value,
        }))

        session_model_patcher.stop()


class TestShouldSendEvent(unittest.TestCase):
    def setUp(self):
        self.sock_giraffe = FakeSocket('giraffe')
        self.sock_giraffe.filter.match.return_value = True

        self.sock_pigeon = FakeSocket('pigeon')

        self.sock_roadkill = FakeSocket('roadkill')
        self.sock_roadkill.terminated = True

    def test_non_sending_socket_receives_event(self):
        data = {'action': 'update', 'src_client_id': 'pigeon'}
        assert should_send_annotation_event(
            self.sock_giraffe,
            {'permissions': {'read': ['group:__world__']}},
            data)

    def test_sending_socket_does_not_receive_event(self):
        data = {'action': 'update', 'src_client_id': 'pigeon'}
        assert should_send_annotation_event(self.sock_pigeon, {}, data) is False


    def test_should_send_annotation_event_no_filter(self):
        self.sock_giraffe.filter = None
        data = {'action': 'update', 'src_client_id': 'pigeon'}
        assert should_send_annotation_event(
            self.sock_giraffe,
            {'permissions': {'read': ['group:__world__']}},
            data) is False

    def test_should_send_annotation_event_doesnt_send_reads(self):
        data = {'action': 'read', 'src_client_id': 'pigeon'}
        assert should_send_annotation_event(self.sock_giraffe, {}, data) is False

    def test_should_send_annotation_event_filtered(self):
        self.sock_pigeon.filter.match.return_value = False
        data = {'action': 'update', 'src_client_id': 'giraffe'}
        assert should_send_annotation_event(
            self.sock_pigeon,
            {'permissions': {'read': ['group:__world__']}},
            data) is False

    def test_should_send_annotation_event_does_not_send_nipsad_annotations(self):
        """Users should not see annotations from NIPSA'd users."""
        annotation = {'user': 'fred', 'nipsa': True}
        socket = Mock(terminated=False, client_id='foo')
        event_data = {'action': 'create', 'src_client_id': 'bar'}

        assert not should_send_annotation_event(socket, annotation, event_data)

    def test_should_send_annotation_event_does_send_nipsad_annotations(self):
        """NIPSA'd users should see their own annotations."""
        annotation = {'user': 'fred', 'nipsa': True}
        socket = Mock(terminated=False, client_id='foo')
        socket.request.authenticated_userid = 'fred'  # The annotation creator.
        event_data = {'action': 'create', 'src_client_id': 'bar'}

        assert should_send_annotation_event(socket, annotation, event_data)

    def test_should_send_annotation_event_does_not_send_group_annotations(self):
        """Users shouldn't see annotations in groups they aren't members of."""
        annotation = {
            'user': 'fred',
            'permissions': {'read': ['group:private-group']}
        }
        socket = Mock(terminated=False, client_id='foo')
        socket.request.effective_principals = []  # No 'group:private-group'.
        event_data = {'action': 'create', 'src_client_id': 'bar'}

        assert not should_send_annotation_event(socket, annotation, event_data)

    def test_should_send_annotation_event_does_send_nipsad_annotations(self):
        """Users should see annotations from groups they are members of."""
        annotation = {
            'user': 'fred',
            'group': 'private-group',
            'permissions': {'read': ['group:private-group']}
        }
        socket = Mock(terminated=False, client_id='foo')
        socket.request.effective_principals = ['group:private-group']
        event_data = {'action': 'create', 'src_client_id': 'bar'}

        assert should_send_annotation_event(socket, annotation, event_data)

    def test_should_send_annotation_event_does_not_crash_if_no_group(self):
        """Users should see annotations from groups they are members of."""
        annotation = {
            'user': 'fred',
            'permissions': {'read': ['group:__world__']}
        }
        socket = Mock(terminated=False, client_id='foo')
        socket.request.effective_principals = ['group:private-group']
        event_data = {'action': 'create', 'src_client_id': 'bar'}

        assert should_send_annotation_event(socket, annotation, event_data)


def test_process_message_calls_handler_with_sockets():
    handler = Mock()
    message = FakeMessage('{"foo": "bar"}')

    streamer.process_message(handler, Mock(), message)

    handler.assert_called_once_with(ANY, WebSocket.instances)


def test_process_message_deserializes_messages():
    handler = Mock()
    message = FakeMessage('{"foo": "bar"}')

    streamer.process_message(handler, Mock(), message)

    handler.assert_called_once_with({'foo': 'bar'}, ANY)


def test_process_queue_creates_reader_for_topic(get_reader):
    settings = {'foo': 'bar'}

    streamer.process_queue(settings, 'donkeys', lambda m, s: None)

    get_reader.assert_any_call(settings, 'donkeys', ANY)


@patch('h.streamer.process_message')
def test_process_queue_connects_reader_on_message_to_process_message(process_message, get_reader):
    settings = {'foo': 'bar'}
    handler = Mock()
    reader = get_reader.return_value

    streamer.process_queue(settings, 'donkeys', handler)
    message_handler = reader.on_message.connect.call_args[1]['receiver']
    message_handler(reader, 'message')

    process_message.assert_called_once_with(handler, reader, 'message')


def test_process_queue_starts_reader(get_reader):
    settings = {'foo': 'bar'}
    reader = get_reader.return_value

    streamer.process_queue(settings, 'donkeys', lambda m, s: None)

    reader.start.assert_called_once_with(block=True)


def test_process_queue_close_readers_explicitly_if_it_stops(get_reader):
    settings = {'foo': 'bar'}
    reader = get_reader.return_value

    streamer.process_queue(settings, 'gorillas', lambda m, s: None)

    reader.close.assert_called_once_with()


@pytest.fixture
def get_reader(request):
    patcher = patch('h.queue.get_reader')
    mock = patcher.start()
    request.addfinalizer(patcher.stop)
    return mock
