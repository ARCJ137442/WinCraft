import {spawnSync} from 'node:child_process';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const dir=path.dirname(fileURLToPath(import.meta.url));const root=path.resolve(dir,'..');
const build=spawnSync(process.execPath,[path.join(dir,'build-ui.mjs')],{stdio:'inherit'});if(build.status!==0)process.exit(build.status??1);
const dist=path.join(root,'apps/desktop/dist');
const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8'};
const server=createServer(async(req,res)=>{
  try{
    const pathname=decodeURIComponent(new URL(req.url??'/','http://127.0.0.1').pathname);
    const file=path.resolve(dist,`.${pathname==='/'?'/index.html':pathname}`);
    if(!file.startsWith(dist+path.sep)){res.writeHead(403);res.end();return;}
    const content=await readFile(file);res.writeHead(200,{'Content-Type':types[path.extname(file)]??'application/octet-stream','Cache-Control':'no-store'});res.end(content);
  }catch{res.writeHead(404);res.end('Not found');}
});
server.listen(1420,'127.0.0.1',()=>console.log('Preview: http://127.0.0.1:1420  | manager: ?preview=manager | rebuild after source edits'));
