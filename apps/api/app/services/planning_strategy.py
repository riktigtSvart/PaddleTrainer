"""Versioned qualitative strategic starter, not a learned response model or a dose.

The evidence motivates the ordering; exact day windows, focus rankings and focus
count are explicitly product heuristics. Never import elite training volumes.
"""
from collections import Counter
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

RULES = 'mesocycle-strategy-v0.1'
SOURCES = [
    {'key':'kayak-periodization-2010','url':'https://pubmed.ncbi.nlm.nih.gov/20414669/',
     'use':'Kajakos általános–specifikus sorrend és korlátozott számú párhuzamos hangsúly.',
     'limit':'Kis létszámú elit minta; a terhelés és a fejlődés mértéke nem másolható át.'},
    {'key':'kayak-combined-2009','url':'https://pubmed.ncbi.nlm.nih.gov/19396614/',
     'use':'Az állóképességi és neuromuszkuláris felkészülés összekapcsolásának mintája.',
     'limit':'Elit kajakos edzésminta, nem személyes hatásbecslés.'},
    {'key':'taper-2007','url':'https://pubmed.ncbi.nlm.nih.gov/17762369/',
     'use':'A főverseny előtti frissítés elkülönítése az új képességépítéstől.',
     'limit':'A 14 napos jelölés csak szerkeszthető kezdőablak; terheléscsökkentést itt nem írunk elő.'},
]
LABELS = {'foundation':'Alapozó hangsúly','specific':'Versenyspecifikus hangsúly',
          'race_readiness':'Verseny előtti frissítés','transition':'Átvezetés és regeneráció',
          'general':'Általános fejlesztés','historical':'Múltbeli tervrész'}
# All these values are policy defaults, not physiological constants.
POLICY = {'specific_window_days':42,'readiness_window_days':14,'transition_days':7,
          'max_primary_capabilities':2,'acute_signal_hours':48,'high_self_report_score':7}

def local_day(data):
    return datetime.fromisoformat(data['captured_at']).astimezone(ZoneInfo(data['timezone_name'])).date()

def event_day(e, field='start_date'):
    return date.fromisoformat(e[field])

def main_events(data):
    return sorted([e for e in data['competitions'] if e['status']=='planned' and e.get('priority')=='main'], key=lambda e:(e['start_date'],e['end_date'],e['key']))

def phase_at(day, events, today):
    if day < today: return 'historical', None
    past = [e for e in events if e.get('precision')=='exact' and e['start_date']==e['end_date'] and 0 < (day-event_day(e,'end_date')).days <= POLICY['transition_days']]
    future = [e for e in events if event_day(e,'end_date')>=day]
    event = future[0] if future else None
    # A nearby next main race takes precedence over a full transition restart.
    if past and (not event or (event_day(event)-day).days>POLICY['readiness_window_days']):
        return 'transition', past[-1]
    if not event: return 'general', None
    gap=(event_day(event)-day).days
    exact=event.get('precision')=='exact' and event['start_date']==event['end_date']
    if exact and gap <= POLICY['readiness_window_days']: return 'race_readiness',event
    if gap <= POLICY['specific_window_days']: return 'specific',event
    return 'foundation',event

def segments(period, events, today):
    first,last=event_day(period),event_day(period,'end_date')
    result=[]
    for offset in range((last-first).days+1):
        day=first+timedelta(days=offset);phase,event=phase_at(day,events,today)
        anchor=event['key'] if event else None
        if result and result[-1]['phase']==phase and result[-1]['event_key']==anchor:
            result[-1]['end_date']=day.isoformat();result[-1]['days']+=1
        else:result.append({'start_date':day.isoformat(),'end_date':day.isoformat(),'days':1,'phase':phase,'label':LABELS[phase],'event_key':anchor,'event_title':event.get('title',anchor) if event else None,'event_precision':event.get('precision') if event else None})
    return result

