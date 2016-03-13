#! /usr/bin/env python2.7

import json
import os
import os.path
import time

import last_week

lw = last_week.LastWeek()
user_ids = lw.users

cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")

files = os.listdir(cache_dir)

users = {}

for fname in files:
    fqfn = os.path.join(cache_dir, fname)
    fobj = open(fqfn, "r")
    payload = fobj.read()
    fobj.close()
    messages = json.loads(payload)
    for message in messages:
        if 'user' not in message:
            continue
        user_id = message['user']
        user_name = user_ids[user_id]
        ts = int(message['ts'].split('.', 2)[0])
        pretty_date = time.asctime(time.localtime(ts))
        payload = {'name': user_name, 'ts': ts, 'datetime': pretty_date}
        if user_id not in users:
            users[user_id] = payload
        else:
            if ts < users[user_id]['ts']:
                users[user_id] = payload

    # print "Processed {}".format(fqfn)

f = open("user_first_post.json", "w")
f.write(json.dumps(users, indent=4))
f.close()
