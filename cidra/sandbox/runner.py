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
from docker.errors import DockerException, ImageNotFound, NotFound
from docker.models.containers import Container

from cidra import config
from cidra.sandbox import limits
from cidra.state import SandboxResult, Step


def _timeout(step: str) -> int:
    """Seconds a step may run. Test and verify runs take the configured timeout,
    read at call time so the dashboard's setting applies to the next run (G-19)."""
    return config.CONTAINER_TIMEOUT if step in ("test", "verify") else limits.TIMEOUTS[step]


_client: Optional[docker.DockerClient] = None


def client() -> docker.DockerClient:
    global _client
    if _client is None:
        _client = docker.from_env()
    return _client


def ensure_image(python: Optional[str] = None) -> str:
    """The image tag for this Python version, building it on first use.

    The default image is still built by setup (README, action.yml). The others
    come from the same Dockerfile on that version's digest-pinned base.
    """
    tag = limits.image_for(python)
    if python is None or tag == limits.IMAGE:
        return tag
    try:
        client().images.get(tag)
    except ImageNotFound:
        args = {"PYTHON_IMAGE": limits.PYTHON_IMAGES[python]}
        if python in limits.TEST_TOOLS:
            args["TEST_TOOLS"] = limits.TEST_TOOLS[python]
        client().images.build(path=str(Path(__file__).parent), tag=tag, rm=True, buildargs=args)
    return tag


def _create(network: str, image: str = limits.IMAGE):
    """Every container in this module is created here, so the caps cannot be
    forgotten or overridden at a call site. No volumes, no binds, no privileged,
    no cap_add, no host env passthrough.
    """
    return client().containers.create(
        image=image,
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
    timeout_s = timeout_s or _timeout(step)
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

    def __init__(self, source_dir: Path, python: Optional[str] = None):
        self.source_dir = source_dir
        self.python = python  # a version in limits.PYTHON_IMAGES, else the default image
        self.image = limits.IMAGE
        self.image_id: Optional[str] = None
        self.container: Optional[Container] = None
        self._patched = False  # a diff is applied on top of the pristine tree

    def __enter__(self) -> "Session":
        self.image = ensure_image(self.python)
        self.image_id = client().images.get(self.image).id  # the exact image, for the evidence block
        self.container = box = _create("none", self.image)
        box.start()
        box.put_archive(limits.WORKDIR, _tar_bytes(self.source_dir))
        code, out, err = _exec_with_timeout(
            box, ["cp", "-a", limits.WORKDIR, limits.PRISTINE], 120, limits.WORKDIR
        )
        if code != 0:
            raise RuntimeError(f"could not snapshot the checkout: {_tail(err or out)}")
        return self

    def __exit__(self, *exc) -> None:
        if self.container is not None:
            try:
                self.container.remove(force=True)
            except (DockerException, NotFound):
                pass
            self.container = None

    @property
    def _box(self) -> Container:
        """The open container: using a session outside its `with` is a bug, said plainly."""
        if self.container is None:
            raise RuntimeError("sandbox session is not open")
        return self.container

    def _workdir_tar(self) -> bytes:
        """Current /work from the session, so the installer sees applied patches."""
        blob = b"".join(self._box.get_archive(limits.WORKDIR)[0])
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
            installer = _create(network="bridge", image=self.image)
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
            try:
                blob = b"".join(installer.get_archive(limits.SITE)[0])
            except NotFound:
                blob = None  # the command installed nothing, so there is nothing to copy
        finally:
            if installer is not None:
                try:
                    installer.remove(force=True)
                except (DockerException, NotFound):
                    pass

        # Replace, not merge: packages from an earlier install (an earlier fix
        # attempt's dependency) must not linger and make a later attempt pass.
        _exec_with_timeout(self._box, ["rm", "-rf", limits.SITE], 60, limits.WORKDIR)
        # get_archive returns the directory itself, so unpack at its parent.
        if blob is not None:
            self._box.put_archive(str(Path(limits.SITE).parent.as_posix()), blob)
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
            self._box, ["sh", "-c", command], timeout_s or _timeout(step), limits.WORKDIR
        )
        return SandboxResult(
            step=step,
            exit_code=code if code is not None else 124,
            stdout_tail=_tail(out),
            stderr_tail=_tail(err),
            duration_s=time.monotonic() - started,
            timed_out=code is None,
        )

    def read_file(self, path: str, max_bytes: int = 5_000_000) -> Optional[bytes]:
        """A file from the container, whole, or None if absent or over `max_bytes`.
        Copied out as an archive, so the output-tail limit of run() does not apply."""
        try:
            stream, stat = self._box.get_archive(path)
        except NotFound:
            return None
        if stat.get("size", 0) > max_bytes:
            return None
        with tarfile.open(fileobj=io.BytesIO(b"".join(stream))) as tar:
            member = tar.next()
            data = tar.extractfile(member) if member is not None and member.isfile() else None
            return data.read() if data is not None else None

    def apply_patch(self, patch: str) -> SandboxResult:
        """Apply an LLM diff as data. Never evaluated as a command.

        Every attempt starts from the checkout as it arrived: a diff an earlier
        attempt applied is removed first. Otherwise attempt 2 lands on top of
        attempt 1, verify_fix proves the two together green, and only attempt 2
        is published (KNOWN_GAPS G-15).
        """
        if self._patched:
            restore = self.run(
                "test",
                f"find {limits.WORKDIR} -mindepth 1 -delete && cp -a {limits.PRISTINE}/. {limits.WORKDIR}/",
                timeout_s=120,
            )
            if not restore.passed:
                return restore
            self._patched = False
        self._box.put_archive(limits.WORKDIR, _patch_tar(patch))
        result = self.run(
            "test",
            "git apply --ignore-whitespace --verbose /work/.cidra.patch || "
            "git apply -p0 --ignore-whitespace --verbose /work/.cidra.patch",
            timeout_s=60,
        )
        # git apply is all-or-nothing, so a failed apply leaves the tree pristine.
        self._patched = result.passed
        return result


def _patch_tar(patch: str) -> bytes:
    buf = io.BytesIO()
    data = patch.encode()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo(".cidra.patch")
        info.size = len(data)
        info.uid = info.gid = limits.UID
        tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()
