import subprocess
import os
import signal
import sys

class ExternalProcessManager:
    def __init__(self, executable_path, args=[]):
        self.executable_path = executable_path
        self.args = args
        self.process = None

    def start(self):
        if self.process is None or self.process.poll() is not None:
            self.process = subprocess.Popen([self.executable_path] + self.args)
            print(f"Process started with PID {self.process.pid}")
        else:
            print("Process is already running.")

    def stop(self):
        if self.process is not None:
            try:
                os.kill(self.process.pid, signal.SIGTERM)
                print(f"Sent SIGTERM to PID {self.process.pid}")
                self.process.wait()  # Optionally wait for the process to terminate
                self.process = None
            except ProcessLookupError:
                print("Process already terminated or PID not found.")
        else:
            print("No process is running.")

    def status(self):
        if self.process is None:
            print("No process is running.")
        elif self.process.poll() is None:
            print(f"Process is running with PID {self.process.pid}")
        else:
            print(f"Process terminated with exit code {self.process.returncode}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 script.py <start|stop|status> <executable_path> [args...]")
        sys.exit(1)

    command = sys.argv[1]
    executable_path = sys.argv[2]
    args = sys.argv[3:]

    manager = ExternalProcessManager(executable_path, args)

    if command == "start":
        manager.start()
    elif command == "stop":
        manager.stop()
    elif command == "status":
        manager.status()
    else:
        print("Invalid command. Use 'start', 'stop', or 'status'.")