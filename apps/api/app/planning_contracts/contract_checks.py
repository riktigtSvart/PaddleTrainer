"""Dependency-free checker for this package's explicitly supported schema subset + domain rules.
Not a general JSON Schema implementation. No network, API, database or model mutations.
"""
import json,math,re,hashlib,argparse
from pathlib import Path
from datetime import datetime,date
P=Path(__file__).resolve().parent
TAXONOMY=['STEADY','INTERVAL','RECOVERY','TRANSITION','START','SPRINT','TECHNIQUE','WARMUP','COOLDOWN','MIXED','UNKNOWN']
RULES_VERSION='speed-applicability-0.1';MODEL_ID='PADDLETRAINER_SPEED_SECTION_MEAN';MODEL_VERSION='0.1'
class ContractError(ValueError):pass

def require(condition,message):
 if not condition:raise ContractError(message)
def timestamp(s):
 require(isinstance(s,str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})',s) is not None,'Timestamp must use offset-aware RFC3339 representation')
 try:d=datetime.fromisoformat(s.replace('Z','+00:00').replace('z','+00:00'))
 except (ValueError,AttributeError):raise ContractError('Invalid timestamp')
 require(d.tzinfo is not None and d.utcoffset() is not None,'Timestamp must include UTC offset');return d

def structural(value,schema,document,path='$'):
 if '$ref' in schema:
  ref=schema['$ref'];file,_,fragment=ref.partition('#');target=document
  if file:
   require(file=='integration-contracts.schema.json','Only pinned local schema reference allowed');target=json.loads((P/'schemas'/file).read_text(encoding='utf-8'))
  node=target
  for part in fragment.strip('/').split('/') if fragment else []:node=node[part]
  return structural(value,node,target,path)
 if 'anyOf' in schema:
  for branch in schema['anyOf']:
   try:structural(value,branch,document,path);break
   except ContractError:continue
  else:raise ContractError(path+': no anyOf branch matches')
 if 'const' in schema:require(value==schema['const'],path+': const mismatch')
 if 'enum' in schema:require(value in schema['enum'],path+': enum mismatch')
 types=schema.get('type');types=[types] if isinstance(types,str) else types
 if types:
  def fits(t):
   return {'null':value is None,'boolean':isinstance(value,bool),'string':isinstance(value,str),'integer':isinstance(value,int) and not isinstance(value,bool),'number':isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value),'array':isinstance(value,list),'object':isinstance(value,dict)}[t]
  require(any(fits(t) for t in types),path+': type mismatch')
 if value is None:return
 if isinstance(value,dict):
  require(all(k in value for k in schema.get('required',[])),path+': missing required fields')
  props=schema.get('properties',{})
  if schema.get('additionalProperties') is False:require(set(value)<=set(props),path+': unknown fields '+str(set(value)-set(props)))
  for k,v in value.items():
   if k in props:structural(v,props[k],document,path+'.'+k)
 if isinstance(value,list):
  require(len(value)>=schema.get('minItems',0),path+': array too short');require(len(value)<=schema.get('maxItems',10**9),path+': array too long')
  for i,v in enumerate(value):structural(v,schema.get('items',{}),document,path+f'[{i}]')
 if isinstance(value,str):
  require(len(value)>=schema.get('minLength',0),path+': string too short');require(len(value)<=schema.get('maxLength',10**9),path+': string too long')
  if 'pattern' in schema:require(re.search(schema['pattern'],value) is not None,path+': pattern mismatch')
  if schema.get('format')=='date-time':timestamp(value)
  if schema.get('format')=='date':
   require(re.fullmatch(r'\d{4}-\d{2}-\d{2}',value) is not None,path+': date must be YYYY-MM-DD')
   try:date.fromisoformat(value)
   except ValueError:raise ContractError(path+': invalid date')
 if isinstance(value,(int,float)) and not isinstance(value,bool):
  require(math.isfinite(value),path+': non-finite number')
  if 'minimum' in schema:require(value>=schema['minimum'],path+': below minimum')
  if 'maximum' in schema:require(value<=schema['maximum'],path+': above maximum')
  if 'exclusiveMinimum' in schema:require(value>schema['exclusiveMinimum'],path+': below exclusive minimum')

