"""Spike runner: python spike/harness/run.py BPFILE INX,INY OUTX,OUTY IN_ITEM OUT_ITEM BELT [warmup] [window]"""
import json, shutil, subprocess, sys, tempfile, time
from pathlib import Path

SERVER = Path.home() / ".cache/blueprint-smith/factorio-headless-2.0.77/factorio/bin/x64/factorio"
HERE = Path(__file__).parent

bp = Path(sys.argv[1]).read_text().strip()
(ix, iy), (ox, oy) = (map(int, a.split(",")) for a in sys.argv[2:4])
in_item, out_item, belt = sys.argv[4:7]
warmup = int(sys.argv[7]) if len(sys.argv) > 7 else 7200
window = int(sys.argv[8]) if len(sys.argv) > 8 else 3600

tmp = Path(tempfile.mkdtemp(prefix="bps-spike-", dir=sys.argv[9] if len(sys.argv) > 9 else None))
(tmp / "write").mkdir()
(tmp / "config.ini").write_text(f"[path]\nread-data=__PATH__executable__/../../data\nwrite-data={tmp/'write'}\n")
mods = tmp / "mods"; mods.mkdir()
(mods / "mod-list.json").write_text(json.dumps({"mods": [{"name": n, "enabled": True} for n in
    ("base", "elevated-rails", "quality", "space-age", "bps-harness")]}))
mod = mods / "bps-harness_0.1.0"; shutil.copytree(HERE / "mod", mod)
ports = [{"role": "input", "item": in_item, "belt": belt, "tile": [ix, iy], "direction": 8},
         {"role": "output", "item": out_item, "belt": belt, "tile": [ox, oy], "direction": 8}]
def lua(v):
    if isinstance(v, str): return json.dumps(v)
    if isinstance(v, (int, float)): return repr(v)
    if isinstance(v, list): return "{" + ", ".join(lua(x) for x in v) + "}"
    if isinstance(v, dict): return "{" + ", ".join(f"{k} = {lua(x)}" for k, x in v.items()) + "}"
(mod / "job.lua").write_text("return " + lua({"blueprint": bp, "ports": ports, "warmup_ticks": warmup, "window_ticks": window}) + "\n")

base = [str(SERVER), "-c", str(tmp / "config.ini"), "--mod-directory", str(mods)]
t0 = time.time()
c = subprocess.run(base + ["--create", str(tmp / "save.zip")], capture_output=True, text=True)
t1 = time.time()
print("create rc", c.returncode, f"{t1-t0:.1f}s")
if c.returncode: print(c.stdout[-3000:], c.stderr[-2000:]); sys.exit(1)
b = subprocess.run(base + ["--benchmark", str(tmp / "save.zip"), "--benchmark-ticks", str(warmup + window + 2)],
                   capture_output=True, text=True)
t2 = time.time()
print("benchmark rc", b.returncode, f"{t2-t1:.1f}s for {warmup+window+2} ticks")
res_file = tmp / "write/script-output/bps-result.json"
if not res_file.exists():
    print("NO RESULT\n", b.stdout[-4000:], b.stderr[-2000:]); print("tmp", tmp); sys.exit(1)
print(b.stdout.strip().splitlines()[-6:])
r = json.loads(res_file.read_text())
print("\n".join(r["log"]))
print("series items/s per 10s:", r["series_per_s"])
print("outputs:", r["outputs"])
ws = sorted(m["working"] for m in r["machines"])
print(f"machines={len(ws)} working min={ws[0]:.3f} max={ws[-1]:.3f}")
bad = sorted(r["machines"], key=lambda m: m["working"])[:5]
for m in bad[:10]: print("  low:", m["position"], m["statuses"])
print("tmp", tmp)
