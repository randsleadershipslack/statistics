#! /usr/bin/env python2.7

import json
import os
import re
import time

import requests

api_token = os.getenv("API_TOKEN")

slack = "rands-leadership"
surl = "https://{}.slack.com/api/".format(slack)
url = surl + "channels.list?exclude_archived=true&token={}".format(api_token)
payload = requests.get(url).json()['channels']
channels = {x['name']: x['id'] for x in payload}
cid = channels['dailychallenge']

fname = "dailychallenge_messages.json"

def get_latest_message():
    try:
        f = open(fname, "r")
        payload = f.read()
        j = json.loads(payload)
        f.close()
        ts = [float(x['ts']) for x in j]
        m = max(ts)
        return (m, j)
    except Exception, e:
        print "Warning: Failed to get latest message: {} {}".format(Exception, e)
        return (0, [])

def get_messages(oldest, token, cid):
    messages = []
    done = False
    latest = None
    while not done:
        murl = surl + "channels.history?oldest={}&token={}&channel={}".format(oldest, token, cid)
        if latest:
            murl += "&latest={}".format(latest)
        else:
            murl += "&latest={}".format(time.time())
        print "murl: {}".format(murl)
        payload = requests.get(murl).json()
        if payload['has_more'] == False:
            done = True
        messages += payload['messages']
        ts = [float(x['ts']) for x in messages]
        earliest = min(ts)
        latest = max(ts)
        latest = earliest
    messages.sort(key = lambda x: float(x['ts']))
    return messages

(latest, previous_messages) = get_latest_message()
print "Latest message prior to this was from {}".format(time.asctime(time.localtime(latest)))
messages = get_messages(str(latest), api_token, cid)
f = open("dailychallenge_messages.json", "w")
previous_messages += messages
f.write(json.dumps(previous_messages, indent=4))
f.close()
