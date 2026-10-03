# Terminal demo for the README. Render from the repository root:
#   vhs docs/demo.tape
#   gifsicle -O3 --lossy=100 --colors 48 -b docs/demo.gif
# Uses only the free, deterministic mock agent. No API keys, nothing is spent.

Output docs/demo.gif

Set Shell "bash"
Set FontSize 18
Set Width 1200
Set Height 700
Set Padding 16
Set Theme "Catppuccin Mocha"
Set TypingSpeed 40ms
Set Framerate 12

Hide
Type `export BASH_SILENCE_DEPRECATION_WARNING=1 PS1='$ '` Enter
Type `uv sync -q && export PATH="$PWD/.venv/bin:$PATH"` Enter
Type `rm -rf /tmp/rerun-bench-demo && mkdir -p /tmp/rerun-bench-demo/home && cd /tmp/rerun-bench-demo` Enter
Type `export HOME=/tmp/rerun-bench-demo/home && clear` Enter
Sleep 2s
Show

Type "rerun-bench run --agent mock --tasks all --runs 5 --out results/ --no-report"
Sleep 800ms
Enter
Sleep 4s
Type "rerun-bench report results/ | tail -n 16"
Sleep 800ms
Enter
Sleep 9s
