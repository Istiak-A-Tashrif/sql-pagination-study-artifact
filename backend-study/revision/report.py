#!/usr/bin/env python3
"""Figures, tables and manuscript values from the revision analysis (results/derived/revision.json)."""
from pathlib import Path
import json,math
import numpy as np
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator,FixedFormatter,NullLocator
from matplotlib.patches import FancyBboxPatch
X=Path(__file__).resolve().parent;B=X.parent;OUT=X/'results/derived';FIG=B/'manuscript/figures'
R=json.loads((OUT/'revision.json').read_text())
for _s in R['summary']:
 if _s['between_session_cv'] is None:_s['between_session_cv']=0.0  # partial dry runs only
S=R['summary'];PL={p['cell']:p for p in R['plans']}
def find(**kw):
 m=[s for s in S if all(s[k]==v for k,v in kw.items())];assert len(m)==1,(kw,len(m));return m[0]
LBL={'global':'Global aggregation','global_hash':'Global, hash-aggregated','global_pushdown':'Global, cursor pushed down','page_grouped':'Page-first grouped','page_lateral':'Page-first lateral','mv':'Materialized view','counter':'Counter columns'}
SH={'global':'Global','global_hash':'Global hash','global_pushdown':'Global pushdown','page_grouped':'PF grouped','page_lateral':'PF lateral','mv':'View','counter':'Counters'}
COL={'global':'#000000','global_hash':'#7F7F7F','global_pushdown':'#CC79A7','page_grouped':'#0072B2','page_lateral':'#D55E00','mv':'#009E73','counter':'#E69F00'}
MK={'global':'o','global_hash':'D','global_pushdown':'P','page_grouped':'s','page_lateral':'^','mv':'v','counter':'X'}
LS={'global_hash':'--','global_pushdown':':'}
def sig(x,n=2):
 """Round to n significant figures for quoted ratios."""
 if x==0 or not math.isfinite(x):return str(x)
 d=n-int(math.floor(math.log10(abs(x))))-1;v=round(x,d)
 return f'{v:,.0f}' if d<=0 else f'{v:.{d}f}'
def ms(x):
 return f'{x:.2f}' if x<10 else (f'{x:.1f}' if x<100 else f'{x:.0f}')
fmt=lambda a:f'{ms(a[0])} [{ms(a[1])}, {ms(a[2])}]'
def rfmt(r):return f"{sig(r['ratio'])} [{sig(r['boot'][0])}, {sig(r['boot'][1])}]"
plt.rcParams.update({'font.family':'Times New Roman','font.size':9,'pdf.fonttype':42,'axes.spines.top':False,'axes.spines.right':False})
def save(fig,name):
 fig.savefig(FIG/(name+'.pdf'),bbox_inches='tight');fig.savefig(FIG/(name+'.png'),dpi=300,bbox_inches='tight');plt.close(fig)
def logy(ax,lo,hi):
 ax.set_yscale('log');ticks=[t for t in [0.01,0.03,0.1,0.3,1,3,10,30,100,300,1000] if lo<=t<=hi]
 ax.yaxis.set_major_locator(FixedLocator(ticks));ax.yaxis.set_major_formatter(FixedFormatter([f'{t:g}' for t in ticks]));ax.yaxis.set_minor_locator(NullLocator());ax.set_ylim(lo,hi)
def series(ax,xs,cells_,d,label=True):
 m=np.array([c['service'] for c in cells_]);col=COL[d]
 for x,c in zip(xs,cells_):  # individual session means, drawn behind the pooled point
  ax.scatter([x]*len(c['session_means']),c['session_means'],s=7,color=col,alpha=.35,lw=0,zorder=2)
 ax.plot(xs,m[:,0],ls=LS.get(d,'-'),color=col,lw=1,zorder=3)
 ax.errorbar(xs,m[:,0],yerr=[m[:,0]-m[:,1],m[:,2]-m[:,0]],fmt=MK[d],mfc='white',mec=col,color=col,ms=5,capsize=3,elinewidth=1,zorder=4,label=LBL[d] if label else None)
