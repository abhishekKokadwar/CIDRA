"""Container execution. See docs/6_sandbox_spec.md §6.

The ONLY module that imports the Docker SDK. Every hard rule from §3 is enforced
here rather than left to callers:

  - never privileged, never mounts the docker socket, no host bind mounts
  - network ON iff step == "install"    (not a caller decision)
  - mem / cpu / pids limits ALWAYS applied  (no override parameter exists)
  - every exec has a timeout
  - the container is destroyed in a finally block
  - no host secrets are passed in
  - LLM output arrives as `patch` (data), never as `command`
"""

import io
import tarfile
import threading
import time
from pathlib import Path
from typing import Optional

import docker
from docker.errors import DockerException, NotFound

from cidra.sandbox import limits
from cidra.state import SandboxResult, Step

_client: Optional[docker.DockerClient] = None


def client() -> docker.DockerClient:
    global _client
    if _client is None:
        _client = docker.from_env()
    return _client


def _create(network: str):
    """Every container in this module is created here, so the caps cannot be
    forgotten or overridden at a call site. No volumes, no binds, no privileged,
    no cap_add, no host env passthrough.
    """
    return client().containers.create(
        image=limits.IMAGE,
        command="sleep infinity",
        network_mode=network,
        mem_limit=limits.MEM_LIMIT,
        memswap_limit=limits.MEMSWAP_LIMIT,
        cpu_quota=limits.CPU_QUOTA,
        cpu_period=limits.CPU_PERIOD,
        pids_limit=limits.PIDS_LIMIT,
        working_dir=limits.WORKDIR,
        environment={
            "PYTHONDONTWRITEBYTECODE": "1",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            # Packages installed by the install step live here.
            "PYTHONPATH": limits.SITE,
            "PATH": f"{limits.SITE}/bin:/usr/local/bin:/usr/bin:/bin",
        },
        security_opt=["no-new-privileges"],
        detach=True,
    )


def _tar_bytes(src: Path) -> bytes:
    """Pack a host directory for put_archive. Skips VCS and caches."""
    skip = {".git", "__pycache__", ".pytest_cache", ".venv", "node_modules"}
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for path in sorted(src.rglob("*")):
            if any(part in skip for part in path.relative_to(src).parts):
                continue
            info = tar.gettarinfo(str(path), arcname=str(path.relative_to(src).as_posix()))
            # Files land owned by the non-root container user.
            info.uid = info.gid = limits.UID
            info.uname = info.gname = limits.USER
            if path.is_file():
                data = path.read_bytes()
                # The container is Linux; a CRLF host checkout would make every
                # unified diff fail to apply. Normalise text on the way in.
                if b"\x00" not in data:
                    data = data.replace(b"\r\n", b"\n")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            elif path.is_dir():
                tar.addfile(info)
    return buf.getvalue()


def _tail(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace")
    if len(text) <= limits.TAIL_BYTES:
        return text
    return "...[truncated]...\n" + text[-limits.TAIL_BYTES :]


def _exec_with_timeout(container, cmd: list[str], timeout_s: int, workdir: str):
    """Run a command, killing the container if it overruns.

    The Docker SDK's exec_run has no timeout, so a watchdog kills the container
    out from under it — exec_run then returns and we report timed_out.
    """
    result: dict = {}

    def target():
        try:
            result["out"] = container.exec_run(
                cmd, workdir=workdir, user=limits.USER, demux=True
            )
        except Exception as e:  # container killed mid-exec
            result["err"] = e

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout_s)

    if thread.is_alive():
        try:
            container.kill()
        except (DockerException, NotFound):
            pass
        thread.join(5)
        return None, b"", b"timed out"

    if "err" in result:
        return None, b"", str(result["err"]).encode()

    out = result["out"]
    stdout, stderr = out.output if isinstance(out.output, tuple) else (out.output, b"")
    return out.exit_code, stdout or b"", stderr or b""


def run_in_sandbox(
    step: Step,
    source_dir: Path,
    command: str,
    patch: Optional[str] = None,
    timeout_s: Optional[int] = None,
) -> SandboxResult:
    """Create a container, run one step, destroy it.

    `command` is CIDRA-authored and fixed. `patch` is the only LLM-supplied input
    and is written as a file, never executed as a command.

    Returns a SandboxResult even when the command fails or times out — a red test
    is a normal result, not an exception. Raises only on infrastructure failure.
    """
    timeout_s = timeout_s or limits.TIMEOUTS[step]
    # Network is derived from the step, never chosen by the caller.
    network = "bridge" if step == "install" else "none"

    started = time.monotonic()
    container = None
    try:
        container = _create(network)
        container.start()

        # The image already has the user and an owned /work, so nothing here
        # ever runs as root.
        container.put_archive(limits.WORKDIR, _tar_bytes(source_dir))

        if patch is not None:
            # Data, not code: written to a file and applied by git, never evaluated.
            container.put_archive(limits.WORKDIR, _patch_tar(patch))
            # --ignore-whitespace tolerates CRLF from a Windows host checkout;
            # -p0/-p1 fallback covers diffs with and without the a/ b/ prefix.
            apply_cmd = (
                "git apply --ignore-whitespace --verbose /work/.cidra.patch || "
                "git apply -p0 --ignore-whitespace --verbose /work/.cidra.patch"
            )
            code, out, err = _exec_with_timeout(
                container, ["sh", "-c", apply_cmd], 60, limits.WORKDIR
            )
            if code != 0:
                return SandboxResult(
                    step=step,
                    exit_code=code if code is not None else 124,
                    stdout_tail=_tail(out),
                    stderr_tail=_tail(err) or "patch did not apply",
                    duration_s=time.monotonic() - started,
                    timed_out=code is None,
                )

        code, out, err = _exec_with_timeout(
            container, ["sh", "-c", command], timeout_s, limits.WORKDIR
        )
        return SandboxResult(
            step=step,
            exit_code=code if code is not None else 124,
            stdout_tail=_tail(out),
            stderr_tail=_tail(err),
            duration_s=time.monotonic() - started,
            timed_out=code is None,
        )
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except (DockerException, NotFound):
                pass


