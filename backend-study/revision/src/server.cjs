// Same instrumentation boundaries as the primary study: service time from route entry through response serialization.
const express=require('express'),{Pool}=require('pg'),fs=require('fs'),crypto=require('crypto');
const {sql,params,schemas,designs}=require('./queries.cjs');
const pool=new Pool({host:'db',user:'unibackend',password:'local-study-only',database:'unibackend',max:1});
const app=express();app.use(express.json());
const log=x=>fs.appendFileSync('/results/api.jsonl',JSON.stringify({at:new Date().toISOString(),...x})+'\n');
app.get('/health',async(_,res)=>{await pool.query('SELECT 1');res.json({ok:true,pid:process.pid})});
app.get('/backend',async(_,res)=>res.json((await pool.query("SELECT pg_backend_pid() pid,pg_postmaster_start_time() started,(SELECT setting FROM pg_settings WHERE name='server_version') version")).rows[0]));
app.post('/query',async(req,res)=>{
 const t=performance.now(),id=crypto.randomUUID(),c=req.body;
 try{
  const {schema,design,method,order,limit,offset,cursor,run}=c;
  if(!schemas.includes(schema)||!designs[design]||!Number.isInteger(limit)||limit<1||limit>100||!Number.isInteger(offset)||offset<0||!/^[-a-zA-Z0-9]+$/.test(run))throw Error('invalid request');
  if(method==='keyset'&&(!cursor||!Number.isInteger(cursor.id)||(order!=='id'&&!/^-?[0-9.]+$/.test(cursor.key))))throw Error('invalid cursor');
  const query=sql(design,method,schema,order);
  const x=performance.now();const rows=(await pool.query(query,params(method,order,limit,offset,cursor))).rows;const dbMs=performance.now()-x;
  const y=performance.now();const body=JSON.stringify({id,data:rows});const responseSerializeMs=performance.now()-y;
  const event={...c,id,dbMs,responseSerializeMs,serviceMs:performance.now()-t,bytes:Buffer.byteLength(body),rowCount:rows.length,rowDigest:crypto.createHash('sha256').update(JSON.stringify(rows)).digest('hex')};
  log(event);res.set('Cache-Control','no-store').type('json').send(body);
 }catch(e){log({...c,id,error:e.message});res.status(500).json({error:e.message})}
});
app.listen(5001,'0.0.0.0');