# ---------- Figure 2: scale ----------
fig,axes=plt.subplots(1,2,figsize=(7.1,3.0),sharey=True)
for ax,m in zip(axes,['offset','keyset']):
 for d in ['global','page_grouped','page_lateral']:
  cs=[find(schema=s,order='id',design=d,method=m,fraction=.95) for s in ['s5000','s25000','s100000']]
  series(ax,[5000,25000,100000],cs,d)
 ax.set_xscale('log');ax.xaxis.set_major_locator(FixedLocator([5000,25000,100000]));ax.xaxis.set_major_formatter(FixedFormatter(['5,000','25,000','100,000']));ax.xaxis.set_minor_locator(NullLocator())
 ax.set_xlim(3500,140000);ax.set_title(m.upper()+' (95% depth, 25 rows)');ax.set_xlabel('Products in dataset (log scale)');ax.grid(alpha=.25,which='major')
logy(axes[0],0.1,1000);axes[0].set_ylabel('API service time, ms (log scale)');axes[0].legend(fontsize=8,frameon=False,loc='upper left')
fig.tight_layout();save(fig,'scale')
# ---------- Figure 3: depth, all ID-ordered designs ----------
fig,axes=plt.subplots(1,2,figsize=(7.1,3.4),sharey=True)
pos=[0,1,2]
for ax,m in zip(axes,['offset','keyset']):
 for d in ['global','global_hash','global_pushdown','page_grouped','page_lateral','mv','counter']:
  try:cs=[find(schema='s100000',order='id',design=d,method=m,fraction=f) for f in (0,.5,.95)]
  except AssertionError:continue
  off={'global':-.12,'global_hash':-.08,'global_pushdown':-.04,'page_grouped':0,'page_lateral':.04,'mv':.08,'counter':.12}[d]
  series(ax,[p+off for p in pos],cs,d)
 ax.set_xticks(pos,['0% (first page)','50%','95%']);ax.set_xlim(-.4,2.4);ax.set_xlabel('Product positions skipped before the page');ax.set_title(m.upper()+' (100,000 products, 25 rows)');ax.grid(alpha=.25,axis='y')
logy(axes[0],0.03,1000);axes[0].set_ylabel('API service time, ms (log scale)')
h,l=[],[]
for ax in axes:
 for a,b in zip(*ax.get_legend_handles_labels()):
  if b not in l:h.append(a);l.append(b)
fig.legend(h,l,loc='lower center',ncol=4,fontsize=8,frameon=False,bbox_to_anchor=(.5,-.08));fig.tight_layout(rect=(0,.08,1,1));save(fig,'depth')
# ---------- Figure 4: cost model ----------
M=R['model'];fig,ax=plt.subplots(figsize=(3.6,3.3))
for pt in M['points']:
 tr=pt['schema']=='s100000';ax.scatter(pt['predicted'],pt['observed'],marker=MK[pt['design']],s=26,facecolor=COL[pt['design']] if tr else 'white',edgecolor=COL[pt['design']],lw=1,zorder=3)
