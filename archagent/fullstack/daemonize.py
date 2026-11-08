#!/usr/bin/env python3
"""Double-fork daemonizer — escapes the tool-call process cleanup.

Usage: daemonize.py LOGFILE -- COMMAND [ARGS...]

Forks, setsid, forks again, redirects stdio to LOGFILE, then execs
COMMAND.  The resulting process is reparented to init (PPID 1) in its
own session and survives the end of the spawning tool call.
"""
import os
import sys

def main() -> None:
    if len(sys.argv) < 4 or sys.argv[2] != "--":
        print(__doc__)
        sys.exit(2)
    logfile = sys.argv[1]
    cmd = sys.argv[3:]

    pid = os.fork()
    if pid > 0:
        # parent waits briefly for the intermediate to exit
        os.waitpid(pid, 0)
        print(f"daemonized -> {cmd[:3]}... (log: {logfile})")
        return

    # intermediate child: new session, then fork again
    os.setsid()
    pid2 = os.fork()
    if pid2 > 0:
        os._exit(0)

    # daemon: redirect stdio, close old fds, exec
    fd = os.open(logfile, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(fd, 0)
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    if fd > 2:
        os.close(fd)
    os.execvp(cmd[0], cmd)

if __name__ == "__main__":
    main()
