#! /usr/bin/env python2.7

import datetime
import json
import math
import re
import sys
import time

f = open("dailychallenge_messages.json", "r")
payload = f.read()
f.close()
j = json.loads(payload)

special = {
    "dc162: what something you've discovered about work/life balance that works for you?": 163}

ignore = [
    "Daily Challenge #666: Is this a test?",
    "How do you evaluate performance of software engineers in your team",
    "How do you capture a cranky tortoise?",
    "For DC#1000, we should have a party."
]

users = {}

def detect(text):
    """
    returns DC number if found, or None if not
    """
    text = text.lower()
    # text = re.sub("\s", "", text)
    # Some user IDs are of the form <@U051DC75B> -- remove them
    debug = False
    for line in text.split("\n"):
        for elem in special:
            if line.find(elem) != -1:
                return special[elem]
        line = re.sub("<[^>]+>", "", line)
        replace = re.sub(".*?daily\s*challenge\s*#?(\d+).*", r"\1", line)
        if replace != line:
            if debug:
                print "\treplace is {}".format(replace)
            return replace
        replace = re.sub(".*?dc\s*#?(\d+).*", r"\1", line, re.M)
        if replace != line:
            if debug:
                print "\treplace is {}".format(replace)
            return replace
    if debug:
        print "\tno replacement found"
    return None


def asciify(text):
    text = ''.join([x for x in list(text) if ord(x) in range(128)])
    return text


def get_author(message):
    text = message['text']
    debug = False
    if text.find("set the channel topic") != -1:
        text = re.sub(">.*", "", text)
        if debug:
            pass  # print "After first transformation, text is {}".format(text)
        text = re.sub("^.*\|", "", text)
        if debug:
            print "1 message {} had author {}".format(message, text)
        return text
    if re.match("^<.*?> says:? Daily Challenge #", text):
        text = re.sub("^<[^\|]+\|([^>]+)>.*", r"\1", text)
        if debug:
            print "2 message {} had author {}".format(message, text)
        return text
    author = message['user']
    if author in users:
        name = users[author]
        if debug:
            print "3 message {} had author {}".format(message, text)
        return name
    else:
        print "Could not find user {} for {}".format(author, message['text'])
        if debug:
            print "4 message {} had author {}".format(message, text)
        return author

detected = {}
authors = {}
authors_by_message = {}
dcnum = None
highest_dcnum = 0
previous_dcnum = None
for message in j:
    message['hour'] = time.localtime(float(message['ts']))[3]
    text = message['text']
    message['length'] = len(text.split())
    for t in text.split():
        t = t.strip()
        if re.match("^<[^>]+>$", t):
            t = t.replace("<@", "").replace(">", "")
            userid = t.split("|")
            if len(userid) == 1:
                # print userid
                pass
            else:
                uid = userid[0]
                name = userid[1]
            users[uid] = name
    if message.get("subtype", "") in ['channel_join', 'channel_leave']:
        continue
    text = ''.join([x for x in list(text) if ord(x) in range(128)])
    to_ignore = False
    for i in ignore:
        if text.find(i) != -1:
            to_ignore = True
            continue
    if to_ignore:
        continue
    dcnum = detect(text)
    if not dcnum:
        continue
    dcnum = str(dcnum)
    if int(dcnum) > (highest_dcnum + 3):
        print "Ignoring {} -- too high {} compared to {}".format(message, dcnum, highest_dcnum)
        dcnum = previous_dcnum
    else:
        previous_dcnum = dcnum
    if int(dcnum) > highest_dcnum:
        highest_dcnum = int(dcnum)
    message['number'] = dcnum
    if dcnum not in detected:
        message['founder'] = dcnum
        author = get_author(message)
        if author not in authors:
            authors[author] = []
        authors[author].append(dcnum)
        authors_by_message[dcnum] = author
        detected[dcnum] = message
        # print "Found DC '{}': {}".format(dcnum, message)

# print ""
# for num in sorted(detected.keys(), key = lambda x: int(x)):
#    print "{}: {}".format(num, asciify(detected[num]['text']))
#    print ""

ints = [int(x) for x in detected.keys()]
m = max(ints)
# print "Maximum question number is {}".format(m)
possibles = range(m + 1)
missing = [x for x in possibles if x not in ints]
# print "Missing DCs: {}".format(missing)

total = len(j)
for hour in range(24):
    matching = [x for x in j if x['hour'] == hour]
    count = len(matching)
    print "In hour {} we had {} messages (or %{})".format(hour, count, (count * 100) / total)

counts = {}
lengths = {}
today = datetime.date.fromtimestamp(time.time())
current = None
for message in j:
    t = asciify(message['text'])
    if message.get("subtype") in ['channel_join', 'channel_leave']:
        continue
    if message.get("founder"):
        current = message['founder']
        last_dc_ts = float(message['ts'])
        today = datetime.date.fromtimestamp(float(message['ts']))
        counts[current] = 0
        lengths[current] = 0
        # print "Started counting for DC {}".format(current)
    elif current:
        this_timestamp = float(message['ts'])
        diff = this_timestamp - last_dc_ts
        if diff <= 86400 or message.get("number") == current:
            counts[current] += 1
            lengths[current] += message['length']
            # print "{} {} includes {}".format(counts[current], current, t)
        else:
            pass
            # print "{} does not include {}".format(current, t)

total = 0
for c in counts:
    total += counts[c]
average = (total * 1.0) / len(counts.keys())

variance = 0
for c in counts:
    diff = counts[c] - average
    variance += (diff * diff)

variance = variance / len(counts.keys())
stdev = math.sqrt(variance)

dcs = counts.keys()
dcs.sort(key=lambda x: counts[x])
dcs.reverse()
print "Average {}, standard deviation {}".format(average, stdev)
for idx, dc in enumerate(dcs):
    if counts[dc] == 0:
        counts[dc] = 1
    avg = lengths[dc] / counts[dc]
    diff = counts[dc] - average
    st = diff / stdev
    m = "{}: Question {} (author: {}) had {} msg, {} words, {} words/message {:.1f} stdev"
    m = m.format(idx + 1, dc, authors_by_message[dc], counts[dc], lengths[dc], avg, st)
    print m

#print "counts:"
#print json.dumps(counts, indent=4)

averages = {}
for author in sorted(authors.keys()):
    dcs = authors[author]
    count = 0
    length = 0
    for dc in dcs:
        count += counts[dc]
        length += lengths[dc]
    dccount = len(dcs)
    average_msg = count / dccount
    average_len = length / dccount
    m = "{} hosted {} DCs: {} msg, avg {} msg/DC, {} words, avg {} words/DC"
    m = m.format(author, dccount, count, average_msg, length, average_len)
    averages[average_msg] = m

acount = averages.keys()
acount.sort()
acount.reverse()
for a in acount:
    print averages[a]

print ""


def make_url(message):
    url = "https://rands-leadership.slack.com/archives/dailychallenge/p"
    url += message['ts'].replace(".", "")
    return url

for message in j:
    if message.get("founder"):
        num = message['founder']
        author = authors_by_message[num]
        print "{} {} {}".format(num, author, make_url(message))
