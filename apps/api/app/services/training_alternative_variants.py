"""Content identity excludes opportunity, venue and reference provenance.

Different goals/durations/doses remain different workouts. All signed source
records stay intact; grouping never authorizes or modifies a candidate.
"""
from datetime import datetime
from decimal import Decimal
from app.planning.domain.common.serialization import canonical_json


def number(value):
    return format(Decimal(str(value)).normalize(),'f') if value is not None else None


def target(row):
    return {k: number(row.get(k)) if k in {'load_value','hold_seconds'} else row.get(k)
            for k in ['repetitions','hold_seconds','load_kind','load_value','load_basis','load_note']}


def variant(candidate,metadata=None):
    meta=metadata or {}
    strength=candidate.get('strength_prescription') or meta.get('strength')
    movements=None
    if isinstance(strength,dict) and isinstance(strength.get('movements'),list):
        movements=[]
        for m in strength['movements']:
            rows=[m['target'] for _ in range(m['work_sets'])] if 'target' in m else m['sets']
            movements.append({'exercise_id':m['exercise_id'],'side':m['side'],'machine_note':m['machine_note'],
                'sets':[target(s) for s in rows], 'minimum_rir':m.get('minimum_rir',strength.get('minimum_rir')),
                'rest_seconds':m.get('rest_seconds',strength.get('rest_seconds'))})
    intro=meta.get('introductory_strength')
    swim=meta.get('swimming')
    return {'schema_version':'training-workout-variant-v0.1','sport':candidate['sport'],
        'template_key':candidate['template_key'],'primary_goal':candidate['capability_key'],'duration_sec':candidate['duration_sec'],
        'blocks':[{k:b.get(k) for k in ['block_type','duration_sec','distance_m','intensity_type','intensity_min','intensity_max','repeat_count','parent_block_id']} for b in candidate['blocks']],
        'strength':movements,'rpe':meta.get('rpe'), 'running_mode':(meta.get('running') or {}).get('mode'),
        'swimming':{k:number(swim.get(k)) if k=='pool_length_m' else swim.get(k) for k in ['mode','stroke','pool_length_m','lengths_per_repeat','rest_seconds']} if swim else None,
        'introductory':{'movements':[m['key'] for m in intro['movements']],'sets':intro['sets_per_movement'],'max_repetitions':intro['max_repetitions']} if intro else None}


def slot(candidate):
    return canonical_json([int(datetime.fromisoformat(candidate['start_at']).timestamp()*1000),
        int(datetime.fromisoformat(candidate['end_at']).timestamp()*1000),candidate.get('location_id'),candidate.get('location')])


def summary(current,current_metadata,candidates,metadata,checked):
    baseline=variant(current,current_metadata)
    other,schedules=set(),set()
    if checked:
        for c in candidates:
            content=variant(c,metadata.get(c['candidate_key']))
            if content==baseline:
                if slot(c)!=slot(current):schedules.add(slot(c))
            else:other.add(canonical_json(content))
    return {'schema_version':'training-alternative-kinds-v0.1','workout_variant':baseline,'original_schedule':slot(current),
            'different_workouts_count':len(other) if checked else None,
            'same_workout_schedule_count':len(schedules) if checked else None}
