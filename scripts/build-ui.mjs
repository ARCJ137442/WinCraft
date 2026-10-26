import {spawnSync} from 'node:child_process';
import {existsSync,mkdirSync,copyFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const tsc=process.env.TSC_JS || path.join(root,'node_modules/typescript/bin/tsc');
if(!existsSync(tsc)){console.error('TypeScript is missing. Run npm install in the repository root.');process.exit(1);}
const result=spawnSync(process.execPath,[tsc,'-p',path.join(root,'apps/desktop/tsconfig.json')],{stdio:'inherit'});
if(result.status!==0)process.exit(result.status??1);
const output=path.join(root,'apps/desktop/dist');mkdirSync(output,{recursive:true});
for(const name of ['index.html','style.css','fit.css'])copyFileSync(path.join(root,'apps/desktop',name),path.join(output,name));
const buildId=new Date().toISOString().replace(/[-:.]/g,'');
writeFileSync(path.join(output,'build-id.txt'),`${buildId}\n`,{encoding:'utf8'});
console.log('UI built: apps/desktop/dist (no runtime framework, no external assets)');
