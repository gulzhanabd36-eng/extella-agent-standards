#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверялка подключения протокола Claude × Codex (CLAUDE_CODEX_PROTOCOL.md).

Правило класса: обязательная ссылка на протокол пары ассистентов не должна
молча исчезнуть ни из одной точки входа. Точки входа:

  1. README.md этого репозитория — упоминание CLAUDE_CODEX_PROTOCOL.md;
  2. ~/.claude/CLAUDE.md — глобальный файл Claude Code;
  3. ~/.codex/AGENTS.md — глобальный файл Codex.

Глобальные файлы (2, 3) есть только на машинах команды Гульжан: если файла нет —
это «пропуск» (skip), а не провал; но если файл ЕСТЬ и ссылки в нём нет — красный.
README проверяется всегда (репозиторий — источник истины).

Как пользоваться:
  python3 tools/check_collab_links.py            # человекочитаемо
  python3 tools/check_collab_links.py --json     # машинно
  python3 tools/check_collab_links.py --selftest # проверка самой проверялки

Коды выхода: 0 — все обязательные ссылки на месте, 1 — ссылка исчезла,
2 — не найден README репозитория (проверять нечего).

Переменные окружения для тестов (подмена путей, боевые файлы не трогаются):
  COLLAB_README, COLLAB_CLAUDE_MD, COLLAB_AGENTS_MD
"""
import json
import os
import re
import sys
import tempfile

# Признак ссылки: имя канонического файла ИЛИ имя локального зеркала.
NEEDLE = re.compile(r"CLAUDE_CODEX_PROTOCOL\.md|CLAUDE-CODEX-COLLABORATION\.md")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def points():
    home = os.path.expanduser("~")
    return [
        # (имя, путь, обязателен ли сам файл)
        ("readme", os.environ.get("COLLAB_README",
                                  os.path.join(REPO_ROOT, "README.md")), True),
        ("claude_md", os.environ.get("COLLAB_CLAUDE_MD",
                                     os.path.join(home, ".claude", "CLAUDE.md")), False),
        ("agents_md", os.environ.get("COLLAB_AGENTS_MD",
                                     os.path.join(home, ".codex", "AGENTS.md")), False),
    ]


def run():
    out = {"ok": True, "points": {}}
    for name, path, required in points():
        if not os.path.exists(path):
            if required:
                out["points"][name] = {"status": "missing_file", "path": path}
                out["ok"] = False
                out["fatal"] = "README репозитория не найден"
                return out, 2
            out["points"][name] = {"status": "skip_no_file", "path": path}
            continue
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError as e:
            out["points"][name] = {"status": "unreadable", "path": path, "error": str(e)}
            out["ok"] = False
            continue
        if NEEDLE.search(text):
            out["points"][name] = {"status": "ok", "path": path}
        else:
            out["points"][name] = {"status": "link_gone", "path": path}
            out["ok"] = False
    return out, (0 if out["ok"] else 1)


def selftest():
    """Проверялка обязана уметь провалиться: гоняем на нарочно испорченных копиях."""
    good = "вход: см. CLAUDE_CODEX_PROTOCOL.md для пары ассистентов\n"
    bad = "здесь когда-то была ссылка, но её вычистили\n"
    cases = []  # (описание, readme, claude, agents, ожидаемый код)
    cases.append(("все ссылки на месте", good, good, good, 0))
    cases.append(("ссылка вычищена из README", bad, good, good, 1))
    cases.append(("ссылка вычищена из CLAUDE.md", good, bad, good, 1))
    cases.append(("ссылка вычищена из AGENTS.md", good, good, bad, 1))
    cases.append(("глобальных файлов нет (чужая машина)", good, None, None, 0))
    cases.append(("README отсутствует", None, good, good, 2))
    failures = 0
    for desc, readme, claude, agents, want in cases:
        with tempfile.TemporaryDirectory() as td:
            def put(fname, content):
                if content is None:
                    return os.path.join(td, fname + ".absent")
                p = os.path.join(td, fname)
                open(p, "w", encoding="utf-8").write(content)
                return p
            os.environ["COLLAB_README"] = put("README.md", readme)
            os.environ["COLLAB_CLAUDE_MD"] = put("CLAUDE.md", claude)
            os.environ["COLLAB_AGENTS_MD"] = put("AGENTS.md", agents)
            _, code = run()
            mark = "ловит" if code == want else "ПРОМАХ"
            print("  [%s] %s (код %d, ждали %d)" % (mark, desc, code, want))
            if code != want:
                failures += 1
    for k in ("COLLAB_README", "COLLAB_CLAUDE_MD", "COLLAB_AGENTS_MD"):
        os.environ.pop(k, None)
    if failures:
        print("SELFTEST: ПРОВАЛ — проверялка не умеет падать где должна")
        return 1
    print("SELFTEST: OK — проверялка умеет падать")
    return 0


def main():
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    out, code = run()
    if "--json" in sys.argv:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for name, st in out["points"].items():
            print("%-10s %-12s %s" % (name, st["status"], st["path"]))
        print("итог:", "ссылки на месте" if code == 0 else "ССЫЛКА ИСЧЕЗЛА (или README не найден)")
    sys.exit(code)


if __name__ == "__main__":
    main()
