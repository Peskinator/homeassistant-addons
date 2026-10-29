#!/usr/bin/env python3
"""Test the real kill-switch rules on a private IPv4/IPv6 Docker network.

Renaming the isolated test interface to tun0 simulates the permitted interface;
this does not establish a real VPN or contact a VPN/Soulseek provider.
"""
import json
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

from test_slskd_persistence import build, output, run


def fetch(container,address,expect,source=None):
    args=['docker','exec',container,'wget','-T','2','-t','1','-qO-']
    if source: args+=['--bind-address='+source]
    result=subprocess.run([*args,f'http://{address}:5030/api/v0/application'],capture_output=True)
    assert (result.returncode==0)==expect, f'Unexpected network access for {address}: expected {expect}'


def main():
    stamp=uuid.uuid4().hex[:8]
    network='slskd-vpn-test-'+stamp
    peer=network+'-peer'
    client=network+'-client'
    missing=network+'-missing-profile'
    browser=network+'-browser'
    image='slskd-vpn-test:'+stamp
    build(image,'vpn-test')
    try:
        run('docker','network','create','--opt','com.docker.network.bridge.enable_ip_masquerade=false','--subnet','172.29.254.0/24','--ipv6','--subnet','fd7a:7a::/64',network)
        # The peer is a real local slskd HTTP service, with no external network.
        run('docker','run','-d','--name',peer,'--network',network,'--ip','172.29.254.3','--ip6','fd7a:7a::3',
            '--cap-add','NET_ADMIN',
            '-e','SLSKD_NO_AUTH=true','-e','SLSKD_NO_CONNECT=true','-e','SLSKD_NO_VERSION_CHECK=true','-e','SLSKD_APP_DIR=/tmp/test-state',
            '--entrypoint','/bin/bash',image,'-c','ip route del default 2>/dev/null || true; ip -6 route del default 2>/dev/null || true; mkdir -p /tmp/test-state && exec ./slskd')
        run('docker','run','-d','--name',client,'--network',network,'--ip','172.29.254.4','--ip6','fd7a:7a::4',
            '--cap-add','NET_ADMIN','--entrypoint','/bin/bash',image,'-c','ip route del default 2>/dev/null || true; ip -6 route del default 2>/dev/null || true; sleep 600')
        for _ in range(30):
            ready=subprocess.run(['docker','exec',client,'wget','-T','1','-qO-','http://172.29.254.3:5030/api/v0/application'],capture_output=True)
            if ready.returncode==0: break
            time.sleep(1)
        else: raise AssertionError('Private test HTTP peer did not become ready')
        fetch(client,'172.29.254.3',True)
        fetch(client,'[fd7a:7a::3]',True)
        run('docker','exec',client,'bash','/ha-vpn-firewall.sh','198.51.100.10','1194','udp')
        fetch(client,'172.29.254.3',False)
        fetch(client,'[fd7a:7a::3]',False)
        run('docker','exec',client,'bash','-c','ip link set eth0 down && ip link set eth0 name tun0 && ip link set tun0 up && ip -6 address replace fd7a:7a::4/64 dev tun0 nodad')
        fetch(client,'172.29.254.3',True)
        fetch(client,'[fd7a:7a::3]',True)
        run('docker','exec',client,'bash','-c','ip link set tun0 down && ip link set tun0 name eth0 && ip link set eth0 up && ip -6 address replace fd7a:7a::4/64 dev eth0 nodad')
        fetch(client,'172.29.254.3',False)
        fetch(client,'[fd7a:7a::3]',False)
        print('PASS: actual IPv4/IPv6 firewall blocks traffic before and after tunnel loss, permits it only on tun0',flush=True)
        # Bind the browser to an off-subnet LAN address. Its bridge address
        # acts as the return gateway, as the HA host does in production.
        run('docker','run','-d','--name',browser,'--network',network,'--ip','172.29.254.5',
            '--cap-add','NET_ADMIN','--entrypoint','bash',image,'-c',
            'ip route del default 2>/dev/null || true; ip -6 route del default 2>/dev/null || true; ip address add 192.168.250.3/24 dev eth0; sleep 600')
        run('docker','exec',peer,'bash','/ha-vpn-firewall.sh','198.51.100.10','1194','udp')
        run('docker','exec',peer,'bash','-c','ip link add tun0 type dummy && ip address add 10.123.0.2/24 dev tun0 && ip link set tun0 up && ip route add 0.0.0.0/1 dev tun0 && ip route add 128.0.0.0/1 dev tun0')
        fetch(browser,'172.29.254.3',False,source='192.168.250.3')
        run('docker','exec',peer,'bash','-c',"printf '%s' '{\"vpn_lan_subnets\":[\"192.168.250.0/24\"]}' > /tmp/lan-options.json")
        run('docker','exec',peer,'bash','/ha-vpn-lan-routes.sh','/tmp/lan-options.json','172.29.254.5','eth0')
        fetch(browser,'172.29.254.3',True,source='192.168.250.3')
        print('PASS: browser on routed LAN can reach the web UI with VPN default routes and kill switch active',flush=True)
        with tempfile.TemporaryDirectory(prefix='slskd-missing-vpn-') as scratch:
            base=Path(scratch)
            for folder in ['data','config','share','media/dedicated-share']:
                (base/folder).mkdir(parents=True)
            options={'puid':1000,'pgid':1000,'soulseek_username':'synthetic','soulseek_password':'synthetic',
                     'web_username':'admin','web_password':'','downloads_path':'/share/downloads',
                     'incomplete_path':'/share/incomplete','shared_dirs':['/media/dedicated-share'],
                     'vpn_enabled':True,'vpn_username':'','vpn_password':''}
            (base/'data/options.json').write_text(json.dumps(options))
            args=['docker','run','--name',missing,'--network','none']
            for folder in ['data','config','share','media']:
                args+=['--mount',f"type=bind,source={base/folder},target=/{folder}"+(',readonly' if folder=='media' else '')]
            result=subprocess.run([*args,image],capture_output=True,text=True)
            assert result.returncode!=0
            assert 'slskd remains stopped' in result.stderr
            print('PASS: VPN-enabled app refuses to start slskd with missing profile, even if Soulseek credentials are configured',flush=True)
    finally:
        for container in [client,peer,missing,browser]:
            subprocess.run(['docker','rm','-f','-v',container],capture_output=True)
        subprocess.run(['docker','network','rm',network],capture_output=True)


if __name__=='__main__':
    main()
