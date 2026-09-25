"""Bounded parallel specialists, independent critic, then whole-contract arbitration.

Specialists never edit the document. State updates pass through a locked
supervisor checkpoint. Models and their outputs confer no extra permissions.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import hashlib
import json
import threading
import time
from typing import Callable
from legal import external_law, review_quality as quality, review_store as store, ydata
from legal.agent_team import SPECIALISTS, build_tasks, enforce_specialist_scope, initial_team
from legal.review_plan import build_plan, relevant_evidence
from legal import review_v2 as v2

COLLABORATION_VERSION = 1
MAX_CALLS_PER_ATTEMPT = 40
MAX_PARALLEL_AGENTS = 3
_MODEL_SLOTS = threading.BoundedSemaphore(4)
FATAL = frozenset({'ydata_not_configured', 'ydata_family_not_configured', 'ydata_key_conflict',
                   'ydata_unauthorized', 'ydata_rate_limited',
                   'legal_call_budget', 'team_paused', 'legacy_review_restart_required', 'contract_version_changed'})
ARBITRATE = v2.VERIFY + '''\n你是汇总复核 Agent，不按投票数决定结论。对全部 specialist_findings 和当前 findings 逐项复核，交叉检查不同职责给出的结论是否矛盾。
必须为每项coverage给出coverage_checks；每项finding给出checks，明确说明支持、待确认或拒绝。不得凭空增加依据，不得改写原文。
对proposed_changes全部候选同时采用的情况逐项输出proposal_checks:[{finding_id,status:"consistent|uncertain|conflict",reason}]。
同一段的不同替代文本不能同时接受；定义、付款条件、责任例外和解除机制冲突须标conflict。缺少某个审查任务时不能宣称全文无遗漏。
复核通过仍是模型判断，法律版本及适用仍需人工确认。'''

def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def block_conflicting_edits(findings: list[dict]) -> None:
    targets: dict[str, set[str]] = {}
    for f in findings:
        if f.get('block_id') and f.get('suggested_text') and f.get('verification_status') == 'supported':
            targets.setdefault(f['block_id'], set()).add(f['suggested_text'])
    for f in findings:
        if len(targets.get(f.get('block_id'), set())) > 1:
            f.update(revision_allowed=False, needs_confirmation=True, conflict_group=f['block_id'],
                     cross_edit_status='conflict', cross_edit_note='多个 Agent 对同一段提出不同修改，请人工合并后重新审查。')

def run_review(rid: str, *, model: Callable | None = None, retrieve: Callable | None = None,
               authorize: Callable | None = None) -> None:
    from legal import review_engine as legacy
    model, retrieve, authorize = model or legacy.model_json, retrieve or external_law.retrieve_law, authorize or legacy.authorize_job
    token = store.claim(rid)
    if not token:
        return
    job = store.review(rid)
    p = job['payload']
    lock = threading.RLock()
    stopped = threading.Event()
    calls = 0
    started = time.monotonic()
    contract = None
    def guard() -> None:
        current = store.review(rid)
        if current.get('worker_token') != token or current['status'] != 'running':
            raise v2.ReviewStopped('review_cancelled_or_lease_lost')
        authorize(job, contract)
        latest = store.contract(job['contract_id'])
        if latest['status'] != 'ready' or latest['revision'] != p['contract_revision']:
            raise ydata.GatewayError('contract_version_changed', '合同状态已变化，请新建审查。', 409)
        if p.get('profile', {}).get('external_processing_provider') != 'ydata':
            raise ydata.GatewayError('legacy_review_restart_required', '请重新确认外部处理授权。', 409)
    def checkpoint(stage: str | None = None, phase: str | None = None) -> None:
        guard()
        if stage is not None:
            p['stage'] = stage
        if phase is not None:
            p['progress'] = {'phase': phase, 'completed': len(p.get('batches', {})),
                             'total': len(p.get('agent_tasks', [])) + 1}
        p['findings'], p['coverage'] = quality.consolidate(p.get('batches', {}))
        for f in p['findings']:
            f['revision_allowed'] = False
        p['summary'] = quality.summary(p['findings'], p['coverage'])
        store.checkpoint(rid, token, p)
    def status(agent_id: str, value: str, note: str = '') -> None:
        with lock:
            for agent in p['collaboration']['agents']:
                if agent['id'] == agent_id:
                    agent.update(status=value, note=note)
            checkpoint()
    def generate(agent_id: str, system: str, data: dict) -> dict:
        nonlocal calls
        while not _MODEL_SLOTS.acquire(timeout=.2):
            with lock:
                guard()
            if stopped.is_set():
                raise ydata.GatewayError('team_paused', '协作调用已暂停，成功步骤可恢复。', 429)
        try:
            with lock:
                guard()
                if stopped.is_set():
                    raise ydata.GatewayError('team_paused', '协作调用已暂停，成功步骤可恢复。', 429)
                if calls >= MAX_CALLS_PER_ATTEMPT:
                    stopped.set()
                    raise ydata.GatewayError('legal_call_budget', '协作调用达到本次预算，未完成步骤已保留。', 429)
                request = {**deepcopy(data), 'profile': deepcopy(p['profile']),
                           'agent_context': {'id': agent_id, 'collaboration_version': COLLABORATION_VERSION}}
                if len(system) + len(json.dumps(request, ensure_ascii=False)) > v2.MAX_INPUT_CHARACTERS:
                    raise ydata.GatewayError('legal_context_budget', '本步骤上下文超过预算，合同未被静默截断。', 422)
                calls += 1
                metrics = p.setdefault('metrics', {})
                metrics['model_calls'] = metrics.get('model_calls', 0) + 1
                agent_calls = metrics.setdefault('agent_model_calls', {})
                agent_calls[agent_id] = agent_calls.get(agent_id, 0) + 1
                checkpoint()
            result = model(system, request)
            with lock:
                guard()
            return result
        finally:
            _MODEL_SLOTS.release()
    def safe_error(exc: Exception) -> str:
        return exc.message if isinstance(exc, ydata.GatewayError) else '本步骤未完成，已保留其他 Agent 的成功结果。'
    try:
        contract = store.contract(job['contract_id'])
        with lock:
            guard()
            if p.get('decisions'):
                raise ydata.GatewayError('legal_new_review_required', '已有人工决定，请新建审查，避免覆盖修改。', 409)
            p['engine_version'] = 2
            p['collaboration_version'] = COLLABORATION_VERSION
            p['plan'] = p.get('plan') or build_plan(legacy.RULES, contract['payload']['redacted_blocks'], p['profile'], p.get('policies', []))
            tasks = build_tasks(p['plan'])
            p['agent_tasks'] = tasks
            p['collaboration'] = {'version': COLLABORATION_VERSION, 'max_parallel': MAX_PARALLEL_AGENTS,
                'call_budget': MAX_CALLS_PER_ATTEMPT, 'agents': initial_team(tasks) + [
                    {'id': 'critic', 'title': '证据与覆盖复核', 'status': 'pending', 'completed': 0, 'total': len(tasks), 'note': ''},
                    {'id': 'arbiter', 'title': '全文协调与冲突检查', 'status': 'pending', 'completed': 0, 'total': 1, 'note': ''}]}
            p.setdefault('batches', {})
            p.setdefault('batch_errors', {})
            blocks, policies = deepcopy(contract['payload']['redacted_blocks']), deepcopy(p.get('policies', []))
            checkpoint('正在读取合同，建立共享的原文事实', 'intake')
        if 'intake' not in p:
            facts = quality.validate_facts(generate('intake', v2.INTAKE, {'contract_blocks': blocks}), blocks)
            with lock:
                p['intake'] = facts
                checkpoint()
        searches = p.setdefault('searches', {})
        for rule in p['plan']:
            if not rule.get('queries') or searches.get(rule['id'], {}).get('status') == 'retrieved':
                continue
            with lock:
                checkpoint('法律资料检索：' + rule['title'], 'retrieval')
            sources, warnings, attempts = {}, [], []
            for query_index, query in enumerate(rule['queries']):
                with lock:
                    guard()
                result = retrieve(query['query'], query['keywords'])
                with lock:
                    guard()
                attempts.append({'query': query['query'], 'status': result.get('status', 'unavailable')})
                warnings.extend(result.get('warnings', []))
                sources.update({s['id']: s for s in result.get('sources', [])})
                if sources and query_index == len(rule['queries']) - 2:
                    break
            with lock:
                searches[rule['id']] = {'status': 'retrieved' if sources else 'no_verified_source',
                    'sources': list(sources.values()), 'warnings': list(dict.fromkeys(warnings)),
                    'provider': result.get('provider', 'external'), 'attempts': attempts}
                checkpoint()
        with lock:
            checkpoint('多个审查 Agent 正在分别检查合同', 'collaboration')
        def work_agent(agent_id: str) -> None:
            own_tasks = [t for t in tasks if t['agent_id'] == agent_id]
            if not own_tasks:
                return
            status(agent_id, 'running')
            errors = 0
            for task in own_tasks:
                if stopped.is_set():
                    break
                group = task['rules']
                selected_policies = [pol for pol in policies if any(r.get('policy_id') == pol['id'] for r in group)]
                sources = relevant_evidence([s for r in group for s in searches.get(r['origin_rule_id'], {}).get('sources', [])]) if agent_id == 'legal' else []
                data = {'rules': group, 'contract_blocks': blocks, 'legal_sources': sources,
                    'company_policies': selected_policies, 'facts': p['intake']['facts'],
                    'parsing_warnings': contract['payload'].get('warnings', []),
                    'specialist': {'id': agent_id, 'allowed_kind': task['kind']}}
                input_hash = digest({'task': task, 'data': data, 'profile': p['profile']})
                with lock:
                    prior = p['batches'].get(task['id'])
                    reuse = prior and prior.get('input_hash') == input_hash and task['id'] not in p['batch_errors']
                if not reuse:
                    try:
                        raw = generate(agent_id, v2.REVIEW + '\n本 Agent 的职责：' + task['instructions'] + '\n仅输出kind=' + task['kind'] + '的候选意见。', data)
                        checked = enforce_specialist_scope(quality.validate(raw, group, blocks, sources, selected_policies), task)
                        status('critic', 'running')
                        verified = generate('critic', v2.VERIFY, {**data, 'findings': checked['findings'], 'coverage': checked['coverage']})
                        quality.apply_verification(checked, verified)
                        checked.update(input_hash=input_hash, agent_id=agent_id, sources=sources)
                        with lock:
                            guard()
                            p['batches'][task['id']] = checked
                            p['batch_errors'].pop(task['id'], None)
                            p.pop('arbitration', None)
                            p['batches'].pop('consistency', None)
                            checkpoint()
                        errors = 0
                    except ydata.GatewayError as exc:
                        with lock:
                            p['batches'].pop(task['id'], None)
                            p.pop('arbitration', None)
                            p['batches'].pop('consistency', None)
                            p['batch_errors'][task['id']] = safe_error(exc)
                            checkpoint()
                        errors += 1
                        if exc.code in FATAL:
                            stopped.set()
                            break
                        if errors >= 2:
                            break
                with lock:
                    for a in p['collaboration']['agents']:
                        if a['id'] == agent_id:
                            a['completed'] = sum(t['id'] in p['batches'] for t in own_tasks)
                        elif a['id'] == 'critic':
                            a['completed'] = sum(t['id'] in p['batches'] for t in tasks)
                    checkpoint()
            with lock:
                done = sum(t['id'] in p['batches'] for t in own_tasks)
                for t in own_tasks:
                    if t['id'] not in p['batches']:
                        p['batch_errors'].setdefault(t['id'], '此 Agent 步骤尚未完成。')
                status(agent_id, 'completed' if done == len(own_tasks) else 'partial')
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_AGENTS, thread_name_prefix='legal-specialist') as pool:
            futures = [pool.submit(work_agent, spec.id) for spec in SPECIALISTS]
            try:
                for future in as_completed(futures):
                    future.result()
            except BaseException:
                stopped.set()
                raise
        with lock:
            status('critic', 'completed' if all(t['id'] in p['batches'] for t in tasks) else 'partial')
            guard()
            specialist_batches = {t['id']: p['batches'][t['id']] for t in tasks if t['id'] in p['batches']}
            findings, coverage = quality.consolidate(specialist_batches)
            pool_sources = v2.all_sources(p)
            cited_ids = {ref['source_id'] for f in findings for ref in f.get('citations', [])}
            cited_sources = [source for source in pool_sources if source['id'] in cited_ids]
            sources = cited_sources + relevant_evidence([source for source in pool_sources if source['id'] not in cited_ids])
            data = {'rules': [v2.CONSISTENCY], 'contract_blocks': blocks, 'legal_sources': sources,
                'company_policies': policies, 'facts': p['intake']['facts'],
                'previous_findings': findings, 'missing_tasks': sorted(p['batch_errors'])}
            arbiter_hash = digest({'data': data, 'coverage': coverage, 'profile': p['profile']})
            arbitration = p.get('arbitration')
        if not arbitration or arbitration.get('input_hash') != arbiter_hash:
            try:
                status('arbiter', 'running')
                extra = quality.validate(generate('arbiter', v2.REVIEW, data), [v2.CONSISTENCY], blocks, sources, policies)
                for finding in extra['findings']:
                    finding.update(agent_id='arbiter', agent_title='全文协调与冲突检查')
                combined = {'findings': deepcopy(findings) + extra['findings'], 'coverage': deepcopy(coverage) + extra['coverage']}
                proposals = [{'finding_id': f['id'], 'block_id': f['block_id'], 'suggested_text': f['suggested_text']} for f in combined['findings'] if f.get('suggested_text')]
                checked = generate('arbiter', ARBITRATE, {**data, **combined, 'specialist_findings': findings, 'proposed_changes': proposals})
                quality.apply_verification(combined, checked)
                quality.apply_cross_edit_checks(combined['findings'], checked)
                block_conflicting_edits(combined['findings'])
                with lock:
                    p['batches']['consistency'] = {**extra, 'sources': sources}
                    p['arbitration'] = arbitration = {'input_hash': arbiter_hash, **combined}
                    p['batch_errors'].pop('consistency', None)
                    status('arbiter', 'completed')
            except (ydata.GatewayError, v2.ReviewStopped) as exc:
                with lock:
                    guard()
                    p['batch_errors']['consistency'] = safe_error(exc)
                    arbitration = None
                    status('arbiter', 'partial')
        with lock:
            guard()
            if arbitration:
                for agent in p['collaboration']['agents']:
                    if agent['id'] == 'arbiter':
                        agent.update(status='completed', completed=1)
                p['findings'], p['coverage'] = deepcopy(arbitration['findings']), deepcopy(arbitration['coverage'])
            else:
                p['findings'], p['coverage'] = findings, coverage
                quality.apply_cross_edit_checks(p['findings'], None)
            covered = {c['rule_id'] for c in p['coverage']}
            for rule in [r for t in tasks for r in t['rules']] + [v2.CONSISTENCY]:
                if rule['id'] not in covered:
                    p['coverage'].append({'rule_id': rule['id'], 'title': rule['title'], 'status': 'not_reviewed',
                        'note': '本项协作检查尚未完成。', 'verification_status': 'uncertain'})
            incomplete = (bool(p['batch_errors']) or any(s['status'] != 'retrieved' for s in searches.values())
                or any(c['status'] in ('not_reviewed', 'needs_information') for c in p['coverage'])
                or any(b.get('rejected_findings', 0) for b in p['batches'].values())
                or any(f['verification_status'] != 'supported' or f['evidence_status'] == 'unverified' or f['missing_facts']
                       or f.get('cross_edit_status') in ('uncertain', 'conflict') for f in p['findings']))
            p['summary'] = quality.summary(p['findings'], p['coverage'])
            p['retryable'] = bool(p['batch_errors']) or any(s['status'] != 'retrieved' for s in searches.values())
            p['stage'] = '协作检查完成，请逐项确认' if not incomplete else '协作检查部分完成，请处理分歧与覆盖缺口'
            p['progress'] = {'phase': 'complete', 'completed': len(p['batches']), 'total': len(tasks) + 1}
            p.setdefault('metrics', {})['last_attempt_seconds'] = round(time.monotonic() - started, 2)
            p.pop('error', None)
            store.checkpoint(rid, token, p, 'partial' if incomplete else 'completed')
    except v2.ReviewStopped:
        stopped.set()
    except Exception as exc:
        stopped.set()
        with lock:
            current = store.review(rid)
            if current.get('worker_token') == token and current['status'] == 'running':
                p.update(stage='协作审查已暂停，已完成步骤已保存', error=safe_error(exc), retryable=True)
                for agent in p.get('collaboration', {}).get('agents', []):
                    if agent['status'] in ('pending', 'running'):
                        agent['status'] = 'paused'
                store.checkpoint(rid, token, p, 'failed')
