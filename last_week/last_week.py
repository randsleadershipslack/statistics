#! /usr/bin/env python2.7

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
import zipfile

import requests


def asciify(text):
    text = ''.join([x for x in list(text) if ord(x) in range(128)])
    return text


def index(m):
    return "{}{}{}".format(asciify(m['text']), m['user'], m['channel'])


def onlyemoji(m):
    t = asciify(m['text'])
    t = re.sub(":[^:]+:", "", t)
    t = re.sub("\s+", "", t)
    return t == ""

class PopReactions(object):
    messages = []
    min_reactions = -1
    max_reactions = 0
    prune_every = 100

    def __init__(self, max):
        self.max = max
        self.counter = 0
        self.last_prune = 0

    def push(self, message, count):
        self.messages.append([message, count])
        self.counter += 1
        if count > self.max_reactions:
            print "Found new max count: {}".format(count)
            self.max_reactions = count
        self.prune()

    def prune(self, force=False):
        if (not force) and len(self.messages) < self.max:
            return
        if (not force) and self.last_prune + self.prune_every < self.counter:
            return
        self.last_prune = self.counter
        self.messages.sort(key=lambda x: x[1])
        while len(self.messages) > self.max:
            self.messages.pop(0)


class LastWeek(object):
    slack = "rands-leadership"
    surl = "https://{}.slack.com/api/".format(slack)
    upload_channel = "zmeta-statistics"
    ignore_channels = ['destalinator-log', 'zmeta-statistics', 'rands-tech']
    ignore_patterns = ["^zmeta-"]
    ignore_users = ['USLACKBOT']
    dayidx = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    def median(self, l):
        halfway = len(l) / 2
        if len(l) % 2 == 0:
            first = l[halfway - 1]
            second = l[halfway]
            return (first + second) / 2.0
        return l[halfway]

    def hour(self, ts):
        try:
            ts = float(ts)
            return time.localtime(ts).tm_hour
        except:
            return -1

    def day(self, ts):
        try:
            ts = float(ts)
            return self.dayidx[time.localtime(ts).tm_wday]
        except:
            print "Failed to get day for {}".format(ts)
            sys.exit(0)

    def retry(self, url, attempts=3):

        while attempts:
            try:
                req = requests.get(url)
                j = req.json()
                return j
            except Exception, e:
                attempts -= 1
                print "Failed to get {}: {}/{} ({} more attempts)".format(url, Exception, e, attempts)
        raise RuntimeError("failed to get {} many times".format(url))

    def __init__(self, weeks_ago=0, debug=False, upload=True, cache=True):

        self.debug = debug
        self.weeks_ago = int(weeks_ago)
        # self.last_week()
        self.use_cache = cache
        self.api_token = os.getenv("API_TOKEN")
        self.get_channels()
        self.get_users()
        self.upload_flag = upload
        if self.weeks_ago == -1:
            self.use_cache = False
            self.upload_flag = False
        print "use_cache: {}".format(self.use_cache)
        self.pr = PopReactions(15)

    def get_channels(self):
        url = self.surl + "channels.list?exclude_archived=true&token={}".format(self.api_token)
        payload = self.retry(url)['channels']
        self.channel_payload = payload
        self.channels_by_id = {x['id']: x['name'] for x in payload}
        self.channels_by_name = {x['name']: x for x in payload}
        self.channels = {x['name']: x['id'] for x in payload}

    def is_new(self, channel_name):
        match = [x for x in self.channel_payload if x['name'] == channel_name]
        if not match:
            return False
        match = match[0]
        created = match['created']
        if created >= self.start:
            return True
        return False

    def get_users(self):
        url = self.surl + "users.list?token=" + self.api_token
        payload = self.retry(url)['members']
        self.user_payload = payload
        self.users = {x['id']: x['name'] for x in payload}

    def get_fname(self, oldest, cid, latest):
        fname = "cache/messages_{}_{}_{}".format(oldest, cid, latest)
        return fname

    def get_messages(self, oldest, cid, latest=None):
        messages = []
        done = False
        fname = self.get_fname(oldest, cid, latest)
        if self.use_cache:
            try:
                f = open(fname, "r")
                j = json.loads(f.read())
                f.close()
                return j
            except:
                pass
        while not done:
            murl = self.surl + "channels.history?oldest={}&token={}&channel={}".format(oldest, self.api_token, cid)
            if latest:
                murl += "&latest={}".format(latest)
            else:
                murl += "&latest={}".format(time.time())
            # print "murl: {}".format(murl)
            payload = self.retry(murl)
            messages += payload['messages']
            if payload['has_more'] is False:
                done = True
                continue
            ts = [float(x['ts']) for x in messages]
            earliest = min(ts)
            latest = earliest
        messages = [x for x in messages if x.get("user") not in self.ignore_users]
        messages.sort(key=lambda x: float(x['ts']))
        if self.use_cache:
            f = open(fname, "wb")
            f.write(json.dumps(messages, indent=4))
            f.close()
        return messages

    def last_week(self):
        """
        returns (first_timestamp_in_last_week, last_timestamp_in_last_week)
        """
        lweek = time.time() - 86400 * 7
        lweek_lt = time.localtime(lweek)
        wday = lweek_lt.tm_wday
        print "wday: {}".format(wday)
        d = 1
        if wday == 6:
            wday = 0
            d = 0
        # print "multiplier: {}".format(multiplier)
        lw = lweek - (86400 * wday)
        lw -= (d * 86400)
        start_of_last_week = time.localtime(lw)
        new_dt = datetime.datetime(start_of_last_week.tm_year, start_of_last_week.tm_mon, start_of_last_week.tm_mday, 0, 0, 0)
        diff = new_dt - datetime.datetime.fromtimestamp(0)
        start = diff.total_seconds()
        end = start + 7 * 86400 - 1
        if self.debug:
            start = end - 86400
        if self.weeks_ago:
            start -= (86400 * 7 * self.weeks_ago)
            end -= (86400 * 7 * self.weeks_ago)
        start_dt = datetime.datetime.fromtimestamp(start)
        end_dt = datetime.datetime.fromtimestamp(end)
        self.start_date = "{}-{:02d}-{:02d} {:02d}:{:02d}".format(start_dt.year, start_dt.month, start_dt.day, start_dt.hour, start_dt.minute)
        self.end_date = "{}-{:02d}-{:02d} {:02d}:{:02d}".format(end_dt.year, end_dt.month, end_dt.day, end_dt.hour, end_dt.minute)
        self.start_date = "{}-{:02d}-{:02d}".format(start_dt.year, start_dt.month, start_dt.day)
        self.end_date = "{}-{:02d}-{:02d}".format(end_dt.year, end_dt.month, end_dt.day)
        print "start: {}".format(self.start_date)
        print "end: {}".format(self.end_date)
        # sys.exit(0)
        self.start = start
        self.end = end
        return (start, end)

    def get_all_messages(self):
        start, end = self.last_week()

        messages = []
        channels = self.channels
        if self.debug:
            channels = ['dailychallenge', 'general', 'perf-management']
        for channel in sorted(channels):
            if channel in self.ignore_channels:
                continue
            ignore = False
            for pattern in self.ignore_patterns:
                if re.match(pattern, channel):
                    ignore = True
            if ignore:
                continue
            # print "Getting messages for {}".format(channel)
            cid = self.channels[channel]
            cur_messages = self.get_messages(start, cid, end)
            for message in cur_messages:
                message['channel'] = channel
            if len(cur_messages):
                print "Got {} messages for {}".format(len(cur_messages), channel)
            messages += cur_messages

        print "Got a total of {} messages for last week".format(len(messages))

        # Filter out messages with subtype (they're operational, like leaving/joining/setting topic)
        messages = [x for x in messages if x.get("subtype") is None]
        print "After filtering, got a total of {} messages for last week".format(len(messages))
        self.messages = messages

    def create_aggregates(self):

        idx = {}
        words = {}
        activity_by_channel = {}
        activity_by_user = {}
        reactions = {}
        reactors_by_reaction = {}
        reactors_by_count = {}
        self.recount = {}
        self.days = {}
        self.hours = {}
        pureemoji = 0

        for hour in range(0,24):
            self.hours[hour] = 0

        for message in self.messages:
            i = index(message)
            if onlyemoji(message):
                pureemoji += 1
            if i in idx:
                continue
            idx[i] = 1
            day = self.day(message['ts'])
            if day not in self.days:
                self.days[day] = 0
            self.days[day] += 1
            self.hours[self.hour(message['ts'])] += 1
            uid = message['user']
            text = asciify(message['text'])
            wc = len(text.split())
            user = self.users[uid]
            if user not in words:
                words[user] = 0
            words[user] += wc
            channel = message['channel']
            if channel not in activity_by_channel:
                activity_by_channel[channel] = {}
            if user not in activity_by_user:
                activity_by_user[user] = {}
            activity_by_channel[channel][user] = activity_by_channel[channel].get(user, 0) + 1
            activity_by_user[user][channel] = activity_by_user[user].get(channel, 0) + 1
            mreactions = message.get("reactions", [])
            tot_reactions = 0
            for reaction in mreactions:
                name = reaction['name']
                if name not in self.recount:
                    self.recount[name] = 0
                count = reaction['count']
                tot_reactions += count
                if uid in reaction['users']:
                    count -= 1
                self.recount[name] += count
                if user not in reactions:
                    reactions[user] = {}
                if name not in reactions[user]:
                    reactions[user][name] = 0
                reactions[user][name] += count
                users = [self.users[uid] for uid in reaction['users']]
                users = [x for x in users if x != user]
                for user in users:
                    if user not in reactors_by_reaction:
                        reactors_by_reaction[user] = {}
                    if user not in reactors_by_count:
                        reactors_by_count[user] = 0
                    if name not in reactors_by_reaction[user]:
                        reactors_by_reaction[user][name] = 0
                    reactors_by_reaction[user][name] += 1
                    reactors_by_count[user] += 1
            self.pr.push(message, tot_reactions)
        print "pureemoji is {}".format(pureemoji)

        self.pr.prune(force=True)
        self.popular_messages = self.pr.messages
        self.popular_messages.reverse()

        user_messages = []
        for user in activity_by_user:
            c = 0
            for channel in activity_by_user[user]:
                c += activity_by_user[user][channel]
            user_messages.append(c)
        self.median_messages = self.median(user_messages)

        for user in activity_by_user:
            total = 0
            for channel in activity_by_user[user]:
                total += activity_by_user[user][channel]
            activity_by_user[user]['$total'] = total

        for channel in activity_by_channel:
            total = 0
            user_count = 0
            for user in activity_by_channel[channel]:
                user_count += 1
                total += activity_by_channel[channel][user]
            activity_by_channel[channel]['$total'] = total
            activity_by_channel[channel]['$average'] = (total * 1.0) / user_count

        self.sorted_channels = sorted(activity_by_channel.keys(), key=lambda x: activity_by_channel[x]['$total'], reverse=True)
        users = sorted(activity_by_user.keys())
        self.sorted_users = sorted(users, key=lambda x: activity_by_user[x]['$total'], reverse=True)
        self.activity_by_channel = activity_by_channel
        self.activity_by_user = activity_by_user
        self.reactions = reactions
        self.reactors_by_count = reactors_by_count
        self.reactors_by_reaction = reactors_by_reaction
        self.words = words

    def td(self, text):
        return "<td>{}</td>".format(text)

    def create_report(self):

        blob = """
        <html>
            <head>
                <title>
                    Channel/User Activity {} to {}
                </title>
            </head>
            <body>
                <h3><center>
                    Channel/User Activity {} to {}
                </h3></center>
            <b>Note:</b>Yellow-background channels are new this week<p/>
        """
        active = len(self.sorted_users)
        total = len(self.users.keys())
        per = (active * 100.0) / total
        # Header row: users
        blob = blob.format(self.start_date, self.end_date, self.start_date, self.end_date)
        blob += "<b>{}/{}</b> (or {:.1f}%) users were active<p/>".format(active, total, per)
        blob += "<b>Median message count</b> was {:.2f} messages<p/>".format(self.median_messages)
        blob += "<p/>For each user's total message cell, the first number is their total "
        blob += "number of messages sent, the second is the percent of total messages their "
        blob += "messages represent, and the third is the running percent of messages "
        blob += "from all the people ahead of them plus theirs."
        blob += "<br/>"
        blob += "for example, if the 2nd person had 870, 3.5%, 7.8%, that means that "
        blob += "They sent 870 messages; 870 messages represented 3.5% of total messages; "
        blob += "and total messages from them and the #1 poster represented 7.8% of total volume"
        blob += "<p/><b>rphm</b> is reactions per 100 messages -- an indication of how many reactions your messages got on average"
        blob += "<p/>"
        blob += "<b>wpm</b> is average words per message<p/>"
        blob += "numbers in paranthesis after channel names are number of users in channel<p/>"
        blob += "<table border='1'>"
        blob += "<tr>"
        blob += "<td></td><td><b>TOTAL</b></td>"

        total = 0

        idx = 0
        last_user = None
        for i, su in enumerate(self.sorted_users):
            last = self.activity_by_user.get(last_user, {}).get("$total", 0)
            cur = self.activity_by_user.get(su, {}).get("$total", 0)
            if cur != last:
                idx = i + 1
            blob += "<td>{} <b>{}</b></td>\n".format(idx, su)
            last_user = su
        blob += "</tr>\n"
        rows = []
        for idx, channel in enumerate(self.sorted_channels):
            activity = self.activity_by_channel[channel]
            row = "<tr>"
            if self.is_new(channel):
                row += "<td bgcolor='#ffff00'>"
            else:
                row += "<td>"
            members = self.channels_by_name[channel]['num_members']
            row += "{} <b>{}</b> ({})</td>".format(idx + 1, channel, members)
            participants = int(activity['$total'] / activity['$average'])
            row += self.td("{}m {}p {:.1f}m/p".format(activity['$total'], participants, activity['$average']))
            total += activity['$total']
            for su in self.sorted_users:
                value = self.activity_by_user[su].get(channel, "")
                if value:
                    row += "<td bgcolor='#00FF00'>"
                else:
                    row += "<td>"
                row += str(value) + "</td>"
            row += "</tr>\n"
            rows.append(row)
        blob += "<tr><td><b>TOTAL</b></td><td><b>"
        blob += "{}m {}p {:.1f}m/p</b></td>".format(total, len(self.sorted_users), total * 1.0 / len(self.sorted_users))
        running = 0
        self.reaction_percentage = {}
        for su in self.sorted_users:
            blob += "<td>"
            cur = self.activity_by_user[su]['$total']

            c = 0
            for v in self.reactions.get(su, {}).values():
                c += v
            reaction_percentage = c * 100.0 / cur

            running += cur
            blob += "{}<br/>".format(cur)
            per = cur * 100.0 / total
            blob += "{:.1f}%<br/>".format(per)
            per = (running * 100.0 / total)
            words = self.words[su]
            wpm = words / cur
            blob += "{:.1f}%<br/>".format(per)
            blob += "{:.1f} rphm<br/>".format(reaction_percentage)
            blob += "{:.1f} wpm".format(wpm)
            self.reaction_percentage[su] = reaction_percentage
            blob += "</td>"
        blob += "</tr>\n"
        for row in rows:
            blob += row
        blob += "</table>\n"
        blob += "<p/>"

        blob += "<table border='1'>"
        blob += "<tr>"

        blob += "<td>"
        blob += "Top Authors by Reactions Per Hundred Messages (rphm)::<p/>"
        blob += "<table border='1'><tr><td><b>Author</b></td><td><b>rphm</b></td></tr>\n"
        authors = self.reaction_percentage.keys()
        authors.sort(key=lambda x: self.reaction_percentage[x])
        authors.reverse()
        authors = authors[0:10]
        for author in authors:
            blob += "<tr>"
            blob += "<td>{}</td>".format(author)
            blob += "<td>{:.1f}</td>".format(self.reaction_percentage[author])
            blob += "</tr>"
        blob += "</table><p/>"
        blob += "</td>"

        blob += "<td>"
        blob += "Messages by day:<p/>"
        blob += "<table border='1'><tr><td><b>Day</b></td><td><b>Messages</b></td></tr>\n"
        for day in self.dayidx:
            blob += "<tr>"
            blob += "<td>{}</td>".format(day)
            blob += "<td>{}</td>".format(self.days.get(day, 0))
            blob += "</tr>"
        blob += "</table><p/>"
        blob += "</td>"

        blob += "<td>"
        blob += "Messages by hour:<p/>"
        blob += "<table border='1'><tr><td><b>Hour</b></td><td><b>Messages</b></td></tr>\n"
        for hour in sorted(self.hours.keys()):
            blob += "<tr>"
            blob += "<td>{}</td>".format(hour)
            blob += "<td>{}</td>".format(self.hours[hour])
            blob += "</tr>"
        blob += "</table><p/>"
        blob += "</td>"

        blob += "<td>"
        blob += "Most reacted-to messages<p/>"
        for message, count in self.popular_messages:
            t = asciify(message['text'])
            u = self.users[message['user']]
            c = message['channel']
            blob += "{} <b>reactions</b> {} by <b>{}</b> in <b>{}</b><br/>".format(count, t, u, c)
        blob += "</td>"

        blob += "</tr>"
        blob += "</table>"

        blob += "</body>\n"
        blob += "</html>\n"

        return blob

    def upload(self, fname):
        cid = self.channels[self.upload_channel]
        url = self.surl + "files.upload?token={}&filename={}".format(self.api_token, fname)
        url += "&channels={}".format(cid)
        files = {'file': open(fname, "rb")}
        r = requests.post(url, files=files)
        print r.status_code

    def run(self):
        self.get_all_messages()
        self.create_aggregates()

        blob = self.create_report()

        fname = "output/activity_{}_to_{}".format(self.start_date, self.end_date)
        html_fname = fname + ".html"
        zip_fname = fname + ".zip"
        json_fname = fname + ".json"

        f = open(html_fname, "w")
        f.write(blob)
        f.close()

        payload = {
            'start': self.start_date,
            'end': self.end_date,
            'statistics': self.activity_by_channel
        }
        f = open(json_fname, "wb")
        f.write(json.dumps(payload, indent=4))
        f.close()


        zf = zipfile.ZipFile(zip_fname, mode="w")
        zf.write(html_fname)
        zf.write(json_fname)
        zf.close()

        if self.upload_flag:
            self.upload(zip_fname)

        messages = {}
        counts = {}
        emojis = {}
        for user in sorted(self.reactions.keys()):
            user_reactions = self.reactions[user]
            m = ""
            total = 0
            user_emojis = user_reactions.keys()
            user_emojis.sort(key=lambda x: user_reactions[x])
            user_emojis.reverse()
            for emoji in user_emojis:
                count = user_reactions[emoji]
                m += "{} :{}: ".format(count, emoji)
                total += count
                emojis[emoji] = emojis.get(emoji, 0) + count
            # s = "{}: {} emojis: {}".format(user, total, m)
            s = "{}: {} emojis".format(user, total)
            counts[user] = total
            messages[user] = s

        users = sorted(counts.keys(), key=lambda x: counts[x])
        users.reverse()
        for idx, user in enumerate(users[0:11]):
            print idx, messages[user]

        e = sorted(emojis.keys(), key=lambda x: emojis[x])
        e.reverse()
        for idx, emoji in enumerate(e):
            # print "{}. {} :{}:".format(idx + 1, emojis[emoji], emoji)
            pass

        print ""
        print "Reactors:"
        users = self.reactors_by_count.keys()
        users.sort(key=lambda x: self.reactors_by_count[x])
        users.reverse()
        for idx, user in enumerate(users[0:11]):
            m = "{} {}: {} reactions ".format(idx, user, self.reactors_by_count[user])
            reactions = self.reactors_by_reaction[user].keys()
            reactions.sort(key=lambda x: self.reactors_by_reaction[user][x])
            reactions.reverse()
            for reaction in reactions:
                # m += "{} :{}: ".format(self.reactors_by_reaction[user][reaction], reaction)
                pass
            print m

        print ""
        print "Most popular reactions:"
        reactions = self.recount.keys()
        reactions.sort(key=lambda x: self.recount[x])
        reactions.reverse()
        for idx, reaction in enumerate(reactions[0:11]):
            print "{} {} :{}:".format(idx, self.recount[reaction], reaction)

        subprocess.call(["/usr/bin/open", html_fname])


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--week", type=int, default=0)
    parser.add_argument("--noupload", action="store_true")
    parser.add_argument("--nocache", action="store_true")
    args = parser.parse_args()
    upload = not args.noupload
    print "upload: {}".format(upload)
    cache = not args.nocache
    lw = LastWeek(weeks_ago=args.week, debug=args.debug, upload=upload, cache=cache)
    lw.run()
