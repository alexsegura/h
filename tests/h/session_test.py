import pytest
import mock

from h import session


class FakeGroup(object):
    def __init__(self, pubid, name):
        self.pubid = pubid
        self.name = name
        self.slug = pubid


def test_model_sorts_groups():
    fake_user = mock.Mock()
    fake_user.groups = [
        FakeGroup('c', 'Group A'),
        FakeGroup('b', 'Group B'),
        FakeGroup('a', 'Group B'),
    ]
    request = mock.Mock(authenticated_user=fake_user)
    session_model = session.model(request)

    ids = [group['id'] for group in session_model['groups']]

    assert ids == ['__world__', 'c', 'a', 'b']


def test_model_includes_features(fake_user):
    feature_dict = {
        'feature_one': True,
        'feature_two': False,
    }
    request = mock.Mock(authenticated_user=fake_user)
    request.feature.all.return_value = feature_dict

    assert session.model(request)['features'] == feature_dict


@pytest.mark.parametrize(
    "user_authenticated,tutorial_dismissed,show_tutorial",
    [(False, False, False),
     (True,  False, True),
     (True,  True,  False)])
def test_model_show_sidebar_tutorial(
        fake_user, user_authenticated, tutorial_dismissed, show_tutorial):
    """It should return or not return "show_sidebar_tutorial" correctly.

    It should return "show_sidebar_tutorial": True only if a user
    is authorized _and_ that user has not dismissed
    the tutorial. Otherwise, preferences should contain no
    "show_sidebar_tutorial" value at all.

    """
    fake_user.sidebar_tutorial_dismissed = tutorial_dismissed
    if user_authenticated:
        authenticated_user = fake_user
    else:
        authenticated_user = None
    request = mock.Mock(
        authenticated_user=authenticated_user,
        )

    preferences = session.model(request)['preferences']

    if show_tutorial:
        assert preferences['show_sidebar_tutorial'] is True
    else:
        assert 'show_sidebar_tutorial' not in preferences


def test_profile_userid_unauthenticated(unauthenticated_request):
    assert session.profile(unauthenticated_request)['userid'] is None


def test_profile_userid_authenticated(authenticated_request):
    profile = session.profile(authenticated_request)
    assert profile['userid'] == u'acct:user@example.com'


def test_profile_sorts_groups():
    fake_user = mock.Mock()
    fake_user.groups = [
        FakeGroup('c', 'Group A'),
        FakeGroup('b', 'Group B'),
        FakeGroup('a', 'Group B'),
    ]
    request = mock.Mock(authenticated_user=fake_user)
    profile = session.profile(request)

    ids = [group['id'] for group in profile['groups']]

    assert ids == ['__world__', 'c', 'a', 'b']


def test_profile_includes_features(fake_user):
    feature_dict = {
        'feature_one': True,
        'feature_two': False,
    }
    request = mock.Mock(authenticated_user=fake_user)
    request.feature.all.return_value = feature_dict

    assert session.profile(request)['features'] == feature_dict


@pytest.mark.parametrize(
    "user_authenticated,tutorial_dismissed,show_tutorial",
    [(False, False, False),
     (True,  False, True),
     (True,  True,  False)])
def test_profile_show_sidebar_tutorial(
        fake_user, user_authenticated, tutorial_dismissed, show_tutorial):
    """It should return or not return "show_sidebar_tutorial" correctly.

    It should return "show_sidebar_tutorial": True only if a user
    is authorized _and_ that user has not dismissed
    the tutorial. Otherwise, preferences should contain no
    "show_sidebar_tutorial" value at all.

    """
    fake_user.sidebar_tutorial_dismissed = tutorial_dismissed
    if user_authenticated:
        authenticated_user = fake_user
    else:
        authenticated_user = None
    request = mock.Mock(
        authenticated_user=authenticated_user,
        )

    preferences = session.profile(request)['preferences']

    if show_tutorial:
        assert preferences['show_sidebar_tutorial'] is True
    else:
        assert 'show_sidebar_tutorial' not in preferences


@pytest.fixture
def fake_user():
    fake_user = mock.Mock()
    fake_user.groups = []
    return fake_user


@pytest.fixture
def unauthenticated_request():
    return mock.Mock(authenticated_userid=None, authenticated_user=None)


@pytest.fixture
def authenticated_request(fake_user):
    return mock.Mock(authenticated_userid=u'acct:user@example.com',
                     authenticated_user=fake_user)