lim=[0.03,1000];ax.plot(lim,lim,color='#555555',lw=.8);ax.fill_between(lim,[v/2 for v in lim],[v*2 for v in lim],color='#DDDDDD',alpha=.5,lw=0)
ax.set_xscale('log');logy(ax,*lim);ax.xaxis.set_major_locator(FixedLocator([0.1,1,10,100,1000]));ax.xaxis.set_major_formatter(FixedFormatter(['0.1','1','10','100','1000']));ax.xaxis.set_minor_locator(NullLocator());ax.set_xlim(*lim)
ax.set_xlabel('Predicted service time, ms');ax.set_ylabel('Observed service time, ms');ax.grid(alpha=.25)
from matplotlib.lines import Line2D
hs=[Line2D([],[],marker=MK[d],ls='',mfc=COL[d],mec=COL[d],label=LBL[d]) for d in ['global','global_pushdown','page_grouped','page_lateral','mv','counter']]
hs+=[Line2D([],[],marker='o',ls='',mfc='#444444',mec='#444444',label='Cloned (fitted)'),Line2D([],[],marker='o',ls='',mfc='white',mec='#444444',label='Skewed (held out)')]
ax.legend(handles=hs,fontsize=6.5,frameon=False,loc='upper left');fig.tight_layout();save(fig,'model')
# ---------- Figure 1: informative schematic ----------
def rows_at(d,m='offset'):
 p=PL[find(schema='s100000',order='id',design=d,method=m,fraction=.95)['cell']];return p['product_rows'],p['child_rows']
fig,ax=plt.subplots(figsize=(7.2,4.4));ax.set_xlim(0,100);ax.set_ylim(-8,100);ax.axis('off')
spec=[('Global\naggregation','global',['Aggregate all order\nitems and reviews\nby product','Join to products','ORDER BY, then\nOFFSET or keyset,\nLIMIT 25'],'All orderings'),
 ('Page-first\ngrouped','page_grouped',['Select the 25-row\nproduct page\n(OFFSET or keyset)','GROUP BY over child\nrows joined to\nthose 25 products','Join aggregates\nto the page'],'Product-column\norderings only'),
 ('Page-first\nlateral','page_lateral',['Select the 25-row\nproduct page\n(OFFSET or keyset)','Per product: indexed\nCOUNT / AVG\nsubqueries','Join aggregates\nto the page'],'Product-column\norderings only'),
 ('Precomputed\n(view or\ncounters)','mv',['Aggregates stored\nper product (refresh\nor row triggers)','Select the 25-row\npage from the stored\naggregates (indexed)','Join the page to\nproduct details'],'All orderings;\nwrite or staleness cost')]
ax.text(23,97,'Steps (same columns, same rows for each ordering)',fontsize=8,style='italic')
ax.text(80,97,'Rows read, 95% depth, OFFSET',fontsize=8,style='italic',ha='center')
ax.text(80,93.5,'products        child rows',fontsize=7,ha='center',color='#444444')
for r,(title,d,boxes,scope) in enumerate(spec):
 y=73-r*23;col=COL[d];ax.text(0,y+8,title,fontsize=8.5,fontweight='bold',color=col,va='center')
 ax.text(0,y-1.5,scope,fontsize=6.5,color='#444444',va='top')
 for i,t in enumerate(boxes):
  x=13+i*19.5;ax.add_patch(FancyBboxPatch((x,y),17,16,boxstyle='round,pad=0.4',fc='white',ec=col,lw=1.3));ax.text(x+8.5,y+8,t,ha='center',va='center',fontsize=6.6)
  if i<2:ax.annotate('',xy=(x+19.3,y+8),xytext=(x+17.6,y+8),arrowprops=dict(arrowstyle='->',color=col,lw=1))
 pr,ch=rows_at(d);ax.text(74,y+8,f'{pr:,.0f}',fontsize=8,ha='center',va='center');ax.text(87,y+8,f'{ch:,.0f}',fontsize=8,ha='center',va='center',fontweight='bold' if ch>10000 else 'normal')
ax.text(80,-6,'Median of 15 EXPLAIN ANALYZE executions; 100,000 products, ID order.',fontsize=6.5,ha='center',color='#444444')
save(fig,'strategies')
# ---------- tables ----------
V={}
def tbl(header,rows):return '| '+' | '.join(header)+' |\n|'+'|'.join(['---' if i<2 else '---:' for i in range(len(header))])+'|\n'+''.join('| '+' | '.join(r)+' |\n' for r in rows)
order_d=['global','global_hash','global_pushdown','page_grouped','page_lateral','mv','counter']
rows=[]
for d in order_d:
 for m in ['offset','keyset']:
  try:c=find(schema='s100000',order='id',design=d,method=m,fraction=.95)
  except AssertionError:continue
  sk=find(schema='skew100000',order='id',design=d,method=m,fraction=.95)
  rows.append([SH[d],m.upper(),fmt(sk['service']),f"{sk['service'][0]/c['service'][0]:.2f}",f"{100*c['between_session_cv']:.0f}%"])