SUPPORTED_SCHEMA_KEYWORDS={'$schema','$id','$defs','$ref','title','description','type','const','enum','anyOf','properties','required','additionalProperties','items','minItems','maxItems','minimum','maximum','exclusiveMinimum','minLength','maxLength','pattern','format'}
def check_schema_subset():
 def walk(s):
  require(set(s)<=SUPPORTED_SCHEMA_KEYWORDS,'Unsupported schema keywords: '+str(set(s)-SUPPORTED_SCHEMA_KEYWORDS))
  for key in ['properties','$defs']:
   for v in s.get(key,{}).values():walk(v)
  for v in s.get('anyOf',[]):walk(v)
  if 'items' in s:walk(s['items'])
 for f in (P/'schemas').glob('*.json'):walk(json.loads(f.read_text(encoding='utf-8')))

def check_evidence(doc):
 evidence=doc.get('evidence',[]);ids=[e['evidence_id'] for e in evidence];require(len(ids)==len(set(ids)),'Duplicate evidence_id')
 def walk(x):
  if isinstance(x,dict):
   for k,v in x.items():
    if k.endswith('evidence_refs'):require(set(v)<=set(ids),'Unresolved evidence reference')
    if k=='zone_definition_ref' and v is not None:require(v in ids,'Missing zone definition evidence')
    if k!='evidence':walk(v)
  elif isinstance(x,list):
   for v in x:walk(v)
 walk(doc)
 for e in evidence:
  if e['available_at'] is not None:require(timestamp(e['available_at'])>=timestamp(e['collected_at']),'Evidence availability precedes collection')

def intensity(i):
 mode=i['target_mode'];typ=i['type'];point=i['value'];lo=i['lower'];hi=i['upper']
 if mode=='POINT':require(typ not in ['FREE','UNKNOWN'] and point is not None and lo is None and hi is None and i['bounds'] is None,'Point intensity needs value only')
 elif mode=='RANGE':
  require(typ not in ['FREE','UNKNOWN'] and point is None and lo is not None and hi is not None and lo<=hi and i['bounds'] is not None,'Range intensity needs ordered bounds')
  require(lo!=hi or i['bounds']=='CLOSED','Empty open range')
 else:
  require(typ==mode and point is None and lo is None and hi is None and i['bounds'] is None,'FREE/UNKNOWN must not masquerade as numeric zero')
  if mode=='UNKNOWN':require(bool(i['unknown_reason']),'Unknown intensity needs reason')
 values=[v for v in [point,lo,hi] if v is not None]
 if typ=='HR_ZONE':require(i['zone_definition_ref'] is not None and all(float(v).is_integer() and 1<=v<=5 for v in values),'HR zone needs versioned definition and integer zone1..5')
 else:require(i['zone_definition_ref'] is None,'Zone ref only valid for HR_ZONE')
 if typ=='RPE_0_10':require(all(0<=v<=10 for v in values),'RPE outside0..10')
 if typ in ['HR_BPM','PACE_S_PER_KM']:require(all(v>0 for v in values),'Positive physical intensity required')

