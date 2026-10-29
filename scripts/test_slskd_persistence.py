#!/usr/bin/env python3
"""Exercise the real slskd image without connecting to the Soulseek network."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import tarfile
import tempfile
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]

def run(*args,**kwargs):
    return subprocess.run(args,check=True,text=True,**kwargs)

def output(*args):
    return run(*args,capture_output=True).stdout

def build(image,version):
    run('docker','build','--build-arg','BUILD_ARCH=amd64','--build-arg',f'BUILD_VERSION={version}','-t',image,str(ROOT/'slskd'))
    assert not json.loads(output('docker','image','inspect',image))[0]['Config'].get('Volumes'), 'Anonymous image volumes'

def inside(name,script):
    return run('docker','exec','-i',name,'bash','-s',input='set -euo pipefail\n'+script,capture_output=True).stdout

def start(name,image,base):
    args=['docker','run','-d','--name',name,'--network','none']
    for folder in ['data','config','share','media']:
        args+=['--mount',f"type=bind,source={base/folder},target=/{folder}"+(',readonly' if folder=='media' else '')]
    run(*args,image)
    for _ in range(90):
        state=json.loads(output('docker','inspect',name))[0]
        if not state['State']['Running']:
            raise RuntimeError(output('docker','logs',name)[-6000:])
        try:
            response=inside(name,'''key=$(jq -r .api_key /config/connection.json)
wget -qO- --header="X-API-Key: $key" http://127.0.0.1:5030/api/v0/application
''')
            app=json.loads(response)
            assert app is not None
            mounts={m['Destination']:m['Type'] for m in state['Mounts']}
            assert mounts=={'/data':'bind','/config':'bind','/media':'bind','/share':'bind'}, mounts
            assert next(m for m in state['Mounts'] if m['Destination']=='/media')['RW'] is False
            return
        except (subprocess.CalledProcessError,json.JSONDecodeError):
            time.sleep(1)
    raise RuntimeError('slskd did not become ready: '+output('docker','logs',name)[-6000:])

def stop(name):
    run('docker','stop','--time','20',name,stdout=subprocess.DEVNULL)
    run('docker','rm','-v',name,stdout=subprocess.DEVNULL)

def private_hashes(base):
    return {p:hashlib.sha256((base/p).read_bytes()).hexdigest() for p in ['config/connection.json','data/slskd.yml','data/.ha-persistence-probe']}

def verify(name,base,snapshot,dbpath):
    assert private_hashes(base)==snapshot, 'Credential/config/state reset'
    with sqlite3.connect(base/dbpath) as db:
        assert db.execute('select value from ha_persistence_probe').fetchone()[0]=='retained'
        assert db.execute('pragma integrity_check').fetchone()[0]=='ok'
    assert (base/'share/soulsync/downloads/.ha-download-probe').read_text()=='retained'
    settings=json.loads((base/'data/slskd.yml').read_text())
    assert settings['flags']['no_connect'] is True
    assert settings['shares']['directories']==['/media/dedicated-share']
    assert settings['web']['authentication']['disabled'] is False
    uid=inside(name,"awk '/^Uid:/{print $2}' /proc/1/status").strip()
    assert uid=='1234', uid
    print('PASS: private keys/session identity, real SQLite state, shared downloads, non-root runtime and read-only media',flush=True)

def main():
    stamp=uuid.uuid4().hex[:10]
    name='slskd-persistence-'+stamp
    first='slskd-ha-test:'+stamp
    second=first+'-rebuilt'
    with tempfile.TemporaryDirectory(prefix='slskd-ha-test-') as scratch:
        base=Path(scratch)
        for folder in ['data','config','share','media/dedicated-share']:
            (base/folder).mkdir(parents=True)
        (base/'media/dedicated-share/only-intended-share.txt').write_text('test-only')
        options={'puid':1234,'pgid':1234,'soulseek_username':'','soulseek_password':'','web_username':'admin','web_password':'',
                 'downloads_path':'/share/soulsync/downloads','incomplete_path':'/share/soulsync/incomplete','shared_dirs':['/media/dedicated-share']}
        (base/'data/options.json').write_text(json.dumps(options))
        try:
            build(first,'0.26.2-test')
            start(name,first,base)
            inside(name,"gosu 1234:1234 bash -c 'printf retained > /share/soulsync/downloads/.ha-download-probe; printf retained > /data/.ha-persistence-probe'")
            stop(name)
            candidates=[p for p in (base/'data').rglob('*') if p.is_file() and p.read_bytes()[:16]==b'SQLite format 3\x00']
            assert candidates, 'slskd did not create persistent SQLite state'
            print('SQLite state files: '+', '.join(str(p.relative_to(base)) for p in candidates),flush=True)
            persistent=[p for p in candidates if 'transfer' in p.name.lower()]
            assert persistent, 'Cannot identify persistent transfer history database'
            dbpath=persistent[0].relative_to(base)
            with sqlite3.connect(base/dbpath) as db:
                db.execute('create table ha_persistence_probe(value text)')
                db.execute("insert into ha_persistence_probe values ('retained')")
            snapshot=private_hashes(base)
            build(second,'0.26.2-test-rebuild')
            start(name,second,base)
            verify(name,base,snapshot,dbpath)
            stop(name)
            archive=base/'backup.tar'
            with tarfile.open(archive,'w') as tar:
                for folder in ['data','config']:
                    tar.add(base/folder,arcname=folder)
            restored=base/'restored'
            restored.mkdir()
            with tarfile.open(archive) as tar:
                tar.extractall(restored,filter='data')
            for folder in ['share','media']:
                (restored/folder).symlink_to(base/folder,target_is_directory=True)
            start(name,second,restored)
            verify(name,restored,snapshot,dbpath)
            stop(name)
            print('PASS: authenticated API, rebuilt-container replacement and cold backup restore; no Soulseek connection made',flush=True)
        finally:
            subprocess.run(['docker','rm','-f','-v',name],capture_output=True)

if __name__=='__main__':
    main()
