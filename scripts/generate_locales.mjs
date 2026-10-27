import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import path from 'node:path';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const localeDirectory=path.join(root,'apps/desktop/src/locales');
const locales=['zh-CN','en-US'];
const catalogs=Object.fromEntries(locales.map(locale=>[
  locale,JSON.parse(readFileSync(path.join(localeDirectory,`${locale}.json`),'utf8'))
]));
const keys=Object.keys(catalogs['zh-CN']).sort();
if(JSON.stringify(keys)!==JSON.stringify(Object.keys(catalogs['en-US']).sort())){
  throw new Error('Host locale catalogs must have identical stable keys');
}
const placeholders=value=>[...value.matchAll(/\{([^}]+)\}/gu)].map(match=>match[1]).sort();
for(const key of keys){
  if(JSON.stringify(placeholders(catalogs['zh-CN'][key]))!==JSON.stringify(placeholders(catalogs['en-US'][key]))){
    throw new Error(`Host locale placeholder mismatch: ${key}`);
  }
}
const output=`// Generated from zh-CN.json and en-US.json by scripts/generate_locales.mjs. Do not edit.\nexport const catalogs = ${JSON.stringify(catalogs,null,2)} as const;\n`;
const destination=path.join(localeDirectory,'generated.ts');
if(process.argv.includes('--check')){
  if(readFileSync(destination,'utf8')!==output)throw new Error('generated.ts is stale; run npm run ui:build');
}else{
  writeFileSync(destination,output,{encoding:'utf8'});
}