V['rev_table_main']=tbl(['Design','Method','Skewed data, ms [95% CI]','Skewed / cloned','Cloned session CV'],rows)
r=R['ratios']
PRI=json.loads((B/'results/derived/manuscript-values.json').read_text());EXT=json.loads((B/'extensions/results/derived/ext-values.json').read_text())
rr=[['Global OFFSET / PF lateral OFFSET','Placement',rfmt(r['offset_lateral']),f"{sig(r['offset_lateral']['t'][0])}–{sig(r['offset_lateral']['t'][1])}",sig(float(PRI['ratio_offset']))],
 ['Global OFFSET / PF lateral keyset','Placement, pagination',rfmt(r['headline']),f"{sig(r['headline']['t'][0])}–{sig(r['headline']['t'][1])}",sig(float(PRI['ratio_headline']))],
 ['Same, skewed data','Placement, pagination',rfmt(r['skew_headline']),f"{sig(r['skew_headline']['t'][0])}–{sig(r['skew_headline']['t'][1])}",sig(float(EXT['ext_ratio_skew']))],
 ['Global keyset / Global pushdown keyset','Predicate placement',rfmt(r['global_keyset_over_pushdown']),f"{sig(r['global_keyset_over_pushdown']['t'][0])}–{sig(r['global_keyset_over_pushdown']['t'][1])}",'–'],
 ['Price order: Global OFFSET / PF lateral OFFSET','Placement',rfmt(r['price_offset_lateral']),f"{sig(r['price_offset_lateral']['t'][0])}–{sig(r['price_offset_lateral']['t'][1])}",'–'],
 ['Order-count order: Global OFFSET / View keyset','Precomputation, pagination',rfmt(r['orders_mv_keyset']),f"{sig(r['orders_mv_keyset']['t'][0])}–{sig(r['orders_mv_keyset']['t'][1])}",'–']]
V['rev_table_ratios']=tbl(['Contrast','Changes','Ratio [95% CI]','Session t interval','Earlier session'],rr)
# merged plan table (replaces former Tables 2 and 3)
pr=[]
for d,m,fs in [('global','offset',(0,.5,.95)),('global','keyset',(0,.95)),('global_pushdown','keyset',(0,.95)),('page_lateral','offset',(0,.95)),('page_lateral','keyset',(0,.95)),('mv','offset',(.95,)),('mv','keyset',(.95,))]:
 for f in fs:
  c=find(schema='s100000',order='id',design=d,method=m,fraction=f);p=PL[c['cell']]
  pr.append([SH[d],m.upper(),f'{int(f*100)}%',f"{p['product_rows']:,.0f}",f"{p['child_rows']:,.0f}",f"{p['hits_median']:,.0f}",f"{p['distinct_shapes']}"])
V['rev_table_plans']=tbl(['Design','Method','Depth','Product-side rows','Child rows','Shared hits','Shapes /15'],pr)
# orderings table
orows=[]
for sch,o,lab in [('s100000','price','Price (non-unique)'),('s100000','orders','Order count'),('s100000','rating','Mean rating'),('skew100000','orders','Order count, skewed')]:
 ds=['global','page_grouped','page_lateral'] if o=='price' else ['global','mv','counter']
 for d in ds:
  vals=[]
  for m in ['offset','keyset']:
   for f in (0,.95):vals.append(ms(find(schema=sch,order=o,design=d,method=m,fraction=f)['service'][0]))
  orows.append([lab,SH[d],*vals])
