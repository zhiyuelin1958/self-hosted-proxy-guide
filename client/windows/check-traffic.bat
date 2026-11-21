@echo off
rem Show server traffic. Replace root and SERVER_IP with your SSH user and server address, or use an ssh alias.
rem eth0 counters reset at reboot; vnstat persists. Billing follows the provider's panel (outbound, or the larger of in/out).
set SSH_TARGET=root@SERVER_IP
ssh -n %SSH_TARGET% "echo '=== [1] eth0 since boot (RX = inbound, TX = outbound) ==='; uptime -s; ip -s -h link show eth0; echo ''; echo '=== [2] vnstat history ==='; vnstat; echo ''; vnstat -m"
pause
