#!/usr/bin/env python3
"""Regenerate views from tasks.json; preserve unchanged case results only.

Does not execute tests or upgrade evidence. Re-run after editing task definitions.
When source code changes, maintainers must revalidate prior runtime evidence.
"""
from __future__ import annotations
import argparse
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load(path): return json.loads((ROOT/path).read_text(encoding="utf-8"))
def save(path, value): (ROOT/path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
def table(headers, rows):
    return "| "+" | ".join(headers)+" |\n|"+"|".join(["---"]*len(headers))+"|\n"+"\n".join("| "+" | ".join(str(v).replace("|","\\|").replace("\n"," ") for v in row)+" |" for row in rows)
def render(path, body, today):
    p=ROOT/path
    header, _=p.read_text(encoding="utf-8")[4:].split("\n---\n",1)
    meta=json.loads(header)
    meta["updated_at"]=today
    # Rendering is not source verification; retain last_verified_at.
    p.write_text("---\n"+json.dumps(meta,ensure_ascii=False,indent=2)+"\n---\n\n# "+meta["title"]+"\n\n"+body.strip()+"\n",encoding="utf-8")
    return meta

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date",required=True,help="actual update date YYYY-MM-DD")
    parser.add_argument("--reset-results",action="store_true",help="invalidate old results after a source/baseline change")
    args=parser.parse_args()
    date.fromisoformat(args.date)
    tasks=load("plan/tasks.json")["tasks"]
    req_file=load("plan/requirements.json")
    reqs=req_file["requirements"]
    req_map={r["id"]:r for r in reqs}
    for r in reqs: r["task_ids"],r["acceptance_ids"]=[],[]
    old={a["id"]:a for a in load("plan/acceptance.json")["cases"]}
    cases=[]
    for t in tasks:
        for rid in t["requirement_ids"]:
            req_map[rid]["task_ids"].append(t["id"])
            req_map[rid]["acceptance_ids"].extend(a["id"] for a in t["acceptance"])
        for a in t["acceptance"]:
            c={"id":a["id"],"task_id":t["id"],"requirement_ids":t["requirement_ids"],"level":t["verification_level"],"criterion":a["criterion"],"status":"NOT_RUN"}
            prev=old.get(a["id"])
            keys=["task_id","requirement_ids","level","criterion"]
            if prev and not args.reset_results and all(prev.get(k)==c[k] for k in keys):
                c.update({k:v for k,v in prev.items() if k not in c or k=="status"})
            cases.append(c)
    req_file["updated_at"]=args.date
    save("plan/requirements.json",req_file)
    save("plan/acceptance.json",{"updated_at":args.date,"cases":cases})
    metas={}
    metas["plan/TRACEABILITY.md"]=render("plan/TRACEABILITY.md", "单一来源为requirements.json与tasks.json，不手改生成表。\n\n"+table(["需求","内容","来源","规范","任务"],[(r["id"],r["requirement"],r["origin"],"["+Path(r["owner_doc"]).stem+"](../"+r["owner_doc"]+")",", ".join(r["task_ids"])) for r in reqs]),args.date)
    metas["plan/ACCEPTANCE.md"]=render("plan/ACCEPTANCE.md", "用例定义来自tasks.json；执行结果仅在acceptance.json记录，代码基线改变须重新验证。\n\n"+table(["用例","任务","层级","条件","状态"],[(a["id"],a["task_id"],a["level"],a["criterion"],a["status"]) for a in cases]),args.date)
    lines=["从tasks.json生成。状态不是已通过的证据。",table(["任务","标题","依赖","验证层"],[(t["id"],t["title"],", ".join(t["depends_on"]) or "无",t["verification_level"]) for t in tasks])]
    for t in tasks:
        lines.extend(["\n## "+t["id"]+" · "+t["title"],"\n**前置：** "+(", ".join(t["depends_on"]) or "无")+"；**需求：** "+", ".join(t["requirement_ids"]),"\n**输入：** "+t["inputs"],"\n**定位：** "+"；".join("`"+x+"`" for x in t["targets"]),"\n### 实施","\n".join(str(i+1)+". "+x for i,x in enumerate(t["implementation_steps"])),"\n### 验收","\n".join("- **"+a["id"]+"** "+a["criterion"] for a in t["acceptance"]),"\n**验证层/目录：** "+t["verification_level"]+" / "+t["verification_workdir"],"\n```text\n"+"\n".join(t["verification_commands"])+"\n```","\n**说明：** "+"；".join(t["verification_instructions"]),"\n**回滚：** "+t["rollback"],"\n**证据：** "+"、".join(t["evidence_required"])])
    metas["plan/TASKS.md"]=render("plan/TASKS.md","\n".join(lines),args.date)
    idx=load("governance/document-index.json")
    for entry in idx["documents"]:
        if entry["path"] in metas: entry.update(metas[entry["path"]])
    idx["updated_at"]=args.date
    save("governance/document-index.json",idx)
    print(json.dumps({"tasks":len(tasks),"cases":len(cases),"tests_executed":False,"results_reset":args.reset_results}))

if __name__=="__main__": main()