V['rev_table_orders']=tbl(['Ordering','Design','OFFSET 0%','OFFSET 95%','Keyset 0%','Keyset 95%'],orows)
w=R['write']
if w:
 V['rev_table_write']=tbl(['Operation (100,000 products)','Mean, ms','Median, ms','95th percentile or range, ms'],[
  ['Insert one order item and one review, no triggers',f"{w['no_trigger']['mean']:.2f}",f"{w['no_trigger']['median']:.2f}",f"{w['no_trigger']['p95']:.2f}"],
  ['Same, counter triggers recompute both aggregates',f"{w['trigger']['mean']:.2f}",f"{w['trigger']['median']:.2f}",f"{w['trigger']['p95']:.2f}"],
  ['REFRESH MATERIALIZED VIEW',f"{w['refresh']['mean']:.0f}",'–',f"{w['refresh']['min']:.0f}–{w['refresh']['max']:.0f}"],
  ['REFRESH MATERIALIZED VIEW CONCURRENTLY',f"{w['refresh_concurrently']['mean']:.0f}",'–',f"{w['refresh_concurrently']['min']:.0f}–{w['refresh_concurrently']['max']:.0f}"]])
# annotated plan excerpt for the skewed keyset/OFFSET anomaly: keep the review and order-item branches
def ex_rows(name,keep):
 out=[]
 for n in R['excerpts'][name]:
  if any(k in n['node'] for k in keep):out.append(n)
 return out
ann=[]
def short(n):
 t=n['node'].replace('Aggregate Hashed','HashAggregate').replace('Aggregate Sorted','GroupAggregate')
 t=t.split(' using ')[0]+(' (index)' if ' using ' in t else '');return t
for name,lab in [('global_offset_skew','OFFSET'),('global_keyset_skew','Keyset')]:
 ns=R['excerpts'][name];keep=[]
 for i,n in enumerate(ns):
  if n['depth']==0 or 'on reviews' in n['node'] or 'on order_items' in n['node']:keep.append(n)
  elif 'Aggregate' in n['node'] and i+1<len(ns) and any(k in ns[j]['node'] for j in range(i+1,min(i+4,len(ns))) for k in ('on reviews','on order_items')):keep.append(n)
 for n in keep:ann.append([lab,short(n),f"{n['rows']:,.0f}",f"{n['ms']:.0f}",f"{n['hits']:,.0f}"])
