// Sequential client for one session. Every response must equal the oracle page digest for its window.
import fs from 'node:fs';import crypto from 'node:crypto';import {performance} from 'node:perf_hooks';
const base=new URL('./',import.meta.url),manifest=JSON.parse(fs.readFileSync(new URL('manifest.json',base)));
const [collection,sessionArg]=process.argv.slice(2),session=Number(sessionArg);
if(!/^[-a-zA-Z0-9]+$/.test(collection||'')||!Number.isInteger(session))throw Error('collection and session required');
const raw=new URL('results/raw/',base),expected=JSON.parse(fs.readFileSync(new URL(`expected-${collection}.json`,raw)));
const append=(f,x)=>fs.appendFileSync(new URL(f,raw),JSON.stringify({at:new Date().toISOString(),collection,session,...x})+'\n');
const API='http://127.0.0.1:24004';
async function query(c,run,phase,step){
 const e=expected[c.schema][c.order][`${c.limit}:${c.offset}`];
 const body={schema:c.schema,design:c.design,method:c.method,order:c.order,limit:c.limit,offset:c.offset,cursor:c.method==='keyset'?e.cursor:null,exp:c.exp,cell:c.cell,run,collection,session,phase,step};
 const start=performance.now(),response=await fetch(API+'/query',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 const value=await response.json(),clientMs=performance.now()-start;
 if(!response.ok)throw Error(JSON.stringify(value));
 const rowDigest=crypto.createHash('sha256').update(JSON.stringify(value.data)).digest('hex');
 if(rowDigest!==e.digest)throw Error('response differs from oracle page '+JSON.stringify(c));
 append('requests.jsonl',{...c,run,phase,step,id:value.id,clientMs,rowDigest,rowCount:value.data.length});
}
for(let i=0;i<240;i++){try{if((await fetch(API+'/health')).ok)break;}catch{}if(i===239)throw Error('API not ready');await new Promise(r=>setTimeout(r,500));}
append('events.jsonl',{event:'session-start',backend:await (await fetch(API+'/backend')).json()});
const s=manifest.sessions[session];
for(const c of manifest.cells)for(let j=0;j<manifest.warmups_per_cell;j++)await query(c,`${collection}-s${session}-warm-${c.cell}`,'warmup',j);
append('events.jsonl',{event:'warmup-complete',cells:manifest.cells.length});
for(const t of s.trials){
 const c=manifest.cells[t.cell],run=`${collection}-${t.trial}`,start=new Date().toISOString();
 for(let j=0;j<manifest.samples_per_trial;j++)await query(c,run,'measurement',j);
 append('trials.jsonl',{...c,trial:t.trial,rep:t.rep,index:t.index,run,start,end:new Date().toISOString()});
 if(t.index%200===0)console.log(JSON.stringify({session,completed:t.index+1,total:s.trials.length}));
}
append('events.jsonl',{event:'measurement-complete',trials:s.trials.length});
