// Repeated EXPLAIN (ANALYZE, BUFFERS) for every manifest cell in one session; explanatory, never timing samples.
const {Pool}=require('pg'),fs=require('fs');const {sql,params}=require('./queries.cjs');
const [collection,session,reps]=[process.argv[2],Number(process.argv[3]),Number(process.argv[4]||3)];
const pool=new Pool({host:'db',user:'unibackend',password:'local-study-only',database:'unibackend',max:1});
const cells=JSON.parse(fs.readFileSync('/results/cells.json','utf8')),expected=JSON.parse(fs.readFileSync(`/results/expected-${collection}.json`,'utf8'));
(async()=>{try{
 for(let rep=0;rep<reps;rep++)for(const c of cells){
  const e=expected[c.schema][c.order][`${c.limit}:${c.offset}`],query=sql(c.design,c.method,c.schema,c.order);
  const plan=(await pool.query('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) '+query,params(c.method,c.order,c.limit,c.offset,e.cursor))).rows[0]['QUERY PLAN'];
  console.log(JSON.stringify({type:'plan',at:new Date().toISOString(),collection,session,rep,cell:c.cell,...c,plan}));
 }
}finally{await pool.end()}})().catch(e=>{console.error(e);process.exitCode=1});
