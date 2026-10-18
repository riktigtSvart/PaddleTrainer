"""Post-hoc development comparison; this module is never imported by inference."""
from app.planning_contracts.phase_reconciliation import digest


def evaluate(result, reference):
    before=digest(result)
    binding=result['binding']
    matching=[s for s in reference['sessions'] if s['session_id']==binding['session_id']
              and s['source_content_sha256']==binding['source_sha256']
              and s['plan_source_content_sha256']==binding['plan_sha256']]
    if len(matching)!=1:
        return {'status':'NO_EXACT_SOURCE_BOUND_DEVELOPMENT_REFERENCE',
                'used_for_inference':False,'new_independent_test':False}
    source=matching[0]
    domains=[{'name':'NATIVE_INDEX_ZERO_ASSUMPTION','offset_s':0.0}]
    origin=result.get('source_route_origin_candidate_s')
    if isinstance(origin,(int,float)) and not isinstance(origin,bool):
        domains.append({'name':'PREEXISTING_ROUTE_ORIGIN_ASSUMPTION','offset_s':origin})
    rows=[]
    for gap in source['inter_phase_intervals']:
        q=next((q for q in result['questions'] if q['after_phase_number']==gap['after_phase_number']),None)
        comparisons=[]
        for domain in domains:
            t=gap['derived_end_s']-domain['offset_s']
            options=[v for v in q['options'] if v['kind']=='LOW_SPEED_AND_MOVEMENT_CANDIDATE'] if q else []
            containing=[v for v in options if v['transition_window_s'][0]-1<=t<=v['transition_window_s'][1]+1]
            comparisons.append({'clock_assumption':domain['name'],
                'offset_s':domain['offset_s'],'native_index_reference_candidate_s':t,
                'motion_option_count':len(options),
                'containing_motion_option_count':len(containing),
                'containing_window_widths_s':[round(v['transition_window_s'][1]-v['transition_window_s'][0],6) for v in containing],
                'display_tolerance_s':1,'clock_alignment_verified':False})
        rows.append({'after_phase_number':gap['after_phase_number'],
                     'displayed_reference_transition_s':gap['derived_end_s'],
                     'comparisons':comparisons,'actual_provider_event_verified':False})
    out={'status':'KNOWN_DEVELOPMENT_REFERENCE_WINDOW_COMPARISON',
        'scope':'MOTION_WINDOWS_ONLY_NOT_POINT_ACCURACY_OR_MODEL_PERFORMANCE',
        'source_screenshot_session_association':source['screenshot_association'],
        'known_manual_reference_count':len(rows),'comparisons':rows,
        'used_for_inference':False,'reference_has_seconds_display_precision':True,
        'rules_and_thresholds_not_independently_validated':True,
        'new_independent_test':False,'result_unchanged_by_evaluation':digest(result)==before}
    assert digest(result)==before
    return out
