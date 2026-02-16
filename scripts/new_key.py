import secrets
import string

def make_key(prefix="live", length=32):
    alphabet = string.ascii_letters + string.digits
    token = "".join(secrets.choice(alphabet) for _ in range(length))
    return f"{prefix}_{token}"

if __name__ == "__main__":
    print(make_key())