def profile_context(data):
    p=(data.get('profile') or {}).get('data') or {}
    target=(data.get('program_sport') or p.get('target_sport') or '').casefold().strip()
    paddling=any(k in target for k in ('kajak','kayak','kenu','canoe'))
    sport_words={'kajak','kayak'} if any(k in target for k in ('kajak','kayak')) else {'kenu','canoe'} if paddling else {target}
    relevant=[h for h in p.get('sport_history',[]) if h.get('current') and any(w and w in h.get('sport','').casefold() for w in sport_words)]
    beginner=p.get('sport_history_status')=='none' or (bool(relevant) and all(h['level']=='beginner' for h in relevant))
    returning=p.get('interruption')=='returning'
    birth=date.fromisoformat(p['birth_date']) if p.get('birth_date') else None
    today=local_day(data)
    age=today.year-birth.year-((today.month,today.day)<(birth.month,birth.day)) if birth else None
    youth=age is not None and age<18
    participation=p.get('participation','unknown')
    restricted=participation in {'paused','professional_review'}
    notes=[]
    if not p:notes.append('Nincs sportolói profil: az elméleti kezdőterv csökkentett bizonyosságú, személyes dózis nélkül.')
    elif beginner or returning:notes.append('Kezdő vagy visszatérő sportoló: az alapok előrébb kerülnek az intenzív specializációnál.')
    if youth:notes.append('Utánpótláskorú sportoló: konzervatív alapképesség-hangsúly, életkornak megfelelő szakmai felülvizsgálattal.')
    if participation=='adapted' or p.get('constraint_status')=='present':notes.append('Az egyéni korlátozásokhoz igazítandó; a stratégia nem ad mozgás- vagy terhelési engedélyt.')
    if restricted:notes.append('Szünet vagy szakmai felülvizsgálat: a jelenlegi szerepek nem jelentenek edzésengedélyt.')
    return {'paddling':paddling,'beginner_or_returning':beginner or returning or youth,'restricted':restricted,
            'participation':participation,'notes':notes,'profile_available':bool(p)}

def recent_signals(data, today):
    cutoff=datetime.fromisoformat(data['captured_at']);low=cutoff-timedelta(hours=POLICY['acute_signal_hours']);signals=[]
    # Only next-morning self reports can trigger a recovery overlay. High RPE or
    # immediate fatigue during/after a hard session is not by itself maladaptation.
    for r in data.get('feedback',[]):
        observed=r.get('recorded_at')
        if r.get('response_timing')!='NEXT_MORNING' or not observed:continue
        at=datetime.fromisoformat(observed)
        if not low<=at<=cutoff:continue
        fields=[k for k in ('fatigue_score','soreness_score') if r.get(k) is not None and float(r[k])>=POLICY['high_self_report_score']]
        if fields:signals.append({'kind':'self_report_review','source_id':r['id'],'observed_at':observed,'fields':fields})
    for r in data.get('recovery_records',[]):
        if 0 <= (today-date.fromisoformat(r['date'])).days <= 1 and r.get('illness') is True:
            signals.append({'kind':'reported_illness','source_id':r['id'],'observed_at':r['date'],'fields':['illness']})
    return signals

def rank(key, phase, beginner, event):
    foundation={'PERIPHERAL_OXIDATIVE_CAPACITY':90,'MAX_STRENGTH':85,'TECHNICAL_SKILL':80,'MUSCULOSKELETAL_ROBUSTNESS':75,'VO2_CAPACITY':40}
    specific={'VO2_CAPACITY':95,'MUSCULAR_ENDURANCE':90,'POWER_RFD':85,'SPRINT_SPEED_AND_START':80,'HIGH_INTENSITY_AND_ANAEROBIC_PROFILE':75,'PACING_COMPETENCE':65,'TECHNICAL_STABILITY_UNDER_FATIGUE':60}
    if beginner:return {'TECHNICAL_SKILL':100,'MUSCULOSKELETAL_ROBUSTNESS':95,'PERIPHERAL_OXIDATIVE_CAPACITY':90}.get(key,20)
    if phase=='specific':
        profile=(event or {}).get('profile') or {}
        distance=profile.get('distance_value');unit=profile.get('distance_unit')
        if distance is not None and float(distance)*(1000 if unit=='km' else 1)==200:
            specific.update(SPRINT_SPEED_AND_START=110,POWER_RFD=105)
        return specific.get(key,30)
    return foundation.get(key,30)

