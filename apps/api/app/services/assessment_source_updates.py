"""An additive exercise registry update does not change an athlete's answers."""
from copy import deepcopy


def registry_extension(context):
    saved = context.get('saved')
    if not context.get('sources_changed') or not saved:
        return False
    from app.services.initial_assessment import source_body
    before = saved['artifact']['snapshot']
    after = context['sources']
    if before['registry']['content_hash'] == after['registry']['content_hash']:
        return False
    left, right = source_body(before), source_body(after)
    left.pop('registry_hash'); right.pop('registry_hash')
    if left != right:
        return False
    old, new = deepcopy(before['registry']), deepcopy(after['registry'])
    old_patterns, new_patterns = old.pop('patterns'), new.pop('patterns')
    old_sports, new_sports = old.pop('sports'), new.pop('sports')
    for value in (old, new):
        value.pop('version'); value.pop('content_hash')
    if old != new or any(v not in new_sports for v in old_sports):
        return False
    lookup = {v['key']: v for v in new_patterns}
    return all(v['key'] in lookup and v['label'] == lookup[v['key']]['label']
               and set(v['exercise_ids']) <= set(lookup[v['key']]['exercise_ids']) for v in old_patterns)
