import asyncio
import os
import gc
import ctypes

from fastapi import HTTPException

heavy_semaphore = asyncio.Semaphore(1)
light_semaphore = asyncio.Semaphore(2)


async def run_subprocess_safe(request, cmd: list, timeout: int = 120):
    """Run a subprocess with client-disconnect detection and overall timeout.

    If the client disconnects (page refresh, cancel button, navigate away),
    the subprocess is killed immediately, freeing server memory.
    Returns (stdout, stderr, returncode).
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        comm_task = asyncio.create_task(proc.communicate())
        elapsed = 0
        while True:
            if await request.is_disconnected():
                proc.kill()
                await proc.wait()
                comm_task.cancel()
                raise HTTPException(499, "客户端已取消")
            try:
                stdout, stderr = await asyncio.wait_for(asyncio.shield(comm_task), timeout=2.0)
                return stdout, stderr, proc.returncode
            except asyncio.TimeoutError:
                elapsed += 2
                if elapsed >= timeout:
                    proc.kill()
                    await proc.wait()
                    comm_task.cancel()
                    raise HTTPException(504, f"处理超时（{timeout}秒）")
                continue
    except HTTPException:
        raise
    except asyncio.CancelledError:
        proc.kill()
        await proc.wait()
        raise
    except Exception:
        proc.kill()
        await proc.wait()
        raise


def check_memory(threshold_mb: int = 100) -> bool:
    """Return True if available memory is above threshold."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    available_kb = int(line.split()[1])
                    return available_kb / 1024 >= threshold_mb
    except Exception:
        pass
    return True


def release_memory():
    """Release freed memory back to the OS (Linux/glibc only).

    Python's pymalloc doesn't return freed memory to the OS.
    malloc_trim(0) forces glibc to release free heap memory.
    """
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass
