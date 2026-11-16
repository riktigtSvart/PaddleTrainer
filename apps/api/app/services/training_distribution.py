"""Deterministic placement preference within existing, verified prescriptions.

This is a bounded local search, not a personal recovery model. It moves or
exchanges editable proposals, without increasing a microcycle's
session count or minutes. Fixed commitments and explicit choices stay fixed.
"""
from datetime import date, datetime, timedelta

from app.services import training_mesocycles as cycles, training_starting_load as load

SCHEMA = 'training-distribution-v0.1'
MAX_PASSES = 32


def block_key(context, candidate):
    block = cycles.block_on(context, candidate['date'])
    return block['key'] if block else candidate['training_period_id']


def totals(context, candidates):
    result = {}
    for c in candidates:
        key = block_key(context, c)
        value = result.setdefault(key, [0, 0])
        value[0] += 1
        value[1] += c['duration_sec']
    return result


def training_days(candidates, fixed, first, last):
    return sorted({date.fromisoformat(c['date']) for c in candidates} | {
        v['date'] for v in fixed if not v.get('missed_reservation') and
        first - timedelta(days=6) <= v['date'] <= last + timedelta(days=6)})


def rhythm(candidates, fixed, first, last):
    days = training_days(candidates, fixed, first, last)
    adjacent = sum((b - a).days == 1 and (first <= a <= last or first <= b <= last)
                   for a, b in zip(days, days[1:]))
    inside = [d for d in days if first <= d <= last]
    left = max((d for d in days if d < first), default=first - timedelta(days=1))
    right = min((d for d in days if d > last), default=last + timedelta(days=1))
    gaps = [(b - a).days - 1 for a, b in zip([left, *inside], [*inside, right])]
    return {'adjacent_training_day_pairs': adjacent,
            'longest_training_free_span_days': max(gaps, default=0),
            'squared_training_free_spans': sum(v * v for v in gaps)}


def matches(candidate, preference):
    return all(candidate.get(k) == preference[k] for k in
               ('template_key', 'opportunity_key', 'capability_key', 'role') if k in preference)


