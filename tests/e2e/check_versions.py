"""Version/ETag/race checks on real PostgreSQL, included in make e2e."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE=os.environ['UAI_TEST_URL']
KEY=os.environ['UAI_TEST_KEY']


def request(path,body=None,method=None,extra=None):
    headers={'Authorization':'Bearer '+KEY,'Content-Type':'application/json'}
    headers.update(extra or {})
    req=Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,
                headers=headers,method=method)
    try:
        with urlopen(req,timeout=30) as r:
            return r.status,r.headers,r.read().decode()
    except HTTPError as r:
        return r.code,r.headers,r.read().decode()


status,_,raw=request('/v1/models')
assert status==200
models=json.loads(raw)
assert models[0]['id']=='test' and {'chat','streaming'} <= set(models[0]['capabilities'])
assert not {'api_key','base_url','secret_ref'} & models[0].keys()
status,headers,raw=request('/v1/assistants',{'name':'Versioned','model':'test','system_prompt':'Original'})
assert status==201 and headers['ETag']=='"1"'
assistant=json.loads(raw)['id']
path='/v1/assistants/'+assistant
status,_,raw=request('/v1/conversations',{'assistant_id':assistant})
assert status==201
conversation=json.loads(raw)['id']
messages=f'/v1/conversations/{conversation}/messages'
status,headers,first=request(messages,{'content':'First'},extra={'Idempotency-Key':'version-test'})
assert status==200 and headers['X-Assistant-Version']=='1'
assert request(path,{'name':'Changed'},'PATCH')[0]==428
status,headers,raw=request(path,{'system_prompt':'Updated'},'PATCH',{'If-Match':'"1"'})
assert status==200 and headers['ETag']=='"2"'
status,headers,replay=request(messages,{'content':'First'},extra={'Idempotency-Key':'version-test'})
assert status==200 and headers['X-Assistant-Version']=='1' and replay==first
status,headers,_=request(messages,{'content':'Second'},extra={'Idempotency-Key':'version-test-2'})
assert status==200 and headers['X-Assistant-Version']=='2'
assert request(path,{'name':'Stale'},'PATCH',{'If-Match':'"1"'})[0]==412
with ThreadPoolExecutor(max_workers=2) as pool:
    replies=list(pool.map(lambda name:request(path,{'name':name},'PATCH',{'If-Match':'"2"'})[0],['Writer A','Writer B']))
assert sorted(replies)==[200,412],replies
status,_,raw=request(path+'/versions')
versions=json.loads(raw)
assert status==200 and [v['version'] for v in versions]==[1,2,3]
assert versions[0]['system_prompt']=='Original' and versions[1]['system_prompt']=='Updated'
assert request(path,{'tools':['Bad Tool']},'PATCH',{'If-Match':'"3"'})[0]==422
print('E2E versions, replay snapshot, catalog and conditional update: passed')
status,headers,_=request(path,{'memory':{'conversation':False}},'PATCH',{'If-Match':'"3"'})
assert status==200 and headers['ETag']=='"4"'
status,headers,raw=request(messages,{'content':'Without history'},extra={'Idempotency-Key':'without-history'})
assert status==200 and headers['X-Assistant-Version']=='4' and 'response.completed' in raw
