import subprocess
import os

def run():
    cli = "venv/bin/python3 manage.py makemigrations analyzer"
    print(f"Running: {cli}")
    res = subprocess.run(cli, shell=True, capture_output=True, text=True)
    with open("migration_log.txt", "w") as f:
        f.write(f"STDOUT:\n{res.stdout}\n")
        f.write(f"STDERR:\n{res.stderr}\n")
        f.write(f"RETURNCODE: {res.returncode}\n")
    print(f"Done. Return code: {res.returncode}")

if __name__ == "__main__":
    run()
