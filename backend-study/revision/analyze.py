#!/usr/bin/env python3
"""Audit and analyse the revision collection (independent sessions, stronger baselines, orderings, plans, cost model).
Only a fully accepted collection is analysed. PARTIAL=1 allows a dry run on the sessions completed so far."""
from pathlib import Path
import json,collections,hashlib,os,math,statistics
import numpy as np
X=Path(__file__).resolve().parent;B=X.parent;RAW=X/'results/raw';OUT=X/'results/derived';OUT.mkdir(parents=True,exist_ok=True)
read=lambda p:[json.loads(l) for l in p.read_text().splitlines() if l.strip()]
PARTIAL=os.environ.get('PARTIAL')=='1'
manifest=json.loads((X/'manifest.json').read_text())
if PARTIAL:
 col=json.loads(sorted(RAW.glob('environment-*.json'))[-1].read_text())['collection']
else:
 acc=[x for x in read(RAW/'collections.jsonl') if x['status']=='accepted'];assert len(acc)==1,'need exactly one accepted collection'
 col=acc[0]['collection'];assert hashlib.sha256((X/'manifest.json').read_bytes()).hexdigest()==acc[0]['manifest_sha256'],'manifest changed'
env=json.loads((RAW/f'environment-{col}.json').read_text())
for k,v in env['sources'].items():
 assert hashlib.sha256((X/k).read_bytes()).hexdigest()==v,('measured source changed',k)
batches=[x for x in read(RAW/'batches.jsonl') if x['collection']==col]
for b in batches:assert b['guard_clear'],b
cells=manifest['cells'];S=len(manifest['sessions']);REPS=manifest['repetitions_per_session']
prep=[json.loads(l) for l in (RAW/f'correctness-{col}.txt').read_text().splitlines() if l.startswith('{')]
checks=[x for x in prep if x['type']=='correctness'];assert len(checks)==124 and all(x['status']=='PASS' for x in checks)
assert any(x['type']=='complete' for x in prep)
requests=[x for x in read(RAW/'requests.jsonl') if x['collection']==col]
api={x['id']:x for x in read(RAW/'api.jsonl') if x.get('collection')==col}
assert not [x for x in api.values() if 'error' in x],'API errors'
trials=[x for x in read(RAW/'trials.jsonl') if x['collection']==col]
per=collections.Counter(t['session'] for t in trials)
sessions_done=sorted(k for k,v in per.items() if v==len(cells)*manifest['repetitions_per_session'])
trials=[t for t in trials if t['session'] in sessions_done]
if not PARTIAL:assert sessions_done==list(range(S)) and len(trials)==manifest['counts']['trials']
expected=json.loads((RAW/f'expected-{col}.json').read_text())
# Every request: server provenance, oracle digest, matching treatment.
by_run=collections.defaultdict(list)
for x in requests:
 a=api[x['id']];assert a['rowDigest']==x['rowDigest']==expected[x['schema']][x['order']][f"{x['limit']}:{x['offset']}"]['digest']
 assert all(a[k]==x[k] for k in ['schema','design','method','order','limit','offset','run','phase','step'])
 if x['phase']=='measurement':by_run[x['run']].append((x,a))
# Session starts: each session must have a distinct postmaster start time (independent restarts).
starts=[x for x in read(RAW/'events.jsonl') if x['collection']==col and x['event']=='session-start']
assert len({x['backend']['started'] for x in starts})==len(starts)>=len(sessions_done),'sessions did not restart PostgreSQL'
recs=[]
for t in trials:
 pairs=by_run[t['run']];assert len(pairs)==3 and {x['step'] for x,_ in pairs}=={0,1,2}
 recs.append(dict(cell=t['cell'],session=t['session'],rep=t['rep'],index=t['index'],service=float(np.mean([a['serviceMs'] for _,a in pairs])),db=float(np.mean([a['dbMs'] for _,a in pairs])),client=float(np.mean([x['clientMs'] for x,_ in pairs])),bytes=pairs[0][1]['bytes']))
