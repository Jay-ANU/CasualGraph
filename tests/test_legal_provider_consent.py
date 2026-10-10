"""Real endpoint entrypoints must match consent to the saved external recipient."""
import pytest
from fastapi import HTTPException

from api.routers import contract_review as routes
from legal import review_questions


def official_review():
    return {'id': 'r1', 'status': 'completed', 'payload': {
        'profile': {'model': {'id': 'claude-test', 'provider': 'anthropic'},
                    'external_processing_provider': 'anthropic'},
        'decisions': {},
    }}


@pytest.mark.parametrize('endpoint', ['question', 'check'])
@pytest.mark.parametrize('provider', [None, 'ydata'])
def test_official_followup_needs_the_official_recipient_in_the_request(monkeypatch, endpoint, provider):
    review = official_review()
    monkeypatch.setattr(routes, '_review', lambda *a: (review, {}))
    monkeypatch.setattr(review_questions, 'ask', lambda *a: pytest.fail('unauthorized question'))
    monkeypatch.setattr(routes.draft_release, 'check', lambda *a: pytest.fail('unauthorized model check'))
    fields = {'request_id': 'request1', 'external_processing_confirmed': True,
              'external_processing_provider': provider}
    with pytest.raises(HTTPException) as error:
        if endpoint == 'question':
            routes.ask_question('r1', routes.QuestionRequest(question='付款安排？', **fields), {'id': 'u1'})
        else:
            routes.check_draft('r1', routes.DraftCheckRequest(**fields), {'id': 'u1'})
    assert error.value.status_code == 409
    assert error.value.detail['error'] == 'legal_model_provider_changed'


@pytest.mark.parametrize('endpoint', ['question', 'check'])
def test_explicit_official_recipient_reaches_the_requested_operation(monkeypatch, endpoint):
    review = official_review()
    monkeypatch.setattr(routes, '_review', lambda *a: (review, {}))
    monkeypatch.setattr(routes.store, 'review', lambda *a: review)
    monkeypatch.setattr(routes, '_review_view', lambda r: r)
    calls = []
    monkeypatch.setattr(review_questions, 'ask', lambda *a: calls.append('question') or {'answer': '合成回答'})
    monkeypatch.setattr(routes.draft_release, 'check', lambda *a: calls.append('check'))
    fields = {'request_id': 'request1', 'external_processing_confirmed': True,
              'external_processing_provider': 'anthropic'}
    if endpoint == 'question':
        routes.ask_question('r1', routes.QuestionRequest(question='付款安排？', **fields), {'id': 'u1'})
    else:
        routes.check_draft('r1', routes.DraftCheckRequest(**fields), {'id': 'u1'})
    assert calls == [endpoint]


def test_resume_does_not_queue_a_legacy_claude_job_for_the_new_provider(monkeypatch):
    review = official_review()
    review.update(status='partial')
    review['payload']['retryable'] = True
    review['payload']['profile'].update(external_processing_provider='ydata',
                                        model={'id': 'claude-test', 'provider': 'ydata'})
    monkeypatch.setattr(routes, '_review', lambda *a: (review, {}))
    monkeypatch.setattr(routes.store, 'queue_resume', lambda *a: pytest.fail('legacy job queued'))
    monkeypatch.setattr(routes.engine, 'submit', lambda *a: pytest.fail('legacy job submitted'))
    with pytest.raises(HTTPException) as error:
        routes.resume('r1', {'id': 'u1'})
    assert error.value.status_code == 409


@pytest.mark.parametrize('provider,expected', [('ydata', False), ('anthropic', True)])
def test_review_view_does_not_offer_resume_for_retired_claude_routing(monkeypatch, provider, expected):
    review = official_review()
    review.update(status='failed', contract_id='c1', created_at=0, lease_until=0)
    review['payload']['profile'].update(external_processing_provider=provider,
                                        model={'id': 'claude-test', 'provider': provider})
    monkeypatch.setattr(routes.draft_release, 'export_state', lambda *a: {'ready': False})
    assert routes._review_view(review, {'id': 'c1'})['resumable'] is expected