def validate_plan(plan):
 seen=set()
 def block(b,depth=0):
  require(depth<=12,'Block nesting too deep');require(b['block_id'] not in seen,'Duplicate block_id');seen.add(b['block_id']);intensity(b['intensity'])
  if b['structure']=='SEQUENCE':require(b['children'] and b['duration_s'] is None and b['distance_m'] is None and b['completion_condition']=='CHILDREN','Sequence must be explicitly structural, no double-counted target duration')
  else:
   require(not b['children'] and b['completion_condition']!='CHILDREN','Segment cannot contain children');ds=b['duration_s'];dm=b['distance_m'];c=b['completion_condition']
   if ds is not None and dm is not None:require(c in ['FIRST_REACHED','BOTH_REACHED'],'Dual target needs explicit completion semantics')
   elif ds is not None:require(c=='DURATION','Duration-only segment needs DURATION')
   elif dm is not None:require(c=='DISTANCE','Distance-only segment needs DISTANCE')
   else:require(c=='MANUAL' and bool(b['description']),'Open/manual segment needs explicit instructions')
  for child in b['children']:block(child,depth+1)
  if b['recovery'] is not None:
   r=b['recovery']['block'];require(r['block_type']=='RECOVERY' and r['structure']=='SEGMENT' and r['repeat_count']==1 and r['recovery'] is None,'Inline recovery must be one explicit RECOVERY segment');block(r,depth+1)
 for b in plan['blocks']:block(b)
 require(len(expand_plan(plan,validate=False))<=10000,'Too many expanded occurrences')

def expand_plan(plan,validate=True):
 if validate:validate_contract(plan)
 output=[]
 def walk(b,parent_path):
  for n in range(1,b['repeat_count']+1):
   path=parent_path+[b['block_id']+'@'+str(n)]
   if b['structure']=='SEQUENCE':
    for child in b['children']:walk(child,path)
   else:
    payload=plan['plan_id']+'\n'+str(plan['plan_revision'])+'\n'+json.dumps(path,ensure_ascii=False,separators=(',',':'));oid='occ_'+hashlib.sha256(payload.encode()).hexdigest();output.append({'planned_occurrence_id':oid,'block_id':b['block_id'],'occurrence_path':path,'block_type':b['block_type'],'duration_s':b['duration_s'],'distance_m':b['distance_m'],'completion_condition':b['completion_condition']})
    require(len(output)<=10000,'Too many expanded occurrences')
   if b['recovery'] and (n<b['repeat_count'] or b['recovery']['placement']=='AFTER_EACH_REPETITION'):walk(b['recovery']['block'],path+['RECOVERY_AFTER'])
 for b in plan['blocks']:walk(b,[])
 return output