data=collections.defaultdict(lambda:collections.defaultdict(list))
for r in recs:data[r['cell']][r['session']].append(r)
rng=np.random.default_rng(20261118)
B_RES=10000
def two_stage(cellid,metric='service',idx=None):
 """Pooled mean and two-stage bootstrap draws (sessions with replacement, then trials within each)."""
 ss=sessions_done;arr=np.array([[r[metric] for r in sorted(data[cellid][s],key=lambda r:r['rep'])] for s in ss])
 return arr
def boot_draws(arr,si,ti):
 # arr: sessions x trials; si: (B, S) session picks; ti: (B, S, T) trial picks
 sel=arr[si];return np.take_along_axis(sel,ti,axis=2).mean(axis=(1,2))
nS=len(sessions_done)
SI=rng.integers(0,nS,(B_RES,nS));TI=rng.integers(0,REPS,(B_RES,nS,REPS))
summary=[];draws={}
for c in cells:
 arr=two_stage(c['cell']);assert arr.shape==(nS,REPS),(c,arr.shape)
 d=boot_draws(arr,SI,TI);draws[c['cell']]=d
 sm=arr.mean(axis=1);lo,hi=np.quantile(d,[.025,.975])
 within=[]
 for s in range(nS):
  w=arr[s][rng.integers(0,REPS,(2000,REPS))].mean(axis=1);within.append([float(sm[s]),*map(float,np.quantile(w,[.025,.975]))])
 dbarr=two_stage(c['cell'],'db');cl=two_stage(c['cell'],'client')
 summary.append({**c,'service':[float(arr.mean()),float(lo),float(hi)],'session_means':[float(x) for x in sm],'session_within_ci':within,'between_session_cv':float(sm.std(ddof=1)/sm.mean()) if nS>1 else None,'db':float(dbarr.mean()),'client':float(cl.mean()),'n_trials':int(arr.size)})
def find(**kw):
 m=[s for s in summary if all(s[k]==v for k,v in kw.items())];assert len(m)==1,(kw,len(m));return m[0]
def cid(**kw):return find(**kw)['cell']
def ratio(num,den):
 """Ratio of pooled means; two-stage bootstrap CI (same resamples for both cells); t-interval on per-session log ratios."""
 a,b=find(**num),find(**den);r=a['service'][0]/b['service'][0]
 d=draws[a['cell']]/draws[b['cell']];lo,hi=np.quantile(d,[.025,.975])
 lr=np.log(np.array(a['session_means'])/np.array(b['session_means']))
 tcrit={1:12.706,2:4.303,3:3.182,4:2.776,5:2.571,6:2.447}.get(len(lr)-1,1.96)
 half=tcrit*lr.std(ddof=1)/math.sqrt(len(lr)) if len(lr)>1 else float('nan')
 return dict(ratio=r,boot=[float(lo),float(hi)],t=[float(math.exp(lr.mean()-half)),float(math.exp(lr.mean()+half))],session=[float(x) for x in np.exp(lr)])
K=lambda **kw:dict(order='id',fraction=.95,limit=25,**kw)
ratios={
 'offset_lateral':ratio(K(schema='s100000',design='global',method='offset'),K(schema='s100000',design='page_lateral',method='offset')),
 'offset_grouped':ratio(K(schema='s100000',design='global',method='offset'),K(schema='s100000',design='page_grouped',method='offset')),
 'headline':ratio(K(schema='s100000',design='global',method='offset'),K(schema='s100000',design='page_lateral',method='keyset')),
 'keyset_global_over_offset':ratio(K(schema='s100000',design='global',method='keyset'),K(schema='s100000',design='global',method='offset')),
 'hash_over_global_offset':ratio(K(schema='s100000',design='global_hash',method='offset'),K(schema='s100000',design='global',method='offset')),
 'global_keyset_over_pushdown':ratio(K(schema='s100000',design='global',method='keyset'),K(schema='s100000',design='global_pushdown',method='keyset')),
 'pushdown_over_lateral_keyset':ratio(K(schema='s100000',design='global_pushdown',method='keyset'),K(schema='s100000',design='page_lateral',method='keyset')),
 'mv_offset_over_lateral_offset':ratio(K(schema='s100000',design='mv',method='offset'),K(schema='s100000',design='page_lateral',method='offset')),
 'skew_offset_lateral':ratio(K(schema='skew100000',design='global',method='offset'),K(schema='skew100000',design='page_lateral',method='offset')),
 'skew_headline':ratio(K(schema='skew100000',design='global',method='offset'),K(schema='skew100000',design='page_lateral',method='keyset')),
 'skew_keyset_global_over_offset':ratio(K(schema='skew100000',design='global',method='keyset'),K(schema='skew100000',design='global',method='offset')),
 'orders_mv_offset':ratio(dict(schema='s100000',order='orders',design='global',method='offset',fraction=.95),dict(schema='s100000',order='orders',design='mv',method='offset',fraction=.95)),
 'orders_mv_keyset':ratio(dict(schema='s100000',order='orders',design='global',method='offset',fraction=.95),dict(schema='s100000',order='orders',design='mv',method='keyset',fraction=.95)),
 'rating_mv_keyset':ratio(dict(schema='s100000',order='rating',design='global',method='offset',fraction=.95),dict(schema='s100000',order='rating',design='mv',method='keyset',fraction=.95)),
 'price_offset_lateral':ratio(dict(schema='s100000',order='price',design='global',method='offset',fraction=.95),dict(schema='s100000',order='price',design='page_lateral',method='offset',fraction=.95)),
 'price_headline':ratio(dict(schema='s100000',order='price',design='global',method='offset',fraction=.95),dict(schema='s100000',order='price',design='page_lateral',method='keyset',fraction=.95)),
}
# ---------- plans: repeated executions, shape stability, counters ----------
def nodes(n):
 yield n
 for c in n.get('Plans',[]):yield from nodes(c)
