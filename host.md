# Host baseline: SSH, firewall, updates

Every guide in this repository secures a service; this one secures the machine under them. Apply it once per host before exposing anything.

## 1. SSH: keys only, no root login

Add your public key to `~/.ssh/authorized_keys` and confirm that key login works **before** disabling passwords. Keep the current session open while testing changes.

`/etc/ssh/sshd_config` (or a file in `/etc/ssh/sshd_config.d/`):

```
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
```

```bash
sudo sshd -t && sudo systemctl reload ssh    # sshd on RHEL-family systems
```

Add a second factor for SSH per [mfa.md](mfa.md): TOTP via [google-authenticator-libpam](https://github.com/google/google-authenticator-libpam) or push approval via Duo's `pam_duo`.

## 2. Firewall: default deny inbound

```bash
# Debian/Ubuntu (ufw)
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

RHEL-family systems use firewalld (`firewall-cmd --permanent --add-service=https` and so on) with the same posture. Open only the ports the TLS-terminating layer needs; databases and app servers stay unreachable from outside per their guides. Docker-published ports bypass ufw entirely; see [docker.md](docker.md) before relying on the firewall.

## 3. Brute-force protection and updates

- fail2ban ([github.com/fail2ban/fail2ban](https://github.com/fail2ban/fail2ban)) or CrowdSec ([crowdsec.net](https://www.crowdsec.net/)) bans repeated authentication failures against SSH and login panels.
- Automate security patches: `unattended-upgrades` on Debian/Ubuntu, `dnf-automatic` on RHEL-family systems.

## 4. Verify

```bash
ss -tlnp                          # only intended listeners, on intended addresses
sudo ufw status verbose           # default deny incoming, minimal allow list
ssh -o PreferredAuthentications=password user@host   # expect: Permission denied
```

Run the SSH test from a second terminal before closing your working session.

## Sources (checked September 2026)

- OpenSSH sshd_config manual: https://man.openbsd.org/sshd_config
- fail2ban: https://github.com/fail2ban/fail2ban
- CrowdSec: https://www.crowdsec.net/
- google-authenticator-libpam: https://github.com/google/google-authenticator-libpam
