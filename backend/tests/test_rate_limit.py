from app.api.v1.router import account_login_limiter
from app.core.rate_limit import LoginRateLimiter
from app.db.seed import DEMO_PASSWORD


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_limiter_blocks_after_max_failures_and_expires():
    clock = FakeClock()
    limiter = LoginRateLimiter(max_failures=3, window_seconds=60, clock=clock)
    for _ in range(2):
        limiter.record_failure("a@x")
    assert limiter.retry_after("a@x") == 0
    limiter.record_failure("a@x")
    assert 0 < limiter.retry_after("a@x") <= 61
    assert limiter.retry_after("b@x") == 0
    clock.now += 60
    assert limiter.retry_after("a@x") == 0


def test_limiter_reset_clears_key():
    limiter = LoginRateLimiter(max_failures=1, window_seconds=60, clock=FakeClock())
    limiter.record_failure("a@x")
    assert limiter.retry_after("a@x") > 0
    limiter.reset("a@x")
    assert limiter.retry_after("a@x") == 0


def _login(client, password, email="admin@demo.local"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_login_returns_429_after_repeated_failures(client):
    for _ in range(account_login_limiter.max_failures):
        assert _login(client, "wrong-password").status_code == 401
    blocked = _login(client, DEMO_PASSWORD)
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    # Other accounts are not locked by one account's failures.
    assert _login(client, DEMO_PASSWORD, email="hr@demo.local").status_code in (200, 401)


def test_successful_login_resets_account_failures(client):
    for _ in range(account_login_limiter.max_failures - 1):
        assert _login(client, "wrong-password").status_code == 401
    assert _login(client, DEMO_PASSWORD).status_code == 200
    assert _login(client, "wrong-password").status_code == 401
    assert _login(client, DEMO_PASSWORD).status_code == 200