def shape(n):
 return n['Node Type']+'('+','.join(filter(None,[n.get('Relation Name'),n.get('Index Name'),n.get('Join Type'),n.get('Strategy')]))+')['+';'.join(shape(c) for c in n.get('Plans',[]))+']'
PARENT={'products','products_c','stats_mv','inventory','categories'};CHILD={'order_items','reviews'}
plans=collections.defaultdict(list)
for f in sorted(RAW.glob(f'plans-s*-{col}.txt')):
 for l in f.read_text().splitlines():
  if not l.startswith('{'):continue
  x=json.loads(l);p=x['plan'][0];root=p['Plan'];ns=list(nodes(root))
  scan=lambda rels:sum(q.get('Actual Rows',0)*q.get('Actual Loops',1)+q.get('Rows Removed by Filter',0)*q.get('Actual Loops',1) for q in ns if q.get('Relation Name') in rels and 'Scan' in q['Node Type'])
  if x['session'] not in sessions_done:continue
  plans[x['cell']].append(dict(session=x['session'],rep=x['rep'],exec=p['Execution Time'],cost=root['Total Cost'],hits=root.get('Shared Hit Blocks',0),reads=root.get('Shared Read Blocks',0),temp=root.get('Temp Written Blocks',0),parent=scan(PARENT),child=scan(CHILD),products=scan({'products','products_c','stats_mv'}),shape=hashlib.sha1(shape(root).encode()).hexdigest()[:10]))
plan_summary=[]
for c in cells:
 ps=plans[c['cell']]
 if not PARTIAL:assert len(ps)==S*int(env['plan_reps_per_session']),(c,len(ps))
 med=lambda k:float(np.median([p[k] for p in ps])) if ps else None
 q=lambda k:[float(x) for x in np.quantile([p[k] for p in ps],[.25,.75])] if ps else None
 shapes=collections.Counter(p['shape'] for p in ps)
 plan_summary.append({**c,'n_plans':len(ps),'distinct_shapes':len(shapes),'modal_share':(shapes.most_common(1)[0][1]/len(ps)) if ps else None,'exec_median':med('exec'),'exec_iqr':q('exec'),'hits_median':med('hits'),'hits_range':[min(p['hits'] for p in ps),max(p['hits'] for p in ps)] if ps else None,'parent_rows':med('parent'),'child_rows':med('child'),'product_rows':med('products'),'child_rows_range':[min(p['child'] for p in ps),max(p['child'] for p in ps)] if ps else None,'temp_blocks':med('temp'),'cost':med('cost')})