V['rev_table_excerpt']=tbl(['Plan','Node','Rows','Time, ms','Shared hits'],ann)
# scalars
g=lambda **kw:find(**kw)['service']
c95=lambda d,m,sch='s100000',o='id',f=.95:find(schema=sch,order=o,design=d,method=m,fraction=f)
V.update({
 'rev_collection':R['collection'],'rev_trials':f"{R['n_trials']:,}",'rev_requests':f"{R['n_measured']:,}",'rev_checks':str(R['checks']),'rev_sessions':str(len(R['sessions'])),
 'rev_g_off':fmt(c95('global','offset')['service']),'rev_g_key':fmt(c95('global','keyset')['service']),'rev_l_off':fmt(c95('page_lateral','offset')['service']),'rev_l_key':fmt(c95('page_lateral','keyset')['service']),
 'rev_gr_off':fmt(c95('page_grouped','offset')['service']),'rev_h_off':fmt(c95('global_hash','offset')['service']),'rev_h_off0':ms(c95('global_hash','offset',f=0)['service'][0]),'rev_g_off0':ms(c95('global','offset',f=0)['service'][0]),
 'rev_pd_key':fmt(c95('global_pushdown','keyset')['service']),'rev_pd_key0':ms(c95('global_pushdown','keyset',f=0)['service'][0]),'rev_pd_key_skew':ms(c95('global_pushdown','keyset','skew100000')['service'][0]),
 'rev_mv_off':ms(c95('mv','offset')['service'][0]),'rev_mv_key':ms(c95('mv','keyset')['service'][0]),'rev_ct_off':ms(c95('counter','offset')['service'][0]),'rev_ct_key':ms(c95('counter','keyset')['service'][0]),
 'rev_ratio_offset':sig(r['offset_lateral']['ratio']),'rev_ratio_offset_ci':f"{sig(r['offset_lateral']['boot'][0])}–{sig(r['offset_lateral']['boot'][1])}",
 'rev_ratio_headline':sig(r['headline']['ratio']),'rev_ratio_headline_ci':f"{sig(r['headline']['boot'][0])}–{sig(r['headline']['boot'][1])}",
 'rev_ratio_headline_t':f"{sig(r['headline']['t'][0])}–{sig(r['headline']['t'][1])}",'rev_ratio_offset_t':f"{sig(r['offset_lateral']['t'][0])}–{sig(r['offset_lateral']['t'][1])}",
 'rev_ratio_offset_sessions':', '.join(sig(x) for x in r['offset_lateral']['session']),'rev_ratio_headline_sessions':', '.join(sig(x) for x in r['headline']['session']),
 'rev_hash_ratio':sig(r['hash_over_global_offset']['ratio']),'rev_pushdown_ratio':sig(r['global_keyset_over_pushdown']['ratio']),'rev_pd_over_lat':sig(r['pushdown_over_lateral_keyset']['ratio']),
 'rev_mv_over_lat':sig(r['mv_offset_over_lateral_offset']['ratio']),'rev_skew_key_over_off':sig(r['skew_keyset_global_over_offset']['ratio'],3),'rev_skew_key_over_off_t':f"{r['skew_keyset_global_over_offset']['t'][0]:.2f}–{r['skew_keyset_global_over_offset']['t'][1]:.2f}",'rev_skew_key_over_off_ci':f"{sig(r['skew_keyset_global_over_offset']['boot'][0],3)}–{sig(r['skew_keyset_global_over_offset']['boot'][1],3)}",
 'rev_key_over_off':sig(r['keyset_global_over_offset']['ratio'],3),'rev_key_over_off_ci':f"{sig(r['keyset_global_over_offset']['boot'][0],3)}–{sig(r['keyset_global_over_offset']['boot'][1],3)}",
 'rev_orders_mv_off':sig(r['orders_mv_offset']['ratio']),'rev_orders_mv_key':sig(r['orders_mv_keyset']['ratio']),'rev_rating_mv_key':sig(r['rating_mv_keyset']['ratio']),
 'rev_price_off':sig(r['price_offset_lateral']['ratio']),'rev_price_head':sig(r['price_headline']['ratio']),
 'rev_go_orders':ms(c95('global','offset',o='orders')['service'][0]),'rev_go_orders0':ms(c95('global','offset',o='orders',f=0)['service'][0]),'rev_gk_orders':ms(c95('global','keyset',o='orders')['service'][0]),
 'rev_mv_orders_off':ms(c95('mv','offset',o='orders')['service'][0]),'rev_mv_orders_key':ms(c95('mv','keyset',o='orders')['service'][0]),
 'rev_g_off_skew':ms(c95('global','offset','skew100000')['service'][0]),'rev_g_key_skew':ms(c95('global','keyset','skew100000')['service'][0]),
 'rev_cv_max':f"{100*max(s['between_session_cv'] for s in S):.0f}",'rev_cv_g':f"{100*c95('global','offset')['between_session_cv']:.0f}",'rev_cv_lk':f"{100*c95('page_lateral','keyset')['between_session_cv']:.0f}",
 'rev_shapes_unstable':str(sum(p['distinct_shapes']>1 for p in R['plans'])),'rev_cells':str(len(S)),
 'rev_m_a':f"{M['coef'][0]:.2f}",'rev_m_b':f"{M['coef'][1]*1000:.3f}",'rev_m_c':f"{M['coef'][2]*1000:.3f}",
 'rev_m_b_ci':f"{M['coef_ci'][1][0]*1000:.3f}–{M['coef_ci'][1][1]*1000:.3f}",'rev_m_c_ci':f"{M['coef_ci'][2][0]*1000:.3f}–{M['coef_ci'][2][1]*1000:.3f}",
 'rev_m_r2_train':f"{M['train']['r2']:.3f}",'rev_m_r2_test':f"{M['test']['r2']:.3f}",'rev_m_mape_train':f"{100*M['train']['mape_ge5ms']:.0f}",'rev_m_mape_test':f"{100*M['test']['mape_ge5ms']:.0f}",
 'rev_m_an_offset':sig(M['analytic']['0.95']['ratio_offset']),'rev_m_an_head':sig(M['analytic']['0.95']['ratio_headline']),'rev_m_an_g':ms(M['analytic']['0.95']['global_offset']),'rev_m_an_pf':ms(M['analytic']['0.95']['page_first_offset']),
})
pts={(p['schema'],p['design'],p['method'],p['fraction']):p for p in M['points']}
gs=pts[('skew100000','global','offset',.95)];V['rev_m_skew_g_pred']=ms(gs['predicted']);V['rev_m_skew_g_obs']=ms(gs['observed'])
if not w:V.update({k:'PENDING' for k in ['rev_table_write','rev_w_trig','rev_w_plain','rev_w_refresh','rev_w_refresh_c']})
if w:V.update({'rev_w_trig':f"{w['trigger']['mean']:.2f}",'rev_w_plain':f"{w['no_trigger']['mean']:.2f}",'rev_w_refresh':f"{w['refresh']['mean']:.0f}",'rev_w_refresh_c':f"{w['refresh_concurrently']['mean']:.0f}"})
dd=R['distribution'];V.update({'rev_corr_clone':f"{[c for c in dd['s100000']['correlation'] if c['tablename']=='reviews'][0]['correlation']:.3f}",'rev_corr_skew':f"{[c for c in dd['skew100000']['correlation'] if c['tablename']=='reviews'][0]['correlation']:.3f}",'rev_distinct_orders':str(dd['s100000']['fanout']['distinct_order_counts']),'rev_distinct_prices':f"{dd['s100000']['fanout']['distinct_prices']:,}"})
ne=R['ext_noindex'];V.update({'ni_idx_hits':f"{ne['s100000']['order_items_hits']:,}",'ni_seq_hits':f"{ne['noidx100000']['order_items_hits']:,}",'ni_idx_agg':f"{ne['s100000']['agg_ms']:.0f}",'ni_seq_agg':f"{ne['noidx100000']['agg_ms']:.0f}",'ni_idx_cost':f"{ne['s100000']['cost']:,.0f}",'ni_seq_cost':f"{ne['noidx100000']['cost']:,.0f}"})
# keyset shared hits vs OFFSET (cloned) for the second anomaly
V['rev_hits_g_off']=f"{PL[c95('global','offset')['cell']]['hits_median']:,.0f}";V['rev_hits_g_key']=f"{PL[c95('global','keyset')['cell']]['hits_median']:,.0f}"
V['rev_m_n']=str(M['train']['n'])
uns=[p for p in R['plans'] if p['distinct_shapes']>1]
V['rev_shapes_list']='; '.join(f"{LBL[p['design']].lower()} {p['method'].upper()} {p['order']} order, {p['schema']}, {int(p['fraction']*100)}% ({p['distinct_shapes']} shapes)" for p in uns) or 'none'
V['rev_hash_temp']=f"{PL[c95('global_hash','offset')['cell']]['temp_blocks']:,.0f}"
V['rev_cost_g']=f"{PL[c95('global','offset')['cell']]['cost']:,.0f}";V['rev_cost_h']=f"{PL[c95('global_hash','offset')['cell']]['cost']:,.0f}"
inside=lambda key,val:'inside' if r[key]['boot'][0]<=val<=r[key]['boot'][1] else 'outside'
V['rev_prior_offset_inside']=inside('offset_lateral',float(PRI['ratio_offset']));V['rev_prior_head_inside']=inside('headline',float(PRI['ratio_headline']))
both=V['rev_prior_offset_inside']==V['rev_prior_head_inside']
V['rev_prior_sentence']=(f"both lie {V['rev_prior_offset_inside']} these intervals" if both else f"lie {V['rev_prior_offset_inside']} and {V['rev_prior_head_inside']} these intervals respectively")
V['rev_prior_offset']=PRI['ratio_offset'];V['rev_prior_head']=PRI['ratio_headline']
V['rev_price_g0']=ms(c95('global','offset',o='price',f=0)['service'][0]);V['rev_price_l_off']=ms(c95('page_lateral','offset',o='price')['service'][0]);V['rev_price_l_key']=ms(c95('page_lateral','keyset',o='price')['service'][0]);V['rev_price_g']=ms(c95('global','offset',o='price')['service'][0])
V['rev_diff_head']=ms(c95('global','offset')['service'][0]-c95('page_lateral','keyset')['service'][0])
V['rev_skew_g_key']=ms(c95('global','keyset','skew100000')['service'][0])
V['rev_ct_orders_off']=ms(c95('counter','offset',o='orders')['service'][0]);V['rev_ct_orders_key']=ms(c95('counter','keyset',o='orders')['service'][0])
V['rev_go_skew_orders']=ms(c95('global','offset','skew100000',o='orders')['service'][0])
# ---------- supplementary material ----------
def full_table():
 rows=[]
 for c in S:
  p=PL[c['cell']]
  rows.append([c['exp'].split('_',1)[0],c['schema'],c['order'],SH[c['design']],c['method'].upper(),f"{int(c['fraction']*100)}%",fmt(c['service']),f"{100*c['between_session_cv']:.0f}%",f"{p['child_rows']:,.0f}",f"{p['distinct_shapes']}"])
 return tbl(['Exp.','Schema','Order','Design','Pagination','Depth','Service ms [95% CI]','Session CV','Child rows','Shapes'],rows)
