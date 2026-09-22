#!/usr/bin/env python3
"""One fresh read-only Codex CLI consultation using existing ChatGPT login."""
import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('record', type=Path)
    ap.add_argument('output', type=Path)
    ap.add_argument('--evidence', type=Path)
    ap.add_argument('--binary', default='/Applications/ChatGPT.app/Contents/Resources/codex')
    args = ap.parse_args()
    auth = subprocess.run([args.binary,'login','status'],capture_output=True,text=True,timeout=20)
    if auth.returncode or 'ChatGPT' not in auth.stdout + auth.stderr:
        raise SystemExit('Existing ChatGPT login required; no API fallback')
    args.output.mkdir(parents=True,exist_ok=False)
    canon = Path(__file__).resolve().parents[1]/'CLAUDE_CODEX_PROTOCOL.md'
    prompt = ('Ты свежий Codex CLI, приглашённый Claude по поручению Гульжан. '
              'Ответь на каждый спорный пункт кратко с причинами. Не меняй файлы, '
              'не вызывай внешние действия, не публикуй, не делегируй. Ты не старый GUI-чат. '
              'Принимаемые по цитате факты не выдавай за лично проверенные. '
              'Верни только независимый разбор и оставшиеся ограничения.\n\nКАНОН:\n'+
              canon.read_text()+'\n\nЗАПИСЬ ДОСЛОВНО:\n'+args.record.read_text())
    if args.evidence:
        prompt += '\n\nДИФФ И ПРОВЕРКИ ДОСЛОВНО:\n'+args.evidence.read_text()
    (args.output/'prompt.txt').write_text(prompt)
    answer_path = args.output/'answer.md'
    command = [args.binary,'exec','--ignore-user-config','--skip-git-repo-check',
               '--ephemeral','--sandbox','read-only','-c','approval_policy="never"',
               '--json','--output-last-message',str(answer_path),'-']
    meta = {'command':command,'started_at':datetime.now(timezone.utc).isoformat(),
            'authMethod':'ChatGPT','timeout_seconds':180,'state':'started'}
    try:
        result = subprocess.run(command,input=prompt,capture_output=True,text=True,
                                cwd=canon.parent,timeout=180)
        (args.output/'stdout.jsonl').write_text(result.stdout)
        (args.output/'stderr.txt').write_text(result.stderr)
        meta['exit_code'] = result.returncode
        events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        meta['session_id'] = next((e.get('thread_id') for e in events if e.get('type')=='thread.started'),None)
        if result.returncode or not answer_path.exists() or not answer_path.read_text().strip():
            raise ValueError('No completed substantive answer')
        if not meta['session_id']:
            raise ValueError('Missing session provenance')
        meta['state'] = 'response_received'
    except (subprocess.TimeoutExpired,ValueError,OSError) as exc:
        if isinstance(exc,subprocess.TimeoutExpired):
            for name,value in [('stdout.jsonl',exc.stdout),('stderr.txt',exc.stderr)]:
                if isinstance(value,bytes):
                    value = value.decode('utf-8',errors='replace')
                (args.output/name).write_text(value or '')
        answer_path.unlink(missing_ok=True)
        meta.update(state='no_response',error=type(exc).__name__)
        raise SystemExit('No valid answer; no automatic retry') from exc
    finally:
        meta['finished_at'] = datetime.now(timezone.utc).isoformat()
        (args.output/'provenance.json').write_text(json.dumps(meta,indent=2))
    print(answer_path)


if __name__ == '__main__':
    main()
