#!/usr/bin/env python3
"""One bounded Claude Code consultation; preserve exact prompt and response."""
import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def response_text(returncode, stdout):
    if returncode != 0:
        raise ValueError('Claude exited unsuccessfully; no position received')
    data = json.loads(stdout)
    if data.get('is_error') or data.get('subtype') != 'success':
        raise ValueError('Claude did not complete successfully')
    if not data.get('session_id') or not isinstance(data.get('result'),str) or not data['result'].strip():
        raise ValueError('Missing session or substantive response')
    return data['result']


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('record', type=Path)
    ap.add_argument('output', type=Path, help='New directory; never overwrite an earlier consultation')
    ap.add_argument('--binary', type=Path)
    ap.add_argument('--evidence', type=Path, help='Verbatim diff and test results to review')
    args = ap.parse_args()
    binary = args.binary
    if binary is None:
        root = Path.home() / 'Library/Application Support/Claude/claude-code'
        paths = list(root.glob('*/claude.app/Contents/MacOS/claude'))
        binary = max(paths, key=lambda p: tuple(map(int, re.findall(r'\d+', p.parts[-5]))))
    auth = subprocess.run([str(binary), 'auth', 'status'], capture_output=True, text=True, timeout=20)
    info = json.loads(auth.stdout)
    if auth.returncode or not info.get('loggedIn') or info.get('authMethod') != 'claude.ai':
        raise SystemExit('Authenticated subscription CLI required; no automatic API fallback')
    args.output.mkdir(parents=True, exist_ok=False)
    canon = Path(__file__).resolve().parents[1] / 'CLAUDE_CODEX_PROTOCOL.md'
    prompt = ('Ты свежая независимая сессия Claude Code, приглашённая по поручению Гульжан. '
              'Ничего не меняй. Ответь по существу на каждый спорный пункт, с причинами. '
              'Факты из цитат не выдавай за лично проверенные. Ты не автор прежнего чата. '
              'Укажи условия согласования и оставшиеся проверки.\n\nКАНОН ДОСЛОВНО:\n' +
              canon.read_text() + '\n\nОБЩАЯ ЗАПИСЬ ДОСЛОВНО:\n' + args.record.read_text())
    if args.evidence:
        prompt += '\n\nДОКАЗАТЕЛЬСТВА И ДИФФ ДОСЛОВНО:\n' + args.evidence.read_text()
    (args.output / 'prompt.txt').write_text(prompt)
    command = [str(binary), '-p', '--tools', '', '--max-turns', '3',
               '--restricted', '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
               '--output-format', 'json', '--no-session-persistence']
    meta = {'command': command, 'started_at': datetime.now(timezone.utc).isoformat(),
            'authMethod': info['authMethod'], 'timeout_seconds': 180, 'state': 'started'}
    try:
        result = subprocess.run(command, input=prompt, text=True, capture_output=True,
                                cwd=canon.parent, timeout=180)
        (args.output / 'stdout.json').write_text(result.stdout)
        (args.output / 'stderr.txt').write_text(result.stderr)
        meta['exit_code'] = result.returncode
        answer = response_text(result.returncode, result.stdout)
        (args.output / 'answer.md').write_text(answer)
        assert (args.output / 'answer.md').read_text() == answer
        meta['state'] = 'response_received'
    except (subprocess.TimeoutExpired, ValueError, OSError) as exc:
        if isinstance(exc,subprocess.TimeoutExpired):
            for name,value in [('stdout.json',exc.stdout),('stderr.txt',exc.stderr)]:
                if isinstance(value,bytes):
                    value = value.decode('utf-8',errors='replace')
                (args.output/name).write_text(value or '')
        meta['state'] = 'no_response'
        meta['error'] = type(exc).__name__
        raise SystemExit('No valid response; do not mark agreement or retry automatically') from exc
    finally:
        meta['finished_at'] = datetime.now(timezone.utc).isoformat()
        (args.output / 'provenance.json').write_text(json.dumps(meta, indent=2))
    print(args.output / 'answer.md')


if __name__ == '__main__':
    main()
