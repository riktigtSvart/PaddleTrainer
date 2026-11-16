"""Field-level profile diagnostics; never edits an observation or source receipt."""
from app.services.initial_assessment import profile_content

SCHEMA = 'strength-profile-comparison-v0.1'


def compare(context):
    saved = (context.get('receipt') or {}).get('artifact')
    if not saved:
        return {'schema_version': SCHEMA, 'changed_fields': [], 'blocking_fields': [],
                'source_reference_changed': False, 'reference_reusable': False}
    original = (saved['snapshot'].get('profile_receipt') or {}).get('artifact')
    current = (context.get('current_profile_receipt') or {}).get('artifact')
    before = original['proposal']['data'] if original else None
    after = current['proposal']['data'] if current else None
    reference_changed = saved['snapshot']['profile_reference'] != context['source_body']['profile_reference']
    if before is None or after is None:
        changed = [] if before is after else ['profile_presence']
        blocking = list(changed)
    else:
        changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
        relevant = set(profile_content(before)) | set(profile_content(after))
        blocking = [k for k in changed if k in relevant]
    return {'schema_version': SCHEMA, 'changed_fields': changed, 'blocking_fields': blocking,
            'source_reference_changed': reference_changed,
            'reference_reusable': before is not None and after is not None and not blocking and not reference_changed}
