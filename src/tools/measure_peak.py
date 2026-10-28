"""Run a command and report the peak commit of its whole process tree (Windows job object).

python measure_peak.py [NAME=value ...] -- <program> <args...>
Children such as the ffmpeg encoder count too, which is what a group memory cap sees.
NAME=value pairs before `--` are set in the child's environment.
"""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time


class Basic(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wt.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wt.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wt.DWORD), ("SchedulingClass", wt.DWORD)]


class Extended(ctypes.Structure):
    _fields_ = [("Basic", Basic), ("IoInfo", ctypes.c_ulonglong * 6), ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


def main():
    sep = sys.argv.index("--")
    cmd = sys.argv[sep + 1:]
    env = dict(os.environ, **dict(a.split("=", 1) for a in sys.argv[1:sep]))
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wt.HANDLE
    job = k32.CreateJobObjectW(None, None)
    t0 = time.time()
    p = subprocess.Popen(cmd, env=env)
    if not k32.AssignProcessToJobObject(wt.HANDLE(job), wt.HANDLE(int(p._handle))):
        print("assign failed", ctypes.get_last_error(), flush=True)
    code = p.wait()
    info = Extended()
    k32.QueryInformationJobObject(wt.HANDLE(job), 9, ctypes.byref(info), ctypes.sizeof(info), None)
    print(f"PEAK job={info.PeakJobMemoryUsed / 2 ** 20:.0f}MiB process={info.PeakProcessMemoryUsed / 2 ** 20:.0f}MiB "
          f"code={code} t={time.time() - t0:.1f}s", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
