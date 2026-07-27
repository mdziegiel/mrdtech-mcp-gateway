#!/usr/bin/env python3
import os, json, ssl, urllib.request, urllib.parse, urllib.error
from typing import Optional, Literal
from mcp.server.fastmcp import FastMCP

PBS_URL = os.environ.get('PBS_URL', 'https://pbs.example.internal:8007').rstrip('/')
PBS_TOKEN_ID = os.environ['PBS_TOKEN_ID']
PBS_TOKEN_SECRET = os.environ['PBS_TOKEN_SECRET']
PBS_DEFAULT_DATASTORE = os.environ.get('PBS_DEFAULT_DATASTORE', 'Backups')
VERIFY_SSL = os.environ.get('PBS_VERIFY_SSL', 'false').lower() in ('1','true','yes')
ctx = None if VERIFY_SSL else ssl._create_unverified_context()
AUTH = f'PBSAPIToken={PBS_TOKEN_ID}:{PBS_TOKEN_SECRET}'
BASE = PBS_URL + '/api2/json'

mcp = FastMCP('pbs-readonly')

def pbs_get(path: str, params: Optional[dict] = None):
    if not path.startswith('/'):
        path = '/' + path
    if params:
        clean = {k: v for k, v in params.items() if v is not None}
        if clean:
            path += '?' + urllib.parse.urlencode(clean)
    req = urllib.request.Request(BASE + path, headers={'Authorization': AUTH}, method='GET')
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=45) as r:
            txt = r.read().decode('utf-8', 'replace')
            return json.loads(txt).get('data') if txt else None
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', 'replace')[:700]
        raise RuntimeError(f'PBS GET {path} failed HTTP {e.code}: {body}')

def store_name(store: Optional[str]) -> str:
    return store or PBS_DEFAULT_DATASTORE

@mcp.tool()
def list_datastores() -> dict:
    """List accessible PBS datastores using GET /admin/datastore."""
    datastores = pbs_get('/admin/datastore') or []
    return {'datastores': datastores, 'count': len(datastores)}

@mcp.tool()
def get_datastore_status(store: Optional[str] = None) -> dict:
    """Get PBS datastore summary/health using GET /admin/datastore/{store}/status."""
    ds = store_name(store)
    return {'store': ds, 'status': pbs_get(f'/admin/datastore/{urllib.parse.quote(ds, safe="")}/status')}

@mcp.tool()
def list_snapshots(store: Optional[str] = None, backup_type: Optional[Literal['vm','ct','host']] = None, backup_id: Optional[str] = None, ns: Optional[str] = None, max_results: int = 100) -> dict:
    """List PBS backup snapshots using GET /admin/datastore/{store}/snapshots. Optional client-side max_results cap."""
    ds = store_name(store)
    params = {'backup-type': backup_type, 'backup-id': backup_id, 'ns': ns}
    snapshots = pbs_get(f'/admin/datastore/{urllib.parse.quote(ds, safe="")}/snapshots', params) or []
    snapshots = sorted(snapshots, key=lambda s: s.get('backup-time', 0), reverse=True)
    if max_results and max_results > 0:
        snapshots = snapshots[:max_results]
    return {'store': ds, 'snapshots': snapshots, 'count': len(snapshots)}

@mcp.tool()
def get_snapshot_verification_status(store: Optional[str] = None, backup_type: Optional[Literal['vm','ct','host']] = None, backup_id: Optional[str] = None, ns: Optional[str] = None, max_results: int = 100) -> dict:
    """Return snapshot verification metadata from GET /admin/datastore/{store}/snapshots. Does not start verification."""
    data = list_snapshots(store, backup_type, backup_id, ns, max_results)
    rows = []
    for s in data['snapshots']:
        v = s.get('verification') or {}
        rows.append({
            'backup_type': s.get('backup-type'),
            'backup_id': s.get('backup-id'),
            'backup_time': s.get('backup-time'),
            'protected': s.get('protected'),
            'verification_state': v.get('state'),
            'verification_upid': v.get('upid'),
        })
    return {'store': data['store'], 'verification': rows, 'count': len(rows)}

@mcp.tool()
def get_gc_status(store: Optional[str] = None) -> dict:
    """Get PBS garbage collection status using GET /admin/datastore/{store}/gc."""
    ds = store_name(store)
    return {'store': ds, 'gc': pbs_get(f'/admin/datastore/{urllib.parse.quote(ds, safe="")}/gc')}

@mcp.tool()
def list_gc_tasks(node: str = 'localhost', limit: int = 50, since: Optional[int] = None, statusfilter: Optional[Literal['ok','warning','error','unknown']] = None) -> dict:
    """List PBS garbage_collection tasks using GET /nodes/{node}/tasks. Read-only."""
    params = {'limit': limit, 'since': since, 'statusfilter': statusfilter, 'typefilter': 'garbage_collection'}
    tasks = pbs_get(f'/nodes/{urllib.parse.quote(node, safe="")}/tasks', params) or []
    return {'node': node, 'tasks': tasks, 'count': len(tasks)}

@mcp.tool()
def get_task_log(upid: str, node: str = 'localhost', start: int = 0, limit: int = 200) -> dict:
    """Read a PBS task log using GET /nodes/{node}/tasks/{upid}/log. Read-only."""
    if not upid.startswith('UPID:'):
        raise ValueError('upid must be a full PBS UPID')
    params = {'start': start, 'limit': limit}
    log = pbs_get(f'/nodes/{urllib.parse.quote(node, safe="")}/tasks/{urllib.parse.quote(upid, safe="")}/log', params) or []
    return {'node': node, 'upid': upid, 'log': log, 'count': len(log)}

if __name__ == '__main__':
    mcp.run()