P={p['cell']:p for p in plan_summary}
# ---------- annotated plan excerpts for the reviewer's anomalies ----------
def excerpt(cellid,maxdepth=12):
 for f in sorted(RAW.glob(f'plans-s*-{col}.txt')):
  for l in f.read_text().splitlines():
   if l.startswith('{') and json.loads(l)['cell']==cellid:
    root=json.loads(l)['plan'][0]['Plan'];out=[]
    def walk(n,d):
     if d>maxdepth:return
     s=n['Node Type']+(' '+n['Strategy'] if n.get('Strategy') and n['Node Type']=='Aggregate' else '')+(f" on {n['Relation Name']}" if 'Relation Name' in n else '')+(f" using {n['Index Name']}" if 'Index Name' in n else '')
     out.append(dict(depth=d,node=s,rows=n.get('Actual Rows',0)*n.get('Actual Loops',1),ms=n.get('Actual Total Time'),hits=n.get('Shared Hit Blocks',0),cost=n.get('Total Cost')))
     for c in n.get('Plans',[]):walk(c,d+1)
    walk(root,0);return out
excerpts={name:excerpt(cid(**spec)) for name,spec in {
 'global_offset_s100000':K(schema='s100000',design='global',method='offset'),'global_keyset_s100000':K(schema='s100000',design='global',method='keyset'),
 'global_offset_skew':K(schema='skew100000',design='global',method='offset'),'global_keyset_skew':K(schema='skew100000',design='global',method='keyset'),
 'global_hash_offset_s100000':K(schema='s100000',design='global_hash',method='offset'),'pushdown_skew':K(schema='skew100000',design='global_pushdown',method='keyset'),
 'lateral_offset_s100000':K(schema='s100000',design='page_lateral',method='offset')}.items()}
# The no-index anomaly comes from the follow-up collection: compare its two retained global OFFSET plans.
EXT=B/'extensions/results/raw'
ext_ex={}
for l in next(EXT.glob('plans-tuned-*.txt')).read_text().splitlines():
 if not l.startswith('{'):continue
 x=json.loads(l)
 if x.get('type')=='plan' and x['variant']=='global' and x['method']=='offset' and x['fraction']==.95 and x['schema'] in ('s100000','noidx100000') and x.get('cursor') in ('none',None):
  root=x['plan'][0]['Plan'];ns=list(nodes(root))
  oi=[n for n in ns if n.get('Relation Name')=='order_items'][0];agg=[n for n in ns if n['Node Type']=='Aggregate' and any(c.get('Relation Name')=='order_items' or any(g.get('Relation Name')=='order_items' for g in c.get('Plans',[])) for c in n.get('Plans',[]))][0]
  ext_ex[x['schema']]=dict(exec=x['plan'][0]['Execution Time'],cost=root['Total Cost'],order_items_node=oi['Node Type'],order_items_rows=oi['Actual Rows'],order_items_hits=oi.get('Shared Hit Blocks',0),order_items_ms=oi['Actual Total Time'],agg_ms=agg['Actual Total Time'],root_hits=root.get('Shared Hit Blocks',0))
# ---------- simple fitted cost model: T = a + b*parent_rows + c*child_rows ----------
# Trained on the cloned 100k ID-ordered cells of the index-based designs; validated, without refitting, on the skewed data.
MODEL_DESIGNS=['global','page_grouped','page_lateral','global_pushdown','mv','counter']
def mrows(schema,order='id'):
 return [(c,P[c['cell']],find(cell=c['cell'])) for c in cells if c['schema']==schema and c['order']==order and c['design'] in MODEL_DESIGNS and c['exp']=='R1_baselines']
train=mrows('s100000');test=mrows('skew100000')
Xtr=np.array([[1,p['parent_rows'],p['child_rows']] for _,p,_ in train]);ytr=np.array([s['service'][0] for _,_,s in train])
coef,*_=np.linalg.lstsq(Xtr,ytr,rcond=None)
pred=lambda p:float(coef@[1,p['parent_rows'],p['child_rows']])
def fitstats(rows):
 y=np.array([s['service'][0] for _,_,s in rows]);yh=np.array([pred(p) for _,p,_ in rows])
 big=y>=5  # relative error is uninformative for sub-millisecond cells dominated by the intercept
 return dict(r2=float(1-((y-yh)**2).sum()/((y-y.mean())**2).sum()),mape_ge5ms=float(np.mean(np.abs(yh[big]-y[big])/y[big])),max_abs_ms=float(np.max(np.abs(yh-y))),n=len(rows))