def improve(baseline, alternatives, state, data, preferences):
    context, fixed = state['coordination'], state['loads']
    first, last = date.fromisoformat(data['start_date']), date.fromisoformat(data['end_date'])
    limits = totals(context, baseline)
    seed_primary = {(block_key(context, c), c['capability_key']) for c in baseline if c['role'] == 'primary_development'}
    pool = {c['candidate_key']: c for a in alternatives for c in a['candidates']}
    # The greedy seed is itself valid, even if its remaining-budget-dependent
    # duration is shorter than a standalone candidate of the same family.
    pool.update({c['candidate_key']: c for c in baseline})
    by_block = {}
    for c in sorted(pool.values(), key=lambda v: (v['date'], v['candidate_key'])):
        by_block.setdefault(block_key(context, c), []).append(c)

    def score(rows):
        represented = {role: set() for role in ('primary_development', 'maintenance', 'secondary_development')}
        strength_freshness = {}
        for c in rows:
            if c['role'] in represented:
                represented[c['role']].add((block_key(context, c), c['capability_key']))
            if c['sport'] == 'STRENGTH':
                block = cycles.block_on(context, c['date'])
                if block:
                    # Reward the first strength session's placement, never
                    # additional strength sessions merely to raise the score.
                    strength_freshness[block['key']] = max(strength_freshness.get(block['key'], 0),
                        (date.fromisoformat(block['end_date']) - date.fromisoformat(c['date'])).days + 1)
        spacing = rhythm(rows, fixed, first, last)
        return (len(represented['primary_development']), len(represented['primary_development'] & seed_primary), len(represented['maintenance']),
                len(represented['secondary_development']), -spacing['adjacent_training_day_pairs'],
                -spacing['squared_training_free_spans'], sum(strength_freshness.values()),
                sum(c['duration_sec'] for c in rows))

    def allowed(rows, candidate):
        if any(c['date'] == candidate['date'] for c in rows):
            return False
        key = block_key(context, candidate)
        if sum(c['duration_sec'] for c in rows if block_key(context, c) == key) + candidate['duration_sec'] > limits[key][1]:
            return False
        others = fixed + [{'date': date.fromisoformat(c['date']), 'seconds': c['duration_sec'],
                           'at': datetime.fromisoformat(c['start_at']), 'sport': c['sport'], 'known': True} for c in rows]
        target = date.fromisoformat(candidate['date'])
        if load.conflicts(others, datetime.fromisoformat(candidate['start_at']), candidate['sport']):
            return False
        # Check every rolling window containing the added session. Removing a
        # seed session cannot worsen any window which does not contain it.
        for offset in range(7):
            low = target - timedelta(days=offset)
            window = [v for v in others if low <= v['date'] <= low + timedelta(days=6)]
            if (len(window) + 1 > state['max_count'] or
                    any(v['seconds'] is None and not v.get('missed_reservation') for v in window) or
                    sum(v['seconds'] or 0 for v in window) + candidate['duration_sec'] > state['max_seconds']):
                return False
        if context['mode'] == 'coordinated':
            room = cycles.remaining(context, candidate['date'], others)
            if room is not None and candidate['duration_sec'] > room:
                return False
        return True

    selected, passes = list(baseline), 0
    if context['mode'] == 'coordinated':
        # Keep an accepted result as a stable seed when current evidence still
        # verifies all of it and its score is at least as good as the new seed.
        prior_keys = {p['candidate_key'] for p in state['eligible']}
        prior = [pool[k] for k in sorted(prior_keys) if k in pool]
        locked = {c['candidate_key'] for c in baseline if c['date'] in preferences}
        if (len(prior) == len(prior_keys) and totals(context, prior) == limits and
                locked <= prior_keys and
                all(allowed([c for c in prior if c is not candidate], candidate) for candidate in prior) and
                all(not preferences.get(c['date']) or matches(c, preferences[c['date']]) for c in prior) and
                score(prior) >= score(selected)):
            selected = prior
        for _ in range(MAX_PASSES):
            current_score = score(selected)
            best, best_score = None, current_score
            for index, previous in enumerate(selected):
                if previous['date'] in preferences:
                    continue
                rest = selected[:index] + selected[index + 1:]
                for candidate in by_block.get(block_key(context, previous), []):
                    if candidate['date'] in preferences or candidate['candidate_key'] == previous['candidate_key']:
                        continue
                    proposed = [*rest, candidate]
                    proposed_score = score(proposed)
                    if proposed_score <= best_score or not allowed(rest, candidate):
                        continue
                    best, best_score = proposed, proposed_score
            if best is None:
                # Exchange two already selected dates without changing the
                # rhythm or dose. This can put strength earlier after a rest
                # while the flexible aerobic work takes its former date.
                for i, left in enumerate(selected):
                    if left['date'] in preferences:
                        continue
                    key = block_key(context, left)
                    for right in selected[i + 1:]:
                        if right['date'] in preferences or block_key(context, right) != key:
                            continue
                        replacements = []
                        for old, target in ((left, right), (right, left)):
                            match = next((c for c in by_block.get(key, []) if c['date'] == target['date'] and
                                all(c.get(k) == old.get(k) for k in ('template_key', 'capability_key', 'role', 'duration_sec', 'location_id'))), None)
                            if match is None:
                                break
                            replacements.append(match)
                        if len(replacements) != 2:
                            continue
                        proposed = [c for c in selected if c is not left and c is not right] + replacements
                        proposed_score = score(proposed)
                        if proposed_score > best_score and all(allowed([c for c in proposed if c is not candidate], candidate) for candidate in proposed):
                            best, best_score = proposed, proposed_score
            if best is None:
                # A whole group may need to shift together: moving any one
                # session alone can temporarily create an adjacent pair.
                # Preserve each prescription and venue in this escape step.
                for key in sorted(limits):
                    group = [c for c in selected if block_key(context, c) == key]
                    if len(group) < 2 or any(c['date'] in preferences for c in group):
                        continue
                    rest = [c for c in selected if block_key(context, c) != key]
                    for offset in (-3, -2, -1, 1, 2, 3):
                        shifted = []
                        for old in group:
                            day = (date.fromisoformat(old['date']) + timedelta(days=offset)).isoformat()
                            match = next((c for c in by_block.get(key, []) if c['date'] == day and day not in preferences and
                                all(c.get(k) == old.get(k) for k in ('template_key', 'capability_key', 'role', 'duration_sec', 'location_id'))), None)
                            if match is None:
                                break
                            shifted.append(match)
                        if len(shifted) != len(group):
                            continue
                        proposed = rest + shifted
                        proposed_score = score(proposed)
                        if proposed_score > best_score and all(allowed([c for c in proposed if c is not candidate], candidate) for candidate in proposed):
                            best, best_score = proposed, proposed_score
            if best is None:
                break
            selected, passes = best, passes + 1
    selected.sort(key=lambda c: (c['date'], c['candidate_key']))
    proof = {'schema_version': SCHEMA, 'placement_preference': 'saved_goals_then_spaced_civil_days',
             'baseline_candidate_keys': sorted(c['candidate_key'] for c in baseline),
             'before': rhythm(baseline, fixed, first, last), 'after': rhythm(selected, fixed, first, last),
             'optimization_passes': passes, 'max_passes': MAX_PASSES,
             'capacity_increased': False, 'personal_response_model_applied': False}
    return selected, proof
