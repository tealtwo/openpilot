#!/usr/bin/env python3
"""Direct socket test for navStateSP messages."""
import cereal.messaging as messaging
import time

sock = messaging.sub_sock('navStateSP', timeout=1000)
print('Listening for navStateSP on socket...')

for i in range(20):
    msg = messaging.recv_one_or_none(sock)
    if msg:
        print(f'Got message #{i}: logMonoTime={msg.logMonoTime}, active={msg.navStateSP.active}')
    else:
        print(f'Iteration {i}: No message')
    time.sleep(0.5)

print('Test complete')
