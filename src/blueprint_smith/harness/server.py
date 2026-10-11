"""Find (or download) the Factorio 2.0.77 headless server the harness runs blueprints in."""
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

REQUIRED_VERSION = "2.0.77"
CACHE_DIR = Path.home() / ".cache" / "blueprint-smith" / f"factorio-headless-{REQUIRED_VERSION}"
DEFAULT_SERVER = CACHE_DIR / "factorio" / "bin" / "x64" / "factorio"
DOWNLOAD_URL = f"https://factorio.com/get-download/{REQUIRED_VERSION}/headless/linux64"
ENV_VAR = "BPS_FACTORIO_SERVER"

_checked: set[Path] = set()  # binaries already seen reporting REQUIRED_VERSION this process


class HarnessUnavailable(Exception):
    """No usable Factorio headless server: missing, won't run, or the wrong version."""


def find_server(path: Path | str | None = None) -> Path:
    """The headless binary (`path`, else $BPS_FACTORIO_SERVER, else DEFAULT_SERVER), checked to run and
    report REQUIRED_VERSION. Raises HarnessUnavailable with what to do about it otherwise."""
    if path is None:
        path = os.environ.get(ENV_VAR) or DEFAULT_SERVER
    path = Path(path).expanduser()
    if path in _checked:
        return path
    fix = (f"install it with `blueprint-smith install-server` (downloads {DOWNLOAD_URL} into {CACHE_DIR}) "
           f"or point ${ENV_VAR} at a Factorio {REQUIRED_VERSION} headless binary")
    if not path.is_file():
        raise HarnessUnavailable(f"no Factorio headless server at {path}: {fix}")
    try:
        out = subprocess.run([str(path), "--version"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        raise HarnessUnavailable(f"can't run {path} --version ({e}): {fix}") from None
    m = re.search(r"^Version:\s*(\d+\.\d+\.\d+)", out.stdout, re.M)
    if out.returncode or not m:
        tail = (out.stdout + out.stderr).strip()[-300:]
        raise HarnessUnavailable(f"{path} --version failed (exit {out.returncode}): {tail!r}: {fix}")
    if m.group(1) != REQUIRED_VERSION:
        raise HarnessUnavailable(f"{path} is Factorio {m.group(1)}, the harness needs {REQUIRED_VERSION}: {fix}")
    _checked.add(path)
    return path


def install_server(dest: Path | str | None = None) -> Path:
    """Download the 2.0.77 headless tarball (~57 MB, no login) and unpack it so `dest/factorio/bin/x64/factorio`
    exists. Extracts into a fresh sibling dir and renames it into place, so a failed download leaves no
    half-installed server. Returns the checked binary."""
    dest = Path(dest).expanduser() if dest else CACHE_DIR
    dest.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f".{dest.name}-", dir=dest.parent))
    try:
        archive = work / "headless.tar.xz"
        with urllib.request.urlopen(DOWNLOAD_URL, timeout=120) as r, open(archive, "wb") as f:
            shutil.copyfileobj(r, f)
        unpacked = work / "unpacked"
        with tarfile.open(archive) as tar:
            if hasattr(tarfile, "data_filter"):  # 3.12+: refuse paths/links escaping the dir
                tar.extractall(unpacked, filter="data")
            else:
                tar.extractall(unpacked)
        binary = unpacked / "factorio" / "bin" / "x64" / "factorio"
        if not binary.is_file():
            raise HarnessUnavailable(f"{DOWNLOAD_URL} didn't contain factorio/bin/x64/factorio")
        if dest.exists():
            shutil.rmtree(dest)
        unpacked.rename(dest)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return find_server(dest / "factorio" / "bin" / "x64" / "factorio")
