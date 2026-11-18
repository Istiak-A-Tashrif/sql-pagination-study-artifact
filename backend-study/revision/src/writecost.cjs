// Write-side cost of the precomputed designs on s100000. Every insert is rolled back, so read data are unchanged.
const {Pool}=require('pg');const {performance}=require('perf_hooks');
const pool=new Pool({host:'db',user:'unibackend',password:'local-study-only',database:'unibackend',max:1});
const emit=x=>console.log(JSON.stringify({at:new Date().toISOString(),...x}));const s='s100000';
(async()=>{try{
 const before=(await pool.query(`SELECT md5(string_agg(id||':'||total_orders||':'||avg_rating,',' ORDER BY id)) h FROM ${s}.products_c`)).rows[0].h;
 // Alternate trigger-maintained and trigger-free inserts; session_replication_role=replica disables ordinary triggers.
 for(let i=0;i<400;i++){
  const mode=i%2?'no_trigger':'trigger',pid=1+((i*7919)%100000);
  await pool.query('BEGIN');
  if(mode==='no_trigger')await pool.query("SET LOCAL session_replication_role='replica'");
  const t=performance.now();
  await pool.query(`INSERT INTO ${s}.order_items(id,order_id,product_id,quantity,unit_price) VALUES (5000000+$1,1,$2,1,9.99)`,[i,pid]);
  await pool.query(`INSERT INTO ${s}.reviews(id,user_id,product_id,rating,comment,created_at) VALUES (5000000+$1,1,$2,5,'w',now())`,[i,pid]);
  const ms=performance.now()-t;
  const c=(await pool.query(`SELECT total_orders,avg_rating FROM ${s}.products_c WHERE id=$1`,[pid])).rows[0];
  const o=(await pool.query(`SELECT count(DISTINCT order_id) total_orders,COALESCE(avg(rating),0) avg_rating FROM (SELECT order_id,NULL::int rating FROM ${s}.order_items WHERE product_id=$1 UNION ALL SELECT NULL,rating FROM ${s}.reviews WHERE product_id=$1) z`,[pid])).rows[0];
  await pool.query('ROLLBACK');
  emit({type:'write',mode,i,product_id:pid,ms,counter_current:c.total_orders===o.total_orders&&String(c.avg_rating)===String(o.avg_rating)});
 }
 for(const mode of ['refresh','refresh_concurrently'])for(let i=0;i<5;i++){
  const t=performance.now();await pool.query(`REFRESH MATERIALIZED VIEW ${mode==='refresh'?'':'CONCURRENTLY '}${s}.stats_mv`);emit({type:'mv_refresh',mode,i,ms:performance.now()-t});
 }
 const after=(await pool.query(`SELECT md5(string_agg(id||':'||total_orders||':'||avg_rating,',' ORDER BY id)) h FROM ${s}.products_c`)).rows[0].h;
 if(before!==after)throw Error('counter table changed');
 emit({type:'complete',status:'PASS'});
}finally{await pool.end()}})().catch(e=>{console.error(e);process.exitCode=1});
