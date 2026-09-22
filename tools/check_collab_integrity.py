#!/usr/bin/env python3
"""Check canonical mirror, record state, and response failure handling."""
import argparse
import json
import re
import tempfile
import subprocess
import sys
from unittest.mock import patch
from pathlib import Path
from collab_claude_once import response_text, main as consult

STATES = {'черновик', 'ожидает ответа Codex', 'ожидает ответа Claude',
          'согласовано', 'выполняется', 'готово', 'заблокировано', 'нужен выбор Гульжан'}


def check(canon, mirror, record):
    errors = []
    for path in (canon, mirror, record):
        if not path.is_file():
            errors.append('missing target: ' + str(path))
    if errors:
        return errors
    def body(path):
        text = path.read_text()
        return text[text.index('**Граница действия.**'):]
    try:
        if body(canon) != body(mirror):
            errors.append('mirror diverged')
    except ValueError:
        errors.append('missing canonical body marker')
    text = record.read_text()
    match = re.search(r'^Статус: \*\*(.+?)\*\*$', text, re.M)
    state = match.group(1) if match else ''
    if state not in STATES:
        errors.append('unknown status')
    if state in {'согласовано', 'выполняется', 'готово'}:
        for role in ('Claude', 'Codex'):
            if not re.search(r'^Происхождение ' + role + r': \S.+$', text, re.M):
                errors.append('missing provenance: ' + role)
            match = re.search(r'^## ' + role + r' — позиция[^\n]*\n(.*?)(?=^## |\Z)', text, re.M | re.S)
            if not match or not match.group(1).strip() or '(ожидается' in match.group(1):
                errors.append('missing position: ' + role)
    if state == 'готово' and 'Проверка завершена:' not in text:
        errors.append('missing completion evidence')
    return errors


def selftest():
    with tempfile.TemporaryDirectory() as td:
        a,b,r = [Path(td)/n for n in ('canon','mirror','record')]
        good = '**Граница действия.**\nCanonical body\n'
        record = ('Статус: **согласовано**\nПроисхождение Claude: session example\n'
                  'Происхождение Codex: task example\n## Claude — позиция\nAccept with evidence\n'
                  '## Codex — позиция\nAccept with evidence\n')
        a.write_text(good); b.write_text(good); r.write_text(record)
        assert not check(a,b,r)
        b.write_text(good+'corrupt'); assert check(a,b,r)
        b.write_text(good); a.unlink(); assert check(a,b,r); a.write_text(good)
        r.write_text(record.replace('Accept with evidence\n','',1)); assert check(a,b,r)
        r.write_text(record.replace('Происхождение Claude: session example\n','')); assert check(a,b,r)
        r.write_text(record.replace('согласовано','готово')); assert check(a,b,r)
        r.write_text(record.replace('согласовано','unrecognized')); assert check(a,b,r)
    valid = json.dumps({'subtype':'success','session_id':'s','result':'answer'})
    assert response_text(0,valid) == 'answer'
    for code, output in [(1,valid),(0,''),(0,'{}'),(0,valid.replace('answer','')),
                         (0,valid.replace('success','error_max_turns'))]:
        try:
            response_text(code,output)
        except ValueError:
            continue
        raise AssertionError('invalid result accepted')
    # Exercise actual runner error paths without invoking any model.
    auth = subprocess.CompletedProcess([],0,'{"loggedIn":true,"authMethod":"claude.ai"}','')
    failures = [subprocess.TimeoutExpired('claude',180),
                subprocess.CompletedProcess([],1,valid,'failure'),
                subprocess.CompletedProcess([],0,'','')]
    for failure in failures:
        with tempfile.TemporaryDirectory() as td:
            record = Path(td)/'record.md'; record.write_text('test consultation')
            output = Path(td)/'out'
            with patch.object(sys,'argv',['consult',str(record),str(output),'--binary','fake']), \
                 patch('collab_claude_once.subprocess.run',side_effect=[auth,failure]):
                try:
                    consult()
                except SystemExit:
                    pass
                else:
                    raise AssertionError('failed transport accepted')
            assert not (output/'answer.md').exists()
            assert json.loads((output/'provenance.json').read_text())['state'] == 'no_response'
    print('SELFTEST OK: divergence, missing target, empty position, provenance, states, CLI failures')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--mirror', type=Path)
    ap.add_argument('--record', type=Path)
    args = ap.parse_args()
    if args.selftest:
        selftest()
    else:
        if not args.mirror or not args.record:
            ap.error('--mirror and --record required')
        errors = check(Path(__file__).resolve().parents[1]/'CLAUDE_CODEX_PROTOCOL.md',args.mirror,args.record)
        print(json.dumps({'ok':not errors,'errors':errors},ensure_ascii=False))
        raise SystemExit(bool(errors))
