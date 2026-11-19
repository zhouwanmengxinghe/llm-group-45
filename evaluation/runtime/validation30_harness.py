"""Independent evaluation on locally built exact-source runtime images."""
import io,json,re,runpy,sys,tarfile,hashlib
from pathlib import Path
from docker.models.containers import Container,ContainerCollection
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'benchmarks/test-runtime'))
from unittest_output import normalize_unittest_output
metadata=json.loads(Path(sys.argv[sys.argv.index('-d')+1]).read_text(encoding='utf-8'))
create,start=ContainerCollection.create,Container.start
original_stop=Container.stop
def local_stop(c,*args,**kw):
 if (c.attrs.get("Config",{}).get("Labels") or {}).get("validation.base"):kw["timeout"]=1
 return original_stop(c,*args,**kw)
Container.stop=local_stop
def local_create(collection,*args,**kw):
 requested=kw.get('image',args[0] if args else '')
 for r in metadata:
  if requested==r['image']:
   kw['labels']={**kw.get('labels',{}),'validation.base':r['base_commit']};break
 kw['network_mode']='none';kw['environment']={**kw.get('environment',{}),'PYTHONPATH':'/testbed/tests:/testbed/src:/testbed','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTHONUNBUFFERED':'1','PIP_NO_INDEX':'1','PIP_DISABLE_PIP_VERSION_CHECK':'1'}
 if kw.get('name'):kw['name']+='.'+hashlib.sha256(str(Path.cwd()).encode()).hexdigest()[:8]
 return create(collection,*args,**kw)
def local_start(c,**kw):
 r=start(c,**kw);c.reload();base=(c.attrs['Config'].get('Labels') or {}).get('validation.base')
 if base:
  p=c.exec_run(['git','-c','safe.directory=/testbed','-C','/testbed','reset','--hard',base],user='root')
  if p.exit_code:raise RuntimeError(p.output.decode(errors='replace'))
 return r
ContainerCollection.create=local_create;Container.start=local_start
from swebench.harness import docker_utils
execute=docker_utils.exec_run_with_timeout
def run(c,cmd,timeout=60):
 original=c.exec_run(['cat','/eval.sh']).output.decode('utf-8');package='pytest' if 'pytest-' in c.name else ('django' if 'django-' in c.name else 'sympy')
 # Sources are already installed by PYTHONPATH. Verify that exact candidate is
 # imported instead of repeating an unnecessary, network-dependent reinstall.
 verify='python -c "import '+package+'; assert '+package+'.__file__.startswith(\'/testbed/\'), '+package+'.__file__" || exit 97'
 original=re.sub(r'^git show$', 'git show --no-patch --oneline', original, flags=re.MULTILINE)
 adapted=re.sub(r'^python -m pip install .*$',verify,original,flags=re.MULTILINE)
 adapted=re.sub(r'^pytest ', 'python -m pytest ', adapted, flags=re.MULTILINE)
 adapted=re.sub(r'(?m)^(\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*)bin/test(?=\s|$)', r'\1python bin/test', adapted)
 adapted=re.sub(r'^\./tests/runtests.py ', 'python tests/runtests.py ', adapted, flags=re.MULTILINE)
 folder=Path('environment-scripts');folder.mkdir(exist_ok=True);(folder/'original.sh').write_text(original,encoding='utf-8');(folder/'source-import.sh').write_text(adapted,encoding='utf-8')
 payload=adapted.encode();stream=io.BytesIO()
 with tarfile.open(fileobj=stream,mode='w') as tar:
  e=tarfile.TarInfo('eval.sh');e.mode=0o755;e.size=len(payload);tar.addfile(e,io.BytesIO(payload))
 assert c.put_archive('/',stream.getvalue());text,timed,duration=execute(c,cmd,timeout);Path('raw-output.txt').write_text(text,encoding='utf-8');return normalize_unittest_output(re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',text)),timed,duration
docker_utils.exec_run_with_timeout=run
sys.argv=['swebench.harness.run_evaluation',*sys.argv[1:]];runpy.run_module('swebench.harness.run_evaluation',run_name='__main__')
