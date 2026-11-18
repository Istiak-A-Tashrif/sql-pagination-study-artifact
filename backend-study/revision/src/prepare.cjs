// Builds the revision schemas, precomputed-aggregate structures and the correctness gate.
// Writes /results/expected-<collection>.json: oracle page digests and the cursor preceding every tested window.
const {Pool}=require('pg'),crypto=require('crypto'),fs=require('fs');
const {sql,params,schemas,orders,designs}=require('./queries.cjs');
const collection=process.argv[2];if(!/^[-a-zA-Z0-9]+$/.test(collection||''))throw Error('collection id required');
const pool=new Pool({host:'db',user:'unibackend',password:'local-study-only',database:'unibackend',max:1});
const q=(t,p)=>pool.query(t,p);
const emit=x=>console.log(JSON.stringify({at:new Date().toISOString(),...x}));
const tables=['users','categories','products','orders','order_items','reviews','inventory','tags','product_tags'];
const digest=rows=>crypto.createHash('sha256').update(JSON.stringify(rows)).digest('hex');
const N={s5000:5000,s25000:25000,s100000:100000,skew100000:100000};
const LIMITS=[10,25,100],FRACTIONS=[0,.5,.95];
const sentinel={id:{id:0},price:{id:0,key:'-1'},orders:{id:2147483647,key:'9223372036854775807'},rating:{id:2147483647,key:'1000000'}};
async function clone(s,rep){
 await q(`DROP SCHEMA IF EXISTS ${s} CASCADE; CREATE SCHEMA ${s}`);
 for(const t of tables)await q(`CREATE TABLE ${s}.${t} (LIKE public.${t} INCLUDING ALL)`);
 const specs={users:"id+k*10000,name,email||'.rep'||k,created_at",categories:'id,name',products:'id+k*5000,name,description,price,category_id,created_at',orders:'id+k*20000,user_id+k*10000,total_amount,created_at',order_items:'id+k*50000,order_id+k*20000,product_id+k*5000,quantity,unit_price',reviews:'id+k*30000,user_id+k*10000,product_id+k*5000,rating,comment,created_at',inventory:'product_id+k*5000,stock,last_updated',tags:'id,name',product_tags:'product_id,tag_id'};
 for(const t of tables){const copies=['categories','tags','product_tags'].includes(t)?1:rep;await q(`INSERT INTO ${s}.${t} SELECT ${specs[t]} FROM public.${t} CROSS JOIN generate_series(0,${copies-1}) k`);}
}
async function skew(s){ // identical generator to the follow-up collection (seed 0.20261022)
 await q(`DROP SCHEMA IF EXISTS ${s} CASCADE; CREATE SCHEMA ${s}`);
 for(const t of tables)await q(`CREATE TABLE ${s}.${t} (LIKE public.${t} INCLUDING ALL)`);
 await q('SELECT setseed(0.20261022)');
 await q(`INSERT INTO ${s}.categories SELECT id,name FROM public.categories`);
 await q(`INSERT INTO ${s}.tags SELECT id,name FROM public.tags`);
 await q(`INSERT INTO ${s}.users SELECT g,'User '||g,'user'||g||'@skew.example',now() FROM generate_series(1,200000) g`);
 await q(`INSERT INTO ${s}.products SELECT g,'Product '||g,'Synthetic skew product '||g,round((10+random()*990)::numeric,2),1+floor(random()*10)::int,now() FROM generate_series(1,100000) g`);
 await q(`INSERT INTO ${s}.orders SELECT g,1+floor(random()*200000)::int,round((random()*500)::numeric,2),now() FROM generate_series(1,400000) g`);
 await q(`INSERT INTO ${s}.order_items SELECT g,1+floor(random()*400000)::int,1+((floor(100000*power(random(),3))::bigint*7919)%100000)::int,1+floor(random()*5)::int,round((5+random()*95)::numeric,2) FROM generate_series(1,1000000) g`);
 await q(`INSERT INTO ${s}.reviews SELECT g,1+floor(random()*200000)::int,1+((floor(100000*power(random(),2))::bigint*104729)%100000)::int,1+floor(random()*5)::int,'Review '||g,now() FROM generate_series(1,600000) g`);
 await q(`INSERT INTO ${s}.inventory SELECT g,floor(random()*500)::int,now() FROM generate_series(1,100000) g`);
}
async function precomputed(s){
 const agg=`SELECT p.id product_id,COALESCE(o.total_orders,0) total_orders,COALESCE(r.avg_rating,0) avg_rating FROM ${s}.products p
  LEFT JOIN (SELECT product_id,COUNT(DISTINCT order_id) total_orders FROM ${s}.order_items GROUP BY product_id) o ON o.product_id=p.id
  LEFT JOIN (SELECT product_id,AVG(rating) avg_rating FROM ${s}.reviews GROUP BY product_id) r ON r.product_id=p.id`;
 // Materialized view: refreshed explicitly, stale between refreshes.
 await q(`CREATE MATERIALIZED VIEW ${s}.stats_mv AS ${agg}`);
 await q(`CREATE UNIQUE INDEX stats_mv_product_id ON ${s}.stats_mv(product_id)`);
 await q(`CREATE INDEX stats_mv_orders ON ${s}.stats_mv(total_orders,product_id)`);
 await q(`CREATE INDEX stats_mv_rating ON ${s}.stats_mv(avg_rating,product_id)`);
 // Counter columns: a product table carrying aggregate columns maintained synchronously by row triggers.
 await q(`CREATE TABLE ${s}.products_c (LIKE ${s}.products INCLUDING ALL)`);
 await q(`ALTER TABLE ${s}.products_c ADD COLUMN total_orders bigint NOT NULL DEFAULT 0, ADD COLUMN avg_rating numeric NOT NULL DEFAULT 0`);
 await q(`INSERT INTO ${s}.products_c SELECT p.*,a.total_orders,a.avg_rating FROM ${s}.products p JOIN (${agg}) a ON a.product_id=p.id`);
 await q(`CREATE INDEX products_c_orders ON ${s}.products_c(total_orders,id)`);
 await q(`CREATE INDEX products_c_rating ON ${s}.products_c(avg_rating,id)`);
 await q(`CREATE FUNCTION ${s}.sync_counter(pid int) RETURNS void LANGUAGE sql AS $$
  UPDATE ${s}.products_c SET total_orders=(SELECT count(DISTINCT order_id) FROM ${s}.order_items WHERE product_id=pid),
   avg_rating=COALESCE((SELECT avg(rating) FROM ${s}.reviews WHERE product_id=pid),0) WHERE id=pid $$`);
 await q(`CREATE FUNCTION ${s}.counter_trigger() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
  IF TG_OP IN ('UPDATE','DELETE') THEN PERFORM ${s}.sync_counter(OLD.product_id); END IF;
  IF TG_OP IN ('INSERT','UPDATE') THEN PERFORM ${s}.sync_counter(NEW.product_id); END IF;
  RETURN NULL; END $$`);
 for(const t of ['order_items','reviews'])await q(`CREATE TRIGGER ${t}_counter AFTER INSERT OR UPDATE OR DELETE ON ${s}.${t} FOR EACH ROW EXECUTE FUNCTION ${s}.counter_trigger()`);
}
const oracleSql=(s,order)=>{
 const by={id:'q.id',price:'q._price,q.id',orders:'q.total_orders DESC,q.id DESC',rating:'q.avg_rating DESC,q.id DESC'}[order];
 return `SELECT q.id,q.name,q.category,q.total_orders,q.avg_rating,q.stock,q._price FROM (SELECT p.id,p.name,c.name category,(SELECT count(DISTINCT order_id) FROM ${s}.order_items x WHERE x.product_id=p.id) total_orders,COALESCE((SELECT avg(rating) FROM ${s}.reviews x WHERE x.product_id=p.id),0) avg_rating,COALESCE((SELECT stock FROM ${s}.inventory x WHERE x.product_id=p.id),0) stock,p.price _price FROM ${s}.products p LEFT JOIN ${s}.categories c ON c.id=p.category_id) q ORDER BY ${by}`;
};
const strip=rows=>rows.map(({_price,...r})=>r);
(async()=>{try{
 const base=(await q('SELECT (SELECT count(*) FROM public.products)::int products')).rows[0];
 if(base.products!==5000)throw Error('base dump incomplete');
 const expected={};let checks=0;
 for(const s of schemas){
  if(s==='skew100000')await skew(s);else await clone(s,N[s]/5000);
  if(s==='s100000')await q(`CREATE INDEX products_price_id ON ${s}.products(price,id)`);
  await precomputed(s);
  for(const t of [...tables,'products_c'])await q(`VACUUM (ANALYZE) ${s}.${t}`);
  await q(`ANALYZE ${s}.stats_mv`);
  const counts={};for(const t of [...tables,'products_c','stats_mv'])counts[t]=Number((await q(`SELECT count(*) n FROM ${s}.${t}`)).rows[0].n);
  emit({type:'counts',schema:s,counts});
  expected[s]={};
  for(const order of Object.keys(orders)){
   const oracleRows=(await q(oracleSql(s,order))).rows,oracle=strip(oracleRows),n=N[s];
   if(oracle.length!==n)throw Error('oracle size');
   const key=r=>order==='price'?r._price:order==='orders'?r.total_orders:order==='rating'?r.avg_rating:null;
   expected[s][order]={all:digest(oracle)};
   for(const limit of LIMITS)for(const f of FRACTIONS){
    const offset=Math.floor(n*f),prev=offset===0?sentinel[order]:{id:oracleRows[offset-1].id,...(order==='id'?{}:{key:String(key(oracleRows[offset-1]))})};
    expected[s][order][`${limit}:${offset}`]={digest:digest(oracle.slice(offset,offset+limit)),cursor:prev,ids:oracle.slice(offset,offset+limit).map(r=>r.id)};
   }
   for(const [d,spec] of Object.entries(designs)){
    if(!spec.orders.includes(order))continue;
    for(const m of spec.methods){
     const all=(await q(sql(d,m,s,order),params(m,order,n,0,sentinel[order]))).rows;
     if(digest(all)!==expected[s][order].all)throw Error('all-row oracle mismatch '+[s,order,d,m]);
     let pages=0;
     for(const limit of LIMITS)for(const f of FRACTIONS){
      const offset=Math.floor(n*f),e=expected[s][order][`${limit}:${offset}`];
      const rows=(await q(sql(d,m,s,order),params(m,order,limit,offset,e.cursor))).rows;
      if(digest(rows)!==e.digest)throw Error('page oracle mismatch '+[s,order,d,m,limit,offset]);pages++;
     }
     checks++;emit({type:'correctness',schema:s,order,design:d,method:m,products:all.length,page_checks:pages,status:'PASS'});
    }
   }
  }
 }
 // Distribution and physical-order statistics used to interpret plans.
 for(const s of ['s100000','skew100000']){
  const f=(await q(`SELECT (SELECT max(c) FROM (SELECT count(*) c FROM ${s}.order_items GROUP BY product_id) z)::int max_items,(SELECT percentile_disc(.5) WITHIN GROUP (ORDER BY c) FROM (SELECT count(*) c FROM ${s}.order_items GROUP BY product_id) z)::int median_items,(SELECT max(c) FROM (SELECT count(*) c FROM ${s}.reviews GROUP BY product_id) z)::int max_reviews,(SELECT count(DISTINCT total_orders) FROM ${s}.stats_mv)::int distinct_order_counts,(SELECT count(DISTINCT avg_rating) FROM ${s}.stats_mv)::int distinct_ratings,(SELECT count(DISTINCT price) FROM ${s}.products)::int distinct_prices`)).rows[0];
  const corr=(await q(`SELECT tablename,attname,correlation FROM pg_stats WHERE schemaname=$1 AND ((tablename IN ('order_items','reviews') AND attname='product_id') OR (tablename='products' AND attname IN ('id','price'))) ORDER BY 1,2`,[s])).rows;
  emit({type:'distribution',schema:s,fanout:f,correlation:corr});
 }
 fs.writeFileSync(`/results/expected-${collection}.json`,JSON.stringify(expected));
 const settings=(await q(`SELECT name,setting,unit FROM pg_settings WHERE name IN ('server_version','shared_buffers','work_mem','hash_mem_multiplier','max_parallel_workers_per_gather','jit','random_page_cost','effective_cache_size','track_io_timing') ORDER BY name`)).rows;
 const indexes=(await q(`SELECT schemaname,tablename,indexname,indexdef FROM pg_indexes WHERE schemaname = ANY($1) ORDER BY 1,2,3`,[schemas])).rows;
 emit({type:'environment',settings,indexes,checks});
 emit({type:'complete',status:'PASS',checks});
}finally{await pool.end()}})().catch(e=>{console.error(e);process.exitCode=1});
