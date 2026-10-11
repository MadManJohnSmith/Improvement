"""Deterministic, non-authorizing skill selection over a Host-approved roster.

Three inputs, one answer, both bound by a digest.

* ``observations`` are Host-verified project facts — language, stack, test
  tooling, observed behaviour. Each carries the SHA-256 of the evidence it
  rests on, so an answer can always be traced back to what was read.
* ``intent`` is the single action the mode declares, from a closed vocabulary.
* ``roster`` is the Creator approval input: the skills Host accepted for this
  project, plus the digest of that approval.

Output: the permitted list with a reason per skill, or ``abstain`` with its
cause, plus the per-mode capability ceiling and a digest over the whole request.

This module selects and nothing else. It does not load, install, invoke,
execute or grant anything, and no field of its output is a capability: the
Host's capability plane remains the only source of authority, exactly as in
``scripts/capabilities.py``. An observation without evidence, a match that
depends on prose rather than a checked fact, an action outside the vocabulary
and a selection that overruns the context budget all abstain instead of
guessing.

Determinism is the baseline and the point: the same request yields the same
answer, so the answer is reproducible and auditable without trusting whoever
produced it.
"""

import hashlib
import json
import re

# Closed vocabularies. A value outside them is an abstention, never a guess.
ACTIONS = frozenset((
    'audit', 'repair', 'implement', 'plan', 'review', 'verify',
))
MODES = {
    # The mode decides the ceiling: what a mode may never do is what this
    # router must never appear to grant. See scripts/mode_lifecycle.py for the
    # candidate lifecycle and scripts/capabilities.py for Host authority.
    'auditor': frozenset(('read_product', 'report')),
    'reparador': frozenset(('read_product', 'candidate_write', 'test_execute', 'report')),
    'implementador': frozenset(('read_product', 'candidate_write', 'test_execute', 'report')),
}
CAPABILITIES = frozenset().union(*MODES.values())
IDENTIFIER = re.compile(r'^[a-z][a-z0-9-]{0,63}$')
DIGEST = re.compile(r'^[0-9a-f]{64}$')
MAX_ROSTER = 64
MAX_OBSERVATIONS = 128
MAX_MATCHES = 16
MAX_BUDGET = 65536
MAX_FACTS = 32


def _digest(value):
    canonical = json.dumps(
        value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def _keys(value, expected):
    return isinstance(value, dict) and set(value) == set(expected)


def _id(value):
    return isinstance(value, str) and bool(IDENTIFIER.fullmatch(value))


def _members(value, choices, *, nonempty=False):
    return (isinstance(value, list)
            and (not nonempty or bool(value))
            and len(value) == len(set(value))
            and all(isinstance(x, str) and x in choices for x in value))


def _result(allowed, reasons, abstain, scope, request_digest):
    result = {
        'allowed': allowed,
        'reasons': reasons,
        'abstain': abstain,
        'scope': scope,
        'request_digest': request_digest,
    }
    result['digest'] = _digest(result)
    return result


def _abstain(reason, request_digest, scope):
    return _result([], [], reason, scope, request_digest)


class Abstain(Exception):
    """A reason to refuse the request, carried up to the single answer."""


def _die(reason):
    raise Abstain(reason)


def _checked_facts(observations):
    """Facts from evidence-bound observations.

    A fact repeated with a different value is ambiguous and the whole request
    is refused: picking one of two contradictory readings would be the router
    inventing a fact it cannot verify.
    """
    if (not isinstance(observations, list)
            or not observations
            or len(observations) > MAX_OBSERVATIONS):
        _die('invalid_observations')
    facts = {}
    for observation in observations:
        if (not _keys(observation, ('fact', 'value', 'evidence_sha256'))
                or not _id(observation['fact'])
                or not isinstance(observation['value'], str)
                or not 0 < len(observation['value']) <= 128
                or not DIGEST.fullmatch(observation['evidence_sha256'])):
            _die('unverified_or_invalid_observations')
        prior = facts.get(observation['fact'])
        if prior is not None and prior != observation['value']:
            _die('ambiguous_observations')
        facts[observation['fact']] = observation['value']
    if len(facts) > MAX_FACTS:
        _die('invalid_observations')
    return facts


def _checked_roster(roster, denied):
    """The approved roster, checked end to end.

    Every skill carries the routing metadata this module needs to decide, and
    every value in it is checked before a name is ever considered: an
    unchecked field is how a name reaches the output without being earned.
    """
    if (not _keys(roster, ('approval_sha256', 'skills'))
            or not isinstance(roster['approval_sha256'], str)
            or not DIGEST.fullmatch(roster['approval_sha256'])
            or not isinstance(roster['skills'], list)
            or not 0 < len(roster['skills']) <= MAX_ROSTER):
        _die('invalid_roster')
    if not isinstance(denied, (list, tuple)) or len(denied) > MAX_ROSTER:
        _die('invalid_denial')
    seen = set()
    for skill in roster['skills']:
        if not _keys(skill, ('name', 'routing')) or not _id(skill['name']):
            _die('invalid_roster')
        if skill['name'] in seen:
            _die('ambiguous_roster')
        seen.add(skill['name'])
        routing = skill['routing']
        if not _keys(routing, ('actions', 'modes', 'requires',
                               'capability_set', 'context_bytes')):
            _die('invalid_routing_metadata')
        if (not _members(routing['actions'], ACTIONS, nonempty=True)
                or not _members(routing['modes'], MODES, nonempty=True)
                or not _members(routing['capability_set'], CAPABILITIES)
                or not isinstance(routing['context_bytes'], int)
                or isinstance(routing['context_bytes'], bool)
                or not 1 <= routing['context_bytes'] <= MAX_BUDGET
                or not isinstance(routing['requires'], dict)
                or not 0 < len(routing['requires']) <= MAX_FACTS
                or not all(_id(key) and isinstance(value, str)
                           and 0 < len(value) <= 128
                           for key, value in routing['requires'].items())):
            _die('invalid_routing_metadata')
    if not _members(list(denied), seen):
        _die('invalid_denial')
    return True


def select(observations, intent, roster, *, mode, budget, denied=()):
    """Return the permitted skill list for this mode and action, or abstain.

    Never an execution authorization. ``allowed`` names are input to the Host's
    own loading path; this function has no path by which a name in its output
    can become a capability, an install or a write.

    A skill is permitted only when all four hold: its routing modes contain this
    mode, its actions contain this intent, every fact it requires is present
    and equal in the evidence-bound observations, and its capability set fits
    the mode's ceiling. Anything else abstains, and the abstention names the
    cause rather than returning an empty success.
    """
    if (not isinstance(mode, str) or mode not in MODES
            or isinstance(budget, bool)
            or not isinstance(budget, int)
            or not 0 <= budget <= MAX_BUDGET):
        return _result([], [], 'invalid_mode_or_budget', {}, None)
    scope = {
        'mode': mode,
        'capability_ceiling': sorted(MODES[mode]),
        'authorizes_execution': False,
    }
    try:
        request_digest = _digest({
            'observations': observations, 'intent': intent, 'roster': roster,
            'mode': mode, 'budget': budget, 'denied': denied,
        })
        facts = _checked_facts(observations)
        if not _keys(intent, ('action',)) or intent['action'] not in ACTIONS:
            _die('unstructured_intent')
        _checked_roster(roster, denied)
    except Abstain as reason:
        return _abstain(str(reason), request_digest, scope)
    except (TypeError, ValueError, OverflowError):
        return _result([], [], 'invalid_input', scope, None)

    action = intent['action']
    ceiling = MODES[mode]
    permitted = []
    for skill in roster['skills']:
        routing = skill['routing']
        if (mode not in routing['modes']
                or action not in routing['actions']
                or not set(routing['capability_set']) <= ceiling
                or skill['name'] in denied):
            continue
        if all(facts.get(fact) == value
               for fact, value in routing['requires'].items()):
            permitted.append(skill)
    if not permitted:
        return _abstain('no_eligible_skill', request_digest, scope)
    if len(permitted) > MAX_MATCHES:
        return _abstain('too_many_matches', request_digest, scope)
    if sum(s['routing']['context_bytes'] for s in permitted) > budget:
        return _abstain('context_budget_exceeded', request_digest, scope)

    permitted.sort(key=lambda s: s['name'])
    reasons = [{
        'skill': skill['name'],
        'action': action,
        'matched_facts': sorted(skill['routing']['requires']),
        'capabilities': sorted(skill['routing']['capability_set']),
        'context_bytes': skill['routing']['context_bytes'],
    } for skill in permitted]
    return _result([s['name'] for s in permitted], reasons, None, scope,
                   request_digest)