def applicable(request):
 """Pure, versioned routing policy. No model prediction or capability inference."""
 reasons=[]
 def reason(code,message,severity='LIMITATION'):reasons.append({'code':code,'severity':severity,'message':message})
 status=None;allowed=False
 if request['model_id']!=MODEL_ID or request['model_version']!=MODEL_VERSION:status='UNKNOWN';reason('MODEL_NOT_SUPPORTED','This rule version covers speed model v0.1 only.','BLOCKING')
 elif request['assessment_scope']=='PRE_EXERCISE_PREDICTION':status='NOT_APPLICABLE';reason('OBSERVED_HR_REQUIRED','The current model is retrospective and conditions on observed HR.','BLOCKING')
 elif request['structure']=='SEQUENCE':status='NOT_APPLICABLE';reason('CONTAINER_NOT_MODEL_UNIT','Assess expanded leaf occurrences separately.','BLOCKING')
 elif request['block_type']=='UNKNOWN' or request['block_type_basis']=='UNKNOWN':status='UNKNOWN';reason('BLOCK_TYPE_UNKNOWN','No automatic interpretation of a free-text session label.','BLOCKING')
 elif request['block_type']!='STEADY':status='NOT_APPLICABLE';reason('BLOCK_TYPE_OUTSIDE_SCOPE','This new draft routing policy covers steady leaf sections only.','BLOCKING')
 elif request['assessment_scope']=='BLOCK_TYPE_ROUTING':status='APPLICABLE_WITH_LIMITATIONS';reason('EXECUTION_EVIDENCE_PENDING','Type routing alone does not authorize a numeric replay.');reason('MODEL_DEVELOPMENT_ONLY','No independent validation or planning transfer established.')
 else:
  c=request['checks']
  if request['parameter_set_id'] is None or request['model_artifact_sha256'] is None:status='UNKNOWN';reason('PARAMETER_SET_UNKNOWN','Numeric replay must identify the exact immutable parameter artifact.','BLOCKING')
  elif c['hr_input']=='FAIL' or c['sensor_quality']=='INVALID':status='NOT_APPLICABLE';reason('REQUIRED_SIGNAL_INVALID','Input signal is explicitly invalid.','BLOCKING')
  elif c['hr_input']=='UNKNOWN' or c['boundaries']=='UNRESOLVED' or c['native_time_origin']=='UNKNOWN' or c['geographical_support']=='UNKNOWN' or c['numeric_range']=='UNKNOWN' or c['sensor_quality']=='UNKNOWN' or (request['block_type_basis']=='PLAN_DECLARED' and c['plan_content_at_execution']=='UNKNOWN'):status='UNKNOWN';reason('EXECUTION_EVIDENCE_INCOMPLETE','Required compatibility checks have not resolved.','BLOCKING')
  else:
   status='APPLICABLE_WITH_LIMITATIONS';allowed=True;reason('MODEL_DEVELOPMENT_ONLY','Numeric result is descriptive development evidence, not a planning recommendation.')
   conditions=[(request['block_type_basis']=='PLAN_DECLARED','PLANNED_TYPE_ONLY','Assessed type is prescribed, not independently observed.'),(request['block_type_basis']=='PLAN_DECLARED' and c['plan_content_at_execution']=='UNVERIFIED','HISTORICAL_PLAN_CONTENT_UNVERIFIED','The captured plan content is not verified as the version used at execution.'),(c['boundaries']=='CANDIDATE','CANDIDATE_BOUNDARIES','Phase boundaries remain candidates.'),(c['native_time_origin']=='UNVERIFIED','NATIVE_ORIGIN_UNVERIFIED','Shared native time origin is unverified.'),(c['sensor_quality']=='UNESTABLISHED','HR_QUALITY_NOT_ESTABLISHED','Optical HR acquisition accuracy is not established.'),(c['geographical_support']=='NEW','GEOGRAPHICAL_EXTRAPOLATION','No repeated-geography support for this section.'),(c['numeric_range']=='EXTRAPOLATION','NUMERIC_EXTRAPOLATION','One or more inputs are outside training range.'),(c['environment']!='REPRESENTATIVE','ENVIRONMENT_PROXY_OR_MISSING','Local environment representativeness is not established.')]
   for yes,code,message in conditions:
    if yes:reason(code,message)
 return {'status':status,'numeric_result_allowed':allowed,'result_use':'DESCRIPTIVE_DEVELOPMENT_ONLY' if allowed else 'NONE','reasons':reasons}