class Session:
    """One container across several steps. See docs/6_sandbox_spec.md §6.1.

    run_in_sandbox creates and destroys a container per call, so anything pip
    installed is gone by the next step. A session keeps one container alive so
    install -> test -> patch -> verify share a filesystem, which is what the
    graph's reproduce/fix/verify sequence actually needs.

    Network is still per-step: the container is created with network off, and
    only an "install" step is allowed to reach the outside. Because a live
    container cannot change networks, install runs in its own throwaway
    container and its site-packages are copied back in.

    Use as a context manager so the container is always destroyed.
    """

    def __init__(self, source_dir: Path):
        self.source_dir = source_dir
        self.container = None

    def __enter__(self) -> "Session":
        self.container = _create("none")
        self.container.start()
        self.container.put_archive(limits.WORKDIR, _tar_bytes(self.source_dir))
        return self

    def __exit__(self, *exc) -> None:
        if self.container is not None:
            try:
                self.container.remove(force=True)
            except (DockerException, NotFound):
                pass
            self.container = None

    def _workdir_tar(self) -> bytes:
        """Current /work from the session, so the installer sees applied patches."""
        blob = b"".join(self.container.get_archive(limits.WORKDIR)[0])
        # get_archive wraps the dir ("work/..."); re-root so it unpacks into /work.
        src = tarfile.open(fileobj=io.BytesIO(blob))
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as out:
            prefix = Path(limits.WORKDIR).name + "/"
            for member in src.getmembers():
                if not member.name.startswith(prefix):
                    continue
                member.name = member.name[len(prefix) :]
                if not member.name:
                    continue
                out.addfile(member, src.extractfile(member) if member.isfile() else None)
        return buf.getvalue()

    def install(self, command: str) -> SandboxResult:
        """Run the one network-enabled step, then copy its packages in.

        Deliberately a separate container: the session container never has
        network, so an LLM patch can never execute with egress. Packages are
        installed to a fixed --target, tarred out, and unpacked into the session,
        where SITE is added to PYTHONPATH by run().
        """
        started = time.monotonic()
        installer = None
        try:
            installer = _create(network="bridge")
            installer.start()
            # Seed from the SESSION, not the host: after apply_patch the session
            # holds the patched manifest and the host copy is stale.
            installer.put_archive(limits.WORKDIR, self._workdir_tar())
            code, out, err = _exec_with_timeout(
                installer,
                ["sh", "-c", f"{command} --target {limits.SITE}"],
                limits.TIMEOUTS["install"],
                limits.WORKDIR,
            )
            if code != 0:
                return SandboxResult(
                    step="install",
                    exit_code=code if code is not None else 124,
                    stdout_tail=_tail(out),
                    stderr_tail=_tail(err),
                    duration_s=time.monotonic() - started,
                    timed_out=code is None,
                )
            blob = b"".join(installer.get_archive(limits.SITE)[0])
        finally:
            if installer is not None:
                try:
                    installer.remove(force=True)
                except (DockerException, NotFound):
                    pass

        # get_archive returns the directory itself, so unpack at its parent.
        self.container.put_archive(str(Path(limits.SITE).parent.as_posix()), blob)
        return SandboxResult(
            step="install",
            exit_code=0,
            stdout_tail=_tail(out),
            stderr_tail=_tail(err),
            duration_s=time.monotonic() - started,
            timed_out=False,
        )

    def run(self, step: Step, command: str, timeout_s: Optional[int] = None) -> SandboxResult:
        """Run a step in the shared container. Never has network."""
        if step == "install":
            raise ValueError("use Session.install(): the session container has no network")
        started = time.monotonic()
        code, out, err = _exec_with_timeout(
            self.container, ["sh", "-c", command], timeout_s or limits.TIMEOUTS[step], limits.WORKDIR
        )
        return SandboxResult(
            step=step,
            exit_code=code if code is not None else 124,
            stdout_tail=_tail(out),
            stderr_tail=_tail(err),
            duration_s=time.monotonic() - started,
            timed_out=code is None,
        )

    def apply_patch(self, patch: str) -> SandboxResult:
        """Apply an LLM diff as data. Never evaluated as a command."""
        self.container.put_archive(limits.WORKDIR, _patch_tar(patch))
        return self.run(
            "test",
            "git apply --ignore-whitespace --verbose /work/.cidra.patch || "
            "git apply -p0 --ignore-whitespace --verbose /work/.cidra.patch",
            timeout_s=60,
        )


def _patch_tar(patch: str) -> bytes:
    buf = io.BytesIO()
    data = patch.encode()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo(".cidra.patch")
        info.size = len(data)
        info.uid = info.gid = limits.UID
        tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()
