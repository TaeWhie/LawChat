# -*- coding: utf-8 -*-
"""채팅 블록을 _render_chat_ui()로 추출하고 main()에서는 fragment 호출만 하도록 수정."""
from pathlib import Path

path = Path(__file__).resolve().parent.parent / "app_chatbot.py"
lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
if not lines[-1].endswith("\n"):
    lines[-1] += "\n"

# 1-based: chat block 464-925 -> index 463-924
chat_block = lines[463:925]
indented = ["    " + line for line in chat_block]
func_body = "".join(indented)
func_def = "def _render_chat_ui():\n" + func_body + "\n\n"

idx_main = next(i for i, L in enumerate(lines) if L.strip() == "def main():")
frag = '    _run_chat = getattr(st, "fragment", lambda f: f)(_render_chat_ui)\n    _run_chat()\n'

new_lines = lines[:idx_main] + [func_def] + lines[idx_main:464] + [frag + "\n"] + lines[925:]
path.write_text("".join(new_lines), encoding="utf-8")
print("Done: _render_chat_ui added, main() updated")
