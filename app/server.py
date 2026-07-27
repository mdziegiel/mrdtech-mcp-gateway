#!/usr/bin/env python3
import os, json, ssl, urllib.request, urllib.error
from typing import Optional
from mcp.server.fastmcp import FastMCP

PORTAINER_URL=os.environ.get("PORTAINER_URL","https://portainer.example.internal:9443").rstrip("/")
TOKEN_FILE=os.environ.get("PORTAINER_TOKEN_FILE","/run/secrets/portainer_api_token")
ALLOWED_ENDPOINTS={int(x) for x in os.environ.get("PORTAINER_ALLOWED_ENDPOINTS","2,3").split(",") if x.strip()}
TLS_VERIFY=os.environ.get("PORTAINER_TLS_VERIFY","false").lower() in ("1","true","yes")
ctx=None if TLS_VERIFY else ssl._create_unverified_context()
API_KEY=os.environ.get("PORTAINER_API_KEY")
if not API_KEY:
    with open(TOKEN_FILE,"r",encoding="utf-8") as f:
        API_KEY=f.read().strip()

mcp=FastMCP("portainer-readonly")

def p_get(path: str):
    if not path.startswith("/"):
        path="/"+path
    req=urllib.request.Request(PORTAINER_URL+path,headers={"X-API-Key":API_KEY},method="GET")
    try:
        with urllib.request.urlopen(req,context=ctx,timeout=30) as r:
            txt=r.read().decode("utf-8","replace")
            return json.loads(txt) if txt else None
    except urllib.error.HTTPError as e:
        body=e.read().decode("utf-8","replace")[:500]
        raise RuntimeError(f"Portainer GET {path} failed HTTP {e.code}: {body}")

def status_text(v):
    return {1:"active",2:"inactive",3:"deploying",4:"error"}.get(v,"unknown")

@mcp.tool()
def list_stacks(endpoint_id: Optional[int]=None) -> dict:
    """List Portainer stacks for allowed endpoints 2 and 3 only."""
    if endpoint_id is not None and endpoint_id not in ALLOWED_ENDPOINTS:
        raise ValueError("endpoint_id is not allowed")
    stacks=p_get("/api/stacks") or []
    out=[]
    for s in stacks:
        eid=s.get("EndpointId")
        if eid not in ALLOWED_ENDPOINTS:
            continue
        if endpoint_id is not None and eid != endpoint_id:
            continue
        out.append({"id":s.get("Id"),"name":s.get("Name"),"endpoint_id":eid,"status":s.get("Status"),"status_text":status_text(s.get("Status")),"type":s.get("Type"),"project_path":s.get("ProjectPath")})
    return {"stacks":out,"count":len(out),"allowed_endpoints":sorted(ALLOWED_ENDPOINTS)}

@mcp.tool()
def get_stack_status(stack_id: int) -> dict:
    """Get status for one Portainer stack by stack_id. Only endpoints 2 and 3 are allowed."""
    stacks=p_get("/api/stacks") or []
    for s in stacks:
        if s.get("Id")==stack_id:
            eid=s.get("EndpointId")
            if eid not in ALLOWED_ENDPOINTS:
                raise ValueError("stack endpoint is not allowed")
            return {"id":s.get("Id"),"name":s.get("Name"),"endpoint_id":eid,"status":s.get("Status"),"status_text":status_text(s.get("Status")),"type":s.get("Type"),"project_path":s.get("ProjectPath")}
    raise ValueError("stack not found or not visible")

@mcp.tool()
def list_containers(endpoint_id: int=2, all: bool=True) -> dict:
    """List containers from an allowed Portainer endpoint via GET-only Docker proxy."""
    if endpoint_id not in ALLOWED_ENDPOINTS:
        raise ValueError("endpoint_id is not allowed")
    containers=p_get(f"/api/endpoints/{endpoint_id}/docker/containers/json?all={'true' if all else 'false'}") or []
    out=[]
    for c in containers:
        labels=c.get("Labels") or {}
        health=(c.get("Health") or {}).get("Status")
        out.append({"id":(c.get("Id") or "")[:12],"names":c.get("Names") or [],"image":c.get("Image"),"state":c.get("State"),"status":c.get("Status"),"health":health,"compose_project":labels.get("com.docker.compose.project"),"compose_service":labels.get("com.docker.compose.service"),"ports":c.get("Ports") or []})
    return {"endpoint_id":endpoint_id,"containers":out,"count":len(out)}

if __name__ == "__main__":
    mcp.run()
