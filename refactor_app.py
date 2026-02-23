import re

with open("app.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

dev_start = -1
dev_end = -1
for i, line in enumerate(lines):
    if 'st.subheader("🛠️ Developer Console")' in line:
        dev_start = i
    if dev_start != -1 and 'col = st.session_state.collection' in line:
        dev_end = i
        break

main_start = -1
for i, line in enumerate(lines):
    if 'st.title("노동법 RAG 챗봇")' in line:
        main_start = i
        break

if dev_start == -1 or main_start == -1:
    print("Could not find blocks. Check indices.")
    import sys; sys.exit(1)

part1 = lines[:dev_start]
dev_console = lines[dev_start:dev_end]
part2 = lines[dev_end:main_start]
main_ui = lines[main_start:]

# Fix indentation for dev_console: the original lines were under `with st.sidebar:` (which is 4 spaces indent, so lines have 8 spaces)
# We want them under `def render_dev_console():` (which is at 4 spaces, so body is at 8 spaces)
# Thus, we can keep the exact same indentation!
new_dev_console = []
new_dev_console.append("    def render_dev_console():\n")
new_dev_console.append('        step = st.session_state.get("step", "input")\n')
new_dev_console.append('        st.caption("현재 단계에 해당하는 콘솔만 표시됩니다.")\n')

for line in dev_console:
    # We want to conditionally show expanders based on the step.
    # First, let's just keep the exact same indentation.
    new_dev_console.append(line)

# Fix indentation for main_ui: add 4 spaces
new_main_ui = []
for line in main_ui:
    if line.strip() == "":
        new_main_ui.append(line)
    else:
        new_main_ui.append("    " + line)

with open("app_refactored.py", "w", encoding="utf-8") as f:
    f.writelines(part1)
    f.writelines(new_dev_console)
    f.writelines(part2)
    f.write("\n    main_col1, main_col2 = st.columns([1, 1])\n")
    f.write("    with main_col1:\n")
    f.write("        # ---------- 메인 UI ----------\n")
    for line in new_main_ui:
        if line.strip() == "# ---------- 메인 UI ----------":
            continue
        f.write(line)
    f.write("\n    with main_col2:\n")
    f.write("        render_dev_console()\n")

print("app_refactored.py created with fixed indentation.")