def plan_text(name,title):
 lines=[f'**{title}**','','```']
 for n in R['excerpts'][name]:lines.append(f"{'  '*n['depth']}{n['node']}  rows={n['rows']:,.0f}  time={n['ms']:.1f} ms  hits={n['hits']:,}  est.cost={n['cost']:,.0f}")
 return '\n'.join(lines+['```',''])
mp=tbl(['Schema','Design','Pagination','Depth','Product-side rows','Child rows','Observed ms','Predicted ms'],[[p['schema'],LBL[p['design']],p['method'].upper(),f"{int(p['fraction']*100)}%",f"{p['parent']:,.0f}",f"{p['child']:,.0f}",ms(p['observed']),ms(p['predicted'])] for p in M['points']])
V['supp_full_table']=full_table();V['supp_model_table']=mp.replace('| Global aggregation |','| Global |')
V['supp_plans']='\n'.join([plan_text('global_offset_s100000','S8.1 Global aggregation, OFFSET, cloned data, 95% depth'),plan_text('global_keyset_s100000','S8.2 Global aggregation, keyset, cloned data, 95% depth'),plan_text('global_offset_skew','S8.3 Global aggregation, OFFSET, skewed data, 95% depth'),plan_text('global_keyset_skew','S8.4 Global aggregation, keyset, skewed data, 95% depth'),plan_text('global_hash_offset_s100000','S8.5 Global, hash-aggregated, OFFSET, cloned data, 95% depth'),plan_text('pushdown_skew','S8.6 Global, cursor pushed down, keyset, skewed data, 95% depth'),plan_text('lateral_offset_s100000','S8.7 Page-first lateral, OFFSET, cloned data, 95% depth')])
(OUT/'rev-values.json').write_text(json.dumps(V,indent=1))
print(json.dumps({k:v for k,v in V.items() if not k.startswith('rev_table')},indent=0)[:4000])
