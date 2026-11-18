#!/usr/bin/env python3
"""Frozen revision manifest (seed 20261118). Cells are fixed here; each independent session gets its own shuffle."""
import json,random,itertools
SEED=20261118;SESSIONS=5;REPS=10;SAMPLES=3;WARMUPS=2;LIMIT=25
N={'s5000':5000,'s25000':25000,'s100000':100000,'skew100000':100000}
cells=[]
def cell(exp,schema,order,design,method,fraction):
 cells.append(dict(cell=len(cells),exp=exp,schema=schema,order=order,design=design,method=method,fraction=fraction,limit=LIMIT,offset=int(N[schema]*fraction)))
F=[0,.5,.95];pk_designs=['global','global_hash','page_grouped','page_lateral','mv','counter']
# R1: stronger baselines for the product-ID-ordered report, cloned and skewed data.
for s in ['s100000','skew100000']:
 for d,m,f in itertools.product(pk_designs,['offset','keyset'],F):cell('R1_baselines',s,'id',d,m,f)
 for f in F:cell('R1_baselines',s,'id','global_pushdown','keyset',f)
# R2: scale points for the original three designs at the deepest page (100k comes from R1).
for s,d,m in itertools.product(['s5000','s25000'],['global','page_grouped','page_lateral'],['offset','keyset']):cell('R2_scale',s,'id',d,m,.95)
# R3: order by an aggregate; page-first restriction is impossible without precomputed aggregates.
for s,o in [('s100000','orders'),('s100000','rating'),('skew100000','orders')]:
 for d,m,f in itertools.product(['global','mv','counter'],['offset','keyset'],F):cell('R3_aggregate_order',s,o,d,m,f)
# R4: order by a non-unique product column (price) with an ID tie-breaker.
for d,m,f in itertools.product(['global','page_grouped','page_lateral'],['offset','keyset'],[0,.95]):cell('R4_price_order','s100000','price',d,m,f)
sessions=[]
for k in range(SESSIONS):
 rng=random.Random(SEED+k);trials=[dict(cell=c['cell'],rep=r) for c in cells for r in range(REPS)];rng.shuffle(trials)
 for i,t in enumerate(trials):t['index']=i;t['trial']=f's{k}-{i:04d}'
 sessions.append(dict(session=k,seed=SEED+k,trials=trials))
counts=dict(cells=len(cells),sessions=SESSIONS,trials=len(cells)*REPS*SESSIONS,measured_requests=len(cells)*REPS*SESSIONS*SAMPLES)
json.dump(dict(seed=SEED,repetitions_per_session=REPS,samples_per_trial=SAMPLES,warmups_per_cell=WARMUPS,cells=cells,sessions=sessions,counts=counts),open('manifest.json','w'),indent=1)
json.dump(cells,open('results/raw/cells.json','w'))
print(counts)
