// SQL for the revision experiments. Parameters: $1 limit; $2 OFFSET count or cursor id; $3 cursor sort value (non-id orders).
const schemas=['s5000','s25000','s100000','skew100000'];
const orders={
 id:{dir:'asc',key:null},
 price:{dir:'asc',key:'numeric'},
 orders:{dir:'desc',key:'bigint'},
 rating:{dir:'desc',key:'numeric'}};
// Which designs are defined for which ordering and method (keyset-only pushdown).
const designs={
 global:{orders:['id','price','orders','rating'],methods:['offset','keyset']},
 global_hash:{orders:['id'],methods:['offset','keyset']},
 global_pushdown:{orders:['id'],methods:['keyset']},
 page_grouped:{orders:['id','price'],methods:['offset','keyset']},
 page_lateral:{orders:['id','price'],methods:['offset','keyset']},
 mv:{orders:['id','orders','rating'],methods:['offset','keyset']},
 counter:{orders:['id','orders','rating'],methods:['offset','keyset']}};
const COLS="p.id,p.name,c.name AS category,COALESCE(o.total_orders,0) AS total_orders,COALESCE(r.avg_rating,0) AS avg_rating,COALESCE(i.stock,0) AS stock";
const aggO=(s,w='')=>`SELECT product_id,COUNT(DISTINCT order_id) total_orders FROM ${s}.order_items${w} GROUP BY product_id`;
const aggOHash=s=>`SELECT product_id,COUNT(*) total_orders FROM (SELECT product_id,order_id FROM ${s}.order_items GROUP BY product_id,order_id) d GROUP BY product_id`;
const aggR=(s,w='')=>`SELECT product_id,AVG(rating) avg_rating FROM ${s}.reviews${w} GROUP BY product_id`;
// ORDER BY / keyset predicate on a relation alias a whose id column is idc and sort columns are named per ordering.
function ord(order,a,idc='id'){
 if(order==='id')return {by:`${a}.${idc}`,pred:`${a}.${idc}>$2`};
 if(order==='price')return {by:`${a}.price,${a}.${idc}`,pred:`(${a}.price,${a}.${idc})>($3::numeric,$2::int)`};
 const col=order==='orders'?'total_orders':'avg_rating',t=orders[order].key;
 return {by:`${a}.${col} DESC,${a}.${idc} DESC`,pred:`(${a}.${col},${a}.${idc})<($3::${t},$2::int)`};
}
const tail=(method,o)=>method==='offset'?` ORDER BY ${o.by} LIMIT $1 OFFSET $2`:` WHERE ${o.pred} ORDER BY ${o.by} LIMIT $1`;
function sql(design,method,schema,order='id'){
 const d=designs[design];
 if(!d||!d.orders.includes(order)||!d.methods.includes(method)||!schemas.includes(schema))throw Error('unknown query cell '+[design,method,schema,order]);
 const s=schema,join=`FROM ${s}.products p LEFT JOIN ${s}.categories c ON c.id=p.category_id`,inv=`LEFT JOIN ${s}.inventory i ON i.product_id=p.id`;
 if(design==='global'||design==='global_hash'||design==='global_pushdown'){
  const w=design==='global_pushdown'?' WHERE product_id>$2':'';
  const base=`SELECT ${COLS} ${join}\nLEFT JOIN (${design==='global_hash'?aggOHash(s):aggO(s,w)}) o ON o.product_id=p.id\nLEFT JOIN (${aggR(s,w)}) r ON r.product_id=p.id\n${inv}`;
  if(order==='id'||order==='price')return base+tail(method,ord(order,'p'));
  // Aggregate order: every product's aggregate must exist before the sort.
  return `SELECT * FROM (${base}) q`+tail(method,ord(order,'q'));
 }
 if(design==='page_grouped'||design==='page_lateral'){
  const o=ord(order,'p'),page=`WITH page AS MATERIALIZED (SELECT p.* FROM ${s}.products p${method==='offset'?'':' WHERE '+o.pred} ORDER BY ${o.by} LIMIT $1${method==='offset'?' OFFSET $2':''})`;
  if(design==='page_grouped')return `${page},\no AS (SELECT oi.product_id,COUNT(DISTINCT oi.order_id) total_orders FROM ${s}.order_items oi JOIN page k ON k.id=oi.product_id GROUP BY oi.product_id),\nr AS (SELECT rv.product_id,AVG(rv.rating) avg_rating FROM ${s}.reviews rv JOIN page k ON k.id=rv.product_id GROUP BY rv.product_id)\nSELECT ${COLS} FROM page p LEFT JOIN ${s}.categories c ON c.id=p.category_id\nLEFT JOIN o ON o.product_id=p.id LEFT JOIN r ON r.product_id=p.id\n${inv} ORDER BY ${o.by}`;
  return `${page}\nSELECT ${COLS} FROM page p LEFT JOIN ${s}.categories c ON c.id=p.category_id\nLEFT JOIN LATERAL (SELECT COUNT(DISTINCT order_id) total_orders FROM ${s}.order_items oi WHERE oi.product_id=p.id) o ON true\nLEFT JOIN LATERAL (SELECT AVG(rating) avg_rating FROM ${s}.reviews rv WHERE rv.product_id=p.id) r ON true\n${inv} ORDER BY ${o.by}`;
 }
 // Precomputed designs are written in their strongest form: select the page from the indexed precomputed
 // relation first (MATERIALIZED), then join the 25 rows to the descriptive tables.
 if(design==='mv'){
  const o=ord(order,'m','product_id'),fin=ord(order,'k','product_id');
  return `WITH k AS MATERIALIZED (SELECT m.* FROM ${s}.stats_mv m${method==='offset'?'':' WHERE '+o.pred} ORDER BY ${o.by} LIMIT $1${method==='offset'?' OFFSET $2':''})\nSELECT p.id,p.name,c.name AS category,k.total_orders,k.avg_rating,COALESCE(i.stock,0) AS stock\nFROM k JOIN ${s}.products p ON p.id=k.product_id LEFT JOIN ${s}.categories c ON c.id=p.category_id\n${inv} ORDER BY ${fin.by}`;
 }
 // counter: aggregate columns kept on a product table by row triggers.
 const o=ord(order,'p');
 return `WITH p AS MATERIALIZED (SELECT p.* FROM ${s}.products_c p${method==='offset'?'':' WHERE '+o.pred} ORDER BY ${o.by} LIMIT $1${method==='offset'?' OFFSET $2':''})\nSELECT p.id,p.name,c.name AS category,p.total_orders,p.avg_rating,COALESCE(i.stock,0) AS stock\nFROM p LEFT JOIN ${s}.categories c ON c.id=p.category_id\n${inv} ORDER BY ${o.by}`;
}
// Parameters in the order the SQL expects; cursor = {id, key} for the row preceding the window.
function params(method,order,limit,offset,cursor){
 if(method==='offset')return [limit,offset];
 if(order==='id')return [limit,cursor.id];
 return [limit,cursor.id,cursor.key];
}
module.exports={sql,params,schemas,orders,designs};
