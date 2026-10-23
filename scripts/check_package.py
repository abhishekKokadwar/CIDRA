"""What a built wheel must hold for `pip install cidra` to work (CI's package job).

    python scripts/check_package.py dist/cidra-0.3.2-py3-none-any.whl

Checks the version against pyproject.toml, that the sandbox Dockerfile ships
(0.2.0 shipped without it), and that the dashboard's files are exactly those its
index.html loads: a missing one is a broken page, an extra one a stale bundle
left by an earlier build (seen with a reused build/ directory). Exit 1 with the
reasons when anything is wrong.
"""

import re
import sys
import zipfile
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # the compat job runs the unit tests, which import this, on 3.10
    import tomli as tomllib

STATIC = "cidra/static/"


def problems(wheel: str, version: str) -> list[str]:
    out = []
    with zipfile.ZipFile(wheel) as z:
        names = set(z.namelist())
        meta = next((n for n in names if n.endswith(".dist-info/METADATA")), None)
        found = re.search(r"^Version: (.+)$", z.read(meta).decode(), re.M).group(1).strip() if meta else None
        if found != version:
            out.append(f"wheel version is {found}, pyproject.toml says {version}")
        if "cidra/sandbox/Dockerfile" not in names:
            out.append("cidra/sandbox/Dockerfile is missing: the sandbox image cannot be built from an install")
        if "cidra/sandbox/Dockerfile.agent" not in names:
            out.append("cidra/sandbox/Dockerfile.agent is missing: a coding agent's image cannot be built from an install")
        if STATIC + "index.html" not in names:
            return out + ["cidra/static/index.html is missing: the dashboard has no page"]
        page = z.read(STATIC + "index.html").decode()
        loaded = {STATIC + p.lstrip("/") for p in re.findall(r'(?:src|href)="(/assets/[^"]+)"', page)}
        bundled = {n for n in names if n.startswith(STATIC + "assets/")}
        out += [f"index.html loads {n}, which is not in the wheel" for n in sorted(loaded - bundled)]
        out += [f"{n} is in the wheel but index.html does not load it (a stale build?)" for n in sorted(bundled - loaded)]
        scripts = [n for n in loaded & bundled if n.endswith(".js")]
        if scripts and not any(version.encode() in z.read(n) for n in scripts):
            out.append(f"the dashboard bundle does not carry version {version}: built before the version bump?")
    return out


def main() -> int:
    version = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    found = [f"{w}: {p}" for w in sys.argv[1:] for p in problems(w, version)]
    print("\n".join(found) or f"ok: {', '.join(sys.argv[1:])} (version {version})")
    return 1 if found or not sys.argv[1:] else 0


if __name__ == "__main__":
    sys.exit(main())
