#!/usr/bin/env python3
"""Guarded revision collection; operates ONLY on compose project unibackendr.
Independent sessions: before each session the API and PostgreSQL containers are stopped and started again,
so each session has a new postmaster, empty shared buffers, a new Node process and its own trial order."""
from pathlib import Path
import sys,subprocess,os,uuid,json,hashlib,platform
X=Path(__file__).resolve().parent;B=X.parent;R=B.parent
sys.path.insert(0,str(B))
import run as base
RAW=X/'results/raw';RAW.mkdir(parents=True,exist_ok=True)
C=['docker','compose','-p','unibackendr','-f',str(X/'docker-compose.yml')]
base.RAW=RAW;base.C=C
base.stop_ours=lambda:subprocess.run(C+['stop','-t','0','api','db'],cwd=R,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
PLAN_REPS=int(os.environ.get('PLAN_REPS','3'))
if __name__=='__main__':
 manifest=json.loads((X/'manifest.json').read_text())
 collection='rev-'+uuid.uuid4().hex[:12]
 clear,_=base.guard()
 if not clear:raise SystemExit('Main research driver active: no load started.')
 awake=subprocess.Popen(['caffeinate','-i','-s','-w',str(os.getpid())])
 try:
  sources={str(p.relative_to(X)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(X.rglob('*')) if p.is_file() and 'results' not in p.parts and (p.suffix in ('.cjs','.mjs','.py','.yml','.json','.md') or p.name=='Dockerfile')}
  env={'collection':collection,'at':base.now(),'platform':platform.platform(),'macos':base.output(['sw_vers','-productVersion']),'cpu':base.output(['sysctl','-n','machdep.cpu.brand_string']),'memory_bytes':int(base.output(['sysctl','-n','hw.memsize'])),'logical_cpus':int(base.output(['sysctl','-n','hw.logicalcpu'])),'node':base.output(['node','--version']),'docker':base.output(['docker','version','--format','{{.Server.Version}}']),'vm':base.output(['docker','info','--format','{{json .NCPU}} {{json .MemTotal}}']),'sources':sources,'dump_sha256':hashlib.sha256((R/'app/generated_test_data_dump.sql').read_bytes()).hexdigest(),'git_commit':base.output(['git','-C',str(R),'rev-parse','HEAD']),'plan_reps_per_session':PLAN_REPS}
  (RAW/('environment-'+collection+'.json')).write_text(json.dumps(env,indent=2)+'\n')
  base.stage('build',C+['build','api'],collection)
  base.stage('startup',C+['up','-d','--wait'],collection)
  prep=base.stage('correctness',C+['exec','-T','api','node','prepare.cjs',collection],collection)
  if not any('"type":"complete"' in x and '"PASS"' in x for x in prep.read_text().splitlines()):raise RuntimeError('Missing correctness completion marker')
  for k in range(len(manifest['sessions'])):
   base.stage(f'restart-s{k}',['sh','-c',' '.join(C+['stop','-t','10','api','db'])+' && '+' '.join(C+['up','-d','--wait','db','api'])],collection)
   base.stage(f'measurement-s{k}',['node',str(X/'runner.mjs'),collection,str(k)],collection)
   base.stage(f'plans-s{k}',C+['exec','-T','api','node','plans.cjs',collection,str(k),str(PLAN_REPS)],collection)
  base.stage('writecost',C+['exec','-T','api','node','writecost.cjs'],collection)
  base.append('collections.jsonl',{'collection':collection,'status':'accepted','manifest_sha256':sources['manifest.json'],'sessions':len(manifest['sessions'])})
  print('Accepted collection:',collection,flush=True)
 finally:
  base.stop_ours();awake.terminate()