# Session-level coefficient uncertainty: refit on each bootstrap of sessions.
cb=[]
for b in range(2000):
 si=rng.integers(0,nS,nS)
 yb=np.array([np.mean([np.mean([r['service'] for r in data[c['cell']][sessions_done[k]]]) for k in si]) for c,_,_ in train])
 cb.append(np.linalg.lstsq(Xtr,yb,rcond=None)[0])
cb=np.array(cb)
model=dict(coef=[float(x) for x in coef],coef_ci=[[float(x) for x in np.quantile(cb[:,i],[.025,.975])] for i in range(3)],train=fitstats(train),test=fitstats(test),
 points=[dict(schema=c['schema'],design=c['design'],method=c['method'],fraction=c['fraction'],observed=s['service'][0],predicted=pred(p),parent=p['parent_rows'],child=p['child_rows']) for c,p,s in train+test])
# Analytical form for the cloned data: fan-outs f_o, f_r per product; depth d of N products; page L.
fo,fr=10,6;N=100000;L=25;a,b,cc=coef
def analytic(d):
 g_off=a+b*(d*N+L)+cc*(d*N+L)*(fo+fr); pf_off=a+b*(d*N+L)+cc*L*(fo+fr); pf_key=a+b*L+cc*L*(fo+fr)
 return dict(global_offset=g_off,page_first_offset=pf_off,page_first_keyset=pf_key,ratio_offset=g_off/pf_off,ratio_headline=g_off/pf_key)
model['analytic']={str(d):analytic(d) for d in (0,.5,.95)}
# ---------- write cost ----------
wc=[json.loads(l) for l in (RAW/f'writecost-{col}.txt').read_text().splitlines() if l.startswith('{')] if (RAW/f'writecost-{col}.txt').exists() else []
write={}
if wc:
 assert any(x['type']=='complete' for x in wc)
 for mode in ['trigger','no_trigger']:
  v=[x['ms'] for x in wc if x['type']=='write' and x['mode']==mode];write[mode]=dict(mean=statistics.mean(v),median=statistics.median(v),p95=float(np.quantile(v,.95)),n=len(v))
 assert all(x['counter_current'] for x in wc if x['type']=='write' and x['mode']=='trigger')
 for mode in ['refresh','refresh_concurrently']:
  v=[x['ms'] for x in wc if x['type']=='mv_refresh' and x['mode']==mode];write[mode]=dict(mean=statistics.mean(v),min=min(v),max=max(v),n=len(v))
dist={x['schema']:x for x in prep if x['type']=='distribution'}
# drift diagnostic per session
drift=[]
for c in cells:
 for s in sessions_done:
  it=sorted(data[c['cell']][s],key=lambda r:r['index']);h=len(it)//2
  drift.append(dict(cell=c['cell'],session=s,early=statistics.mean(r['service'] for r in it[:h]),late=statistics.mean(r['service'] for r in it[h:])))
res=dict(collection=col,sessions=sessions_done,n_trials=len(recs),n_requests=len(requests),n_measured=sum(x['phase']=='measurement' for x in requests),checks=len(checks),summary=summary,ratios=ratios,plans=plan_summary,excerpts=excerpts,ext_noindex=ext_ex,model=model,write=write,distribution=dist,
 starts=[x['backend'] for x in starts],measurement_window=[next(b['at'] for b in batches if b['stage']=='measurement-s0' and b['event']=='start'),[b['at'] for b in batches if b['stage'].startswith('measurement-s') and b['event']=='end'][-1]])
(OUT/'revision.json').write_text(json.dumps(res,indent=1))
(OUT/'trial-means.json').write_text(json.dumps(recs))
(OUT/'drift.json').write_text(json.dumps(drift))
if not PARTIAL:(OUT/'raw-sha256.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(RAW.glob('*')) if p.is_file()},indent=1))
print('PASS' if not PARTIAL else 'PARTIAL',col,'sessions',sessions_done,'trials',len(recs))
for k,v in ratios.items():print(f"{k:32s} {v['ratio']:9.2f} boot[{v['boot'][0]:.2f},{v['boot'][1]:.2f}] t[{v['t'][0]:.2f},{v['t'][1]:.2f}]")
print('model',model['coef'],model['train'],model['test'])
