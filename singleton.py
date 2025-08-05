import os
import sys

if os.name == "nt":
    import msvcrt
else:
    import fcntl

class SingleInstance:
    def __init__(self, lockfile):
        self.lockfile = lockfile
        self.fp = None

    def already_running(self):
        self.fp = open(self.lockfile, "w")
        try:
            if os.name == "nt":
                msvcrt.locking(self.fp.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(self.fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (IOError, BlockingIOError):
            return True
        return False

    def cleanup(self):
        if self.fp:
            try:
                if os.name == "nt":
                    self.fp.seek(0)
                    msvcrt.locking(self.fp.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(self.fp, fcntl.LOCK_UN)
            except:
                pass
            self.fp.close()