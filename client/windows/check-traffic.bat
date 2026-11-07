@echo off
rem Show server traffic. Replace azureuser and SERVER_IP (or use an ssh alias from docs/02).
rem eth0 counters reset at reboot; vnstat persists. Billing follows the cloud provider's usage records.
set SSH_TARGET=azureuser@SERVER_IP
ssh -n %SSH_TARGET% "echo '=== [1] eth0 since boot (TX = outbound, usually billed) ==='; uptime -s; ip -s -h link show eth0; echo ''; echo '=== [2] vnstat history ==='; vnstat; echo ''; vnstat -m"
pause