def enrich(data, draft):
    today=local_day(data);events=main_events(data);ctx=profile_context(data);signals=recent_signals(data,today)
    draft['schema_version']='planning-goal-suggestions-v0.2';draft['rules_version']=RULES
    draft['periodization_inferred']=True
    draft['strategy']={'schema_version':'planning-strategy-v0.1','policy':POLICY,'sources':SOURCES,
        'source_basis':'evidence_informed_product_heuristic','profile_context':ctx,
        'recent_review_signals':signals,'personal_response_model':{'applied':False,'status':'no_prescription_validated_model_connected',
        'reason':'A megfigyelések és leíró összefüggések önmagukban nem igazolnak személyes fejlődési vagy terhelési modellt.'},
        'boundaries_changed':False,'race_dates_changed':False,'workouts_created':False,'dose_selected':False}
    draft['event_titles']={e['key']:e.get('title',e['key']) for e in data['competitions']}
    for macro in draft['macrocycles']:
        children=sorted([p for p in data['periods'] if p.get('parent_id')==macro['macrocycle_period_id'] and p['period_type']=='MESOCYCLE'],key=lambda p:p['start_date'])
        rows=macro['rows'];keys=[r['capability_key'] for r in rows];plan=[]
        for child in children:
            spans=segments(child,events,today)
            future=[s for s in spans if s['phase']!='historical']
            counts=Counter()
            for s in future or spans:counts[s['phase']]+=s['days']
            phase=max(counts,key=counts.get);anchor=next((e for e in events if e['key']==next((s['event_key'] for s in (future or spans) if s['phase']==phase),None)),None)
            ranked=sorted(keys,key=lambda k:(-rank(k,phase,ctx['beginner_or_returning'],anchor),k))
            primary=set(ranked[:POLICY['max_primary_capabilities']]) if phase not in {'race_readiness','transition','historical'} and not ctx['restricted'] else set()
            plan.append({'mesocycle_period_id':child['id'],'title':child['title'],'phase':phase,'label':LABELS[phase],
                         'segments':spans,'confidence':'limited' if not ctx['profile_available'] or not anchor or anchor.get('precision')!='exact' else 'theoretical_starter',
                         'current_overlay':'review_recovery' if signals and child['start_date']<=today.isoformat()<=child['end_date'] else None})
            for row in rows:
                d=next(v for v in row['mesocycle_directives'] if v['mesocycle_period_id']==child['id'])
                if d['origin']=='recorded':continue
                role='primary_development' if row['capability_key'] in primary else 'secondary_development'
                if phase in {'race_readiness','transition','historical'} or ctx['restricted'] or row['role'] in {'maintenance','permitted_decline'}:role='maintenance'
                if ctx['beginner_or_returning'] and row['capability_key'] in {'HIGH_INTENSITY_AND_ANAEROBIC_PROFILE','SPRINT_SPEED_AND_START','POWER_RFD'}:role='maintenance'
                d.update(role=role,origin='strategy_v0_1',rationale=f"{LABELS[phase]}. " + ('A fő fejlesztési hangsúlyok egyike.' if role=='primary_development' else 'Támogató fejlesztés a kiemelt képességek mellett.' if role=='secondary_development' else 'A meglévő képesség megőrzése, új fejlesztési hangsúly nélkül.') + ' Elméleti kezdőjavaslat, a szakaszhatárok és a napi terhelés külön felülvizsgálandók.')
                if signals and child['start_date']<=today.isoformat()<=child['end_date']:d['rationale']+=' Friss állapotjelzés: a következő edzések előtt regenerációs felülvizsgálat szükséges; ez nem a teljes mezociklus átírása.'
        for row in rows:
            if row['origin']=='recorded':continue
            row['role']='primary_development' if any(d['role']=='primary_development' for d in row['mesocycle_directives']) else 'maintenance' if all(d['role']=='maintenance' for d in row['mesocycle_directives']) else 'secondary_development'
            row['origin']='strategy_v0_1';row['rationale']='A megadott cél és versenyprofil alapján kitöltött, mezociklusokra bontott stratégia. Elméleti kezdőterv, nem személyes fejlődési hatásbecslés.'
        macro['strategy_periods']=plan
        macro['primary_focus_limit']=POLICY['max_primary_capabilities']
    return draft
