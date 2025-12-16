def log_info(msg: str):
    print(f"\033[92m[INFO]\033[0m {msg}")


def log_warn(msg: str):
    print(f"\033[93m[WARN]\033[0m {msg}")


def log_error(msg: str):
    print(f"\033[91m[ERROR]\033[0m {msg}")
