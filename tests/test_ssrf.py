import pytest

from app.core.ssrf import SSRFError, is_blocked_ip, validate_url


def res(*ips):
    return lambda host, port: list(ips)


@pytest.mark.parametrize(
    "ip",
    ["127.0.0.1", "10.0.0.5", "192.168.1.1", "172.16.0.1", "169.254.169.254", "0.0.0.0", "100.64.0.1",
     "::1", "fe80::1", "fc00::1", "::ffff:127.0.0.1", "::ffff:169.254.169.254", "not-an-ip"],
)
def test_blocked_ips(ip):
    assert is_blocked_ip(ip)


@pytest.mark.parametrize("ip", ["93.184.216.34", "8.8.8.8", "2606:4700:4700::1111"])
def test_public_ips_allowed(ip):
    assert not is_blocked_ip(ip)


@pytest.mark.parametrize(
    "url",
    ["ftp://example.com/", "file:///etc/passwd", "gopher://example.com", "javascript:alert(1)",
     "http://example.com:8080/", "https://example.com:22/", "http://user:pw@example.com/",
     "http:///nohost", "", "x" * 3000],
)
def test_bad_urls_rejected(url):
    with pytest.raises(SSRFError):
        validate_url(url, res("93.184.216.34"))


def test_private_resolution_rejected():
    with pytest.raises(SSRFError):
        validate_url("http://evil.example/", res("127.0.0.1"))


def test_mixed_resolution_rejected():
    # One public and one private answer: reject (DNS rebinding style).
    with pytest.raises(SSRFError):
        validate_url("http://evil.example/", res("93.184.216.34", "10.0.0.1"))


def test_unresolvable_rejected():
    def boom(host, port):
        raise OSError("nxdomain")

    with pytest.raises(SSRFError):
        validate_url("http://nope.invalid/", boom)


def test_literal_metadata_ip_rejected():
    with pytest.raises(SSRFError):
        validate_url("http://169.254.169.254/latest/meta-data/", lambda h, p: [h])


def test_valid_url():
    t = validate_url("https://example.com/privacy", res("93.184.216.34"))
    assert (t.host, t.port, t.ip) == ("example.com", 443, "93.184.216.34")