def make_decision(**request):
 # Identity is generated only from this constrained ID/string/check payload, not raw biometric data.
 out={'contract_type':'SpeedModelApplicabilityDecision','schema_version':'0.1','rules_version':RULES_VERSION,**request};result=applicable(out);out.update(result);encoded=json.dumps(out,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode();out['decision_id']='decision_'+hashlib.sha256(encoded).hexdigest();return out

def feedback_available_for_prediction(feedback,cutoff):
 return timestamp(feedback['recorded_at'])<=timestamp(cutoff) and bool(feedback['evidence']) and all(e['available_at'] is not None and timestamp(e['available_at'])<=timestamp(cutoff) for e in feedback['evidence'])

def validate_contract(doc):
 name=doc.get('contract_type');require(name in ['WorkoutPlanContract','ExecutedWorkout','SessionFeedback','PlanExecutionComparison','SpeedModelApplicabilityDecision','IntegrationBundle'],'Unknown contract type');schema=json.loads((P/'schemas'/(name+'.schema.json')).read_text(encoding='utf-8'));structural(doc,schema,schema)
 if name=='IntegrationBundle':return validate_bundle(doc)
 check_evidence(doc)
 if name=='WorkoutPlanContract':validate_plan(doc)
 if name=='ExecutedWorkout':
  if doc['end_time'] is not None:require(timestamp(doc['end_time'])>=timestamp(doc['start_time']),'Execution end before start')
  require((doc['plan_ref'] is None)==(doc['plan_link_status']=='UNKNOWN'),'Missing plan identity must be UNKNOWN link')
  ids=[b['executed_block_id'] for b in doc['blocks']];require(len(ids)==len(set(ids)),'Duplicate executed block ID')
  for b in doc['blocks']:
   boundary=b['boundary'];a,z=boundary['start_offset_s'],boundary['end_offset_s']
   if boundary['status']=='UNRESOLVED':require(a is None and z is None,'Unresolved boundaries must not invent numeric offsets')
   else:require(a is not None and z is not None and z>a and boundary['clock_domain']!='UNKNOWN','Known bounds need positive interval and explicit clock')
   if boundary['status']=='VERIFIED':require(doc['native_time_origin_status']=='VERIFIED','Verified physical alignment cannot be derived from unverified native origin')
   for m in b['metrics']:
    expected={'MEAN_HEART_RATE':'BPM','MEAN_SPEED':'M_PER_S','DISTANCE':'METRE','DURATION':'SECOND','CARDIO_LOAD':'SOURCE_NATIVE'}[m['metric_name']];require(m['unit']==expected,'Metric unit mismatch');require((m['status']=='AVAILABLE')==(m['value'] is not None),'Missing metric is null, not zero')
  for s in doc['speed_results']:require(s['executed_block_id'] in ids and math.isclose(s['predicted_mean_speed_mps'],s['native_value']/3.6,abs_tol=1e-9),'Speed result identity/unit conversion mismatch')
 if name=='SpeedModelApplicabilityDecision':
  require(any(v is not None for v in doc['subject'].values()),'Decision needs subject');expected=applicable(doc)
  for k in ['status','numeric_result_allowed','result_use']:require(doc[k]==expected[k],'Decision differs from pinned rules: '+k)
  require([(r['code'],r['severity']) for r in doc['reasons']]==[(r['code'],r['severity']) for r in expected['reasons']],'Decision reason codes differ from pinned rules')
  payload={k:v for k,v in doc.items() if k!='decision_id'};digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest();require(doc['decision_id']=='decision_'+digest,'Decision identity changed without a new immutable assessment')
 if name=='SessionFeedback':
  require((doc['scope']=='BLOCK')==(doc['executed_block_id'] is not None),'Feedback scope mismatch')
  for k in ['wind_effect','waves_effect','overall_exertion','prescription_completion']:
   a=doc[k];require((a['answer_status']=='ANSWERED')==(a['value'] is not None),'Unanswered feedback must be null')
  a=doc['thermal_effect']
  if a['answer_status']=='ANSWERED':require(a['direction'] is not None and a['severity'] is not None and ((a['direction']=='NONE' and a['severity']==0) or (a['direction'] in ['HEAT','COLD'] and a['severity']>0)),'Thermal answer mismatch')
  else:require(a['direction'] is None and a['severity'] is None,'Unknown thermal effect must not become NONE')
 if name=='PlanExecutionComparison':
  for row in doc['rows']:
   for a in row['target_adherence']:
    vals=[a[k] for k in ['inside_s','below_s','above_s','unknown_s','observed_s']]
    if a['status'] in ['NOT_EVALUABLE','NOT_APPLICABLE']:require(all(v is None for v in vals) and a['reasons'],'Non-evaluable adherence needs nulls and reason')
    else:
     require(all(v is not None for v in vals) and math.isclose(sum(vals[:4]),vals[4],abs_tol=1e-6),'Adherence time accounting mismatch')
     if a['status']=='VERIFIED':require(row['alignment_status']=='MATCHED_VERIFIED' and a['endpoint_policy']!='UNKNOWN','Candidate alignment/endpoints cannot imply verified adherence')
 return True

def validate_bundle(bundle):
 plan=bundle['plan'];exe=bundle['executed'];comp=bundle['comparison'];docs=[plan,exe,comp]+bundle['feedback']+bundle['applicability_decisions']
 for d in docs:validate_contract(d);require(d['athlete_id']==plan['athlete_id'],'Cross-athlete evidence join rejected')
 registry={}
 for d in docs:
  for e in d['evidence']:
   require(e['evidence_id'] not in registry or registry[e['evidence_id']]==e,'Conflicting evidence with same global ID');registry[e['evidence_id']]=e
 pref={'plan_id':plan['plan_id'],'plan_revision':plan['plan_revision']};eref={'executed_workout_id':exe['executed_workout_id'],'execution_revision':exe['execution_revision']};require(exe['plan_ref']==pref and comp['plan_ref']==pref and comp['execution_ref']==eref,'Plan/execution revision mismatch')
 occurrences={r['planned_occurrence_id']:r for r in expand_plan(plan)};allblocks={}
 def collect(b):
  allblocks[b['block_id']]=b
  for c in b['children']:collect(c)
  if b['recovery']:collect(b['recovery']['block'])
 for b in plan['blocks']:collect(b)
 observed={b['executed_block_id']:b for b in exe['blocks']};decisions={d['decision_id']:d for d in bundle['applicability_decisions']};require(len(decisions)==len(bundle['applicability_decisions']),'Duplicate decision ID')
 for b in exe['blocks']:
  if b['planned_occurrence_id'] is not None:require(b['planned_occurrence_id'] in occurrences and b['planned_block_id']==occurrences[b['planned_occurrence_id']]['block_id'],'Executed occurrence identity mismatch')
  elif b['planned_block_id'] is not None:require(b['planned_block_id'] in allblocks,'Unknown planned block reference')
 for d in decisions.values():
  require(d['plan_ref']==pref and (d['execution_ref'] is None or d['execution_ref']==eref),'Decision revision mismatch');s=d['subject']
  if s['executed_block_id'] is not None:require(s['executed_block_id'] in observed,'Decision references unknown executed block')
  if s['planned_block_id'] is not None:
   require(s['planned_block_id'] in allblocks,'Decision references unknown planned block')
   if d['block_type_basis']=='PLAN_DECLARED':require(d['block_type']==allblocks[s['planned_block_id']]['block_type'] and d['structure']==allblocks[s['planned_block_id']]['structure'],'Decision subject type mismatch')
  if d['block_type_basis']=='EXECUTION_RECONSTRUCTED':require(s['executed_block_id'] is not None and d['block_type']==observed[s['executed_block_id']]['observed_block_type'] and d['structure']=='SEGMENT','Observed type basis mismatch')
  if s['planned_occurrence_id'] is not None:require(s['planned_occurrence_id'] in occurrences,'Decision occurrence missing')
  if s['planned_occurrence_id'] is not None and s['planned_block_id'] is not None:require(occurrences[s['planned_occurrence_id']]['block_id']==s['planned_block_id'],'Decision occurrence belongs to another block')
  if s['executed_block_id'] is not None and s['planned_occurrence_id'] is not None:require(observed[s['executed_block_id']]['planned_occurrence_id']==s['planned_occurrence_id'],'Decision occurrence differs from observed link')
  if d['assessment_scope']=='EXECUTED_DATA_REPLAY':
   require(d['execution_ref']==eref and s['executed_block_id'] is not None,'Replay decision needs actual executed subject');b=observed[s['executed_block_id']];require(d['checks']['boundaries']==b['boundary']['status'],'Decision boundary claims conflict with actual evidence')
   if d['block_type_basis']=='PLAN_DECLARED':require(d['checks']['plan_content_at_execution']==exe['plan_content_at_execution_status'],'Historical plan content check conflict')
   require(not (d['checks']['native_time_origin']=='VERIFIED' and exe['native_time_origin_status']!='VERIFIED'),'Decision falsely promotes native clock evidence')
   require(not (d['checks']['sensor_quality']=='ESTABLISHED' and exe['hr_acquisition_quality']!='ESTABLISHED'),'Decision falsely promotes sensor quality')
   if exe['hr_acquisition_quality']=='INVALID':require(d['checks']['sensor_quality']=='INVALID','Invalid acquisition quality cannot be hidden by decision')
   if d['checks']['hr_input']=='PASS':require(any(m['metric_name']=='MEAN_HEART_RATE' and m['status']=='AVAILABLE' and m['value']>0 for m in b['metrics']),'PASS HR check needs a nonmissing positive observed HR metric')
 for s in exe['speed_results']:
  require(s['decision_id'] in decisions,'Unresolved applicability decision');d=decisions[s['decision_id']];require(d['numeric_result_allowed'] and d['assessment_scope']=='EXECUTED_DATA_REPLAY' and d['subject']['executed_block_id']==s['executed_block_id'],'Numeric result blocked by applicability decision');require(all(s[k]==d[k] for k in ['model_id','model_version','model_variant','parameter_set_id','model_artifact_sha256']),'Model/parameter artifact identity mismatch')
 for f in bundle['feedback']:require(f['execution_ref']==eref and (f['executed_block_id'] is None or f['executed_block_id'] in observed),'Feedback identity mismatch')
 if comp['coverage']=='COMPLETE':
  require({r['planned_occurrence_id'] for r in comp['rows'] if r['planned_occurrence_id'] is not None}==set(occurrences),'Complete comparison omits plan occurrences')
  require({v for r in comp['rows'] for v in r['executed_block_ids']}==set(observed),'Complete comparison omits observed blocks')
 for row in comp['rows']:
  oid=row['planned_occurrence_id'];require(oid is None or oid in occurrences,'Comparison references nonexistent occurrence');require(set(row['executed_block_ids'])<=set(observed),'Comparison references unknown execution');require(set(row['applicability_decision_ids'])<=set(decisions),'Comparison references unknown decision')
  if row['alignment_status']=='MATCHED_VERIFIED':require(exe['plan_link_status'] in ['EXACT_PROVIDER_ID','MANUAL_CONFIRMED'] and exe['plan_content_at_execution_status']=='VERIFIED' and all(observed[k]['boundary']['status']=='VERIFIED' for k in row['executed_block_ids']) and oid is not None and row['executed_block_ids'],'Candidate evidence cannot imply verified plan alignment')
  if any(a['status']=='VERIFIED' for a in row['target_adherence']):
   require(all(observed[k]['boundary']['status']=='VERIFIED' for k in row['executed_block_ids']) and exe['plan_link_status'] in ['EXACT_PROVIDER_ID','MANUAL_CONFIRMED'] and exe['plan_content_at_execution_status']=='VERIFIED','Verified adherence requires verified plan and boundary evidence')
  if row['alignment_status']=='MISSED':require(oid is not None and not row['executed_block_ids'],'Missed planned occurrence cannot have observed blocks')
  if row['alignment_status']=='UNPLANNED':require(oid is None and row['executed_block_ids'],'Unplanned observation must not invent plan identity')
 return True

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('file',type=Path);args=a.parse_args();check_schema_subset();doc=json.loads(args.file.read_text(encoding='utf-8'));validate_contract(doc);print(json.dumps({'status':'PLANNING_DATA_CONTRACT_VALID','contract_type':doc['contract_type'],'schema_version':doc['schema_version']},indent=2))

# Descriptors for a future adapter, not an ORM migration or automatic conversion.
def describe_legacy_type(value):
 if value in ['RECOVERY','WARMUP','COOLDOWN']:return {'block_type':value,'structure':'SEGMENT','needs_semantic_annotation':False}
 if value=='REPEAT':return {'block_type':'UNKNOWN','structure':'SEQUENCE','needs_semantic_annotation':True}
 return {'block_type':'UNKNOWN','structure':'SEGMENT','needs_semantic_annotation':True}
