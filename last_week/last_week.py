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

male = [x.strip() for x in open("male", "r").readlines()]
female = [x.strip() for x in open("female", "r").readlines()]
undetermined = [x.strip() for x in open("undetermined", "r").readlines()]

genders = {'female': female, 'male': male, 'undetermined': undetermined}


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
            # print "Found new max count: {}".format(count)
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
    ignore_channels = ['destalinator-log', 'zmeta-statistics', 'rands-tech', 'rands-slack-rules', 'slack-support']
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

    def __init__(self, weeks_ago=0, debug=False, upload=False, produce_html=True, cache=True, report=True):

        self.debug = debug
        self.weeks_ago = int(weeks_ago)
        # self.last_week()
        self.use_cache = cache
        self.api_token = os.getenv("API_TOKEN")
        self.get_channels()
        self.get_users()
        self.upload_flag = upload
        self.produce_html = produce_html
        self.report_flag = report
        if self.weeks_ago == -1:
            self.use_cache = False
            self.upload_flag = False
        if not self.report_flag:
            self.upload_flag = False
        # print "use_cache: {}".format(self.use_cache)
        if self.use_cache and not os.path.isdir("cache"):
            os.makedirs("cache")
        if not os.path.isdir("output"):
            os.makedirs("output")

        self.pr = PopReactions(15)
        if self.produce_html:
            import jinja2
            jinja_environment = jinja2.Environment(loader=jinja2.FileSystemLoader("."))
            self.template = jinja_environment.get_template("report.html")

    def minify(self, blob):
        import htmlmin
        return htmlmin.minify(blob,
                              remove_comments=True,
                              remove_empty_space=True,
                              remove_all_empty_space=True,
                              reduce_boolean_attributes=True
                              )

    def replace_id(self, cid):
        """
        Assuming either a #channelid or @personid, replace them with #channelname or @username
        """
        stripped = cid[1:]
        first = cid[0]
        if first == "#":
            if stripped.find("|") != -1:
                cid, cname = stripped.split("|")
            else:
                cname = self.channels_by_id[stripped]
            return "#" + cname
        elif first == "@":
            if stripped.find("|") != -1:
                uid, uname = stripped.split("|")
            else:
                uname = self.users[stripped]
            return "@" + uname
        return cid

    def detokenize(self, message):
        new = []
        tokens = re.split("(<.*?>)", message)
        for token in tokens:
            if len(token) > 3 and token[0] == "<" and token[-1] == ">":
                token = self.replace_id(token[1:-1])
            new.append(token)
        message = " ".join(new)
        return message

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
        self.users_real_name = {x['name']: x.get("real_name", "") for x in payload}

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
        # print "wday: {}".format(wday)
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
        # print "start: {}".format(self.start_date)
        # print "end: {}".format(self.end_date)
        # sys.exit(0)
        self.start = start
        self.end = end
        return (start, end)

    def get_all_messages(self):
        start, end = self.last_week()
        if self.weeks_ago > 0:
            print "Getting messages from {} to {}".format(self.start_date, self.end_date)

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
            s = time.time()
            cur_messages = self.get_messages(start, cid, end)
            e = time.time()
            for message in cur_messages:
                message['channel'] = channel
            if len(cur_messages) and e - s > .5:
                print "Got {} messages for {}".format(len(cur_messages), channel)
            messages += cur_messages

        # print "Got a total of {} messages for last week".format(len(messages))

        # Filter out messages with subtype (they're operational, like leaving/joining/setting topic)
        messages = [x for x in messages if x.get("subtype") is None]
        # print "After filtering, got a total of {} messages for last week".format(len(messages))
        self.messages = messages

    def get_gender(self, username):
        for label in genders:
            if username in genders[label]:
                return label
        return "unknown"

    def create_aggregates(self):

        if not self.messages:
            return

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
        self.gendercount = {}
        self.unknown = []

        for hour in range(0, 24):
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
            gender = self.get_gender(user)
            if gender not in self.gendercount:
                self.gendercount[gender] = 0
            self.gendercount[gender] += 1
            if gender == "unknown" and user not in self.unknown:
                self.unknown.append(user)
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
                users = [self.users[u] for u in reaction['users']]
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
        # print "pureemoji is {}".format(pureemoji)

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
        if not self.messages:
            return

        active = len(self.sorted_users)
        total = len(self.users.keys())
        per = (active * 100.0) / total
        # Header row: users

        payload = {}
        payload['start_date'] = self.start_date
        payload['end_date'] = self.end_date
        payload['active_users'] = active
        payload['total_users'] = total
        payload['active_percentage'] = "{:.1f}".format(per)
        payload['median_messages'] = self.median_messages
        payload['users'] = []

        total = 0

        idx = 0
        last_user = None
        self.rank = {}
        for i, su in enumerate(self.sorted_users):
            last = self.activity_by_user.get(last_user, {}).get("$total", 0)
            cur = self.activity_by_user.get(su, {}).get("$total", 0)
            if cur != last:
                idx = i + 1
            last_user = su
            payload['users'].append({'rank': idx, 'name': su})
            self.rank[su] = idx

        payload['channels'] = []
        for idx, channel in enumerate(self.sorted_channels):
            activity = self.activity_by_channel[channel]
            members = self.channels_by_name[channel]['num_members']
            participants = int(activity['$total'] / activity['$average'])
            co = {'rank': idx + 1, 'name': channel, 'members': members}
            co['messages'] = activity['$total']
            co['participants'] = participants
            co['messages_per_participant'] = "{:.1f}".format(activity['$average'])
            co['user_activity'] = []
            co['new'] = self.is_new(channel)
            total += activity['$total']
            for su in self.sorted_users:
                value = self.activity_by_user[su].get(channel, "")
                co['user_activity'].append(value)
            payload['channels'].append(co)

        payload['total_messages'] = total
        payload['total_participants'] = len(self.sorted_users)
        payload['messages_per_participant'] = "{:.1f}".format(total * 1.0 / len(self.sorted_users))

        running = 0
        self.reaction_percentage = {}
        ctr = 0
        for user in payload['users']:
            ctr += 1
            su = user['name']
            cur = self.activity_by_user[su]['$total']
            c = 0
            for v in self.reactions.get(su, {}).values():
                c += v
            reaction_percentage = c * 100.0 / cur
            self.reaction_percentage[su] = reaction_percentage

            running += cur
            per = cur * 100.0 / total
            per = (running * 100.0 / total)
            words = self.words[su]
            wpm = words / cur
            user['messages'] = cur
            user['percentage'] = "{:.1f}".format(cur * 100.0 / total)
            cumpercentage = (running * 100.0 / total)
            if ctr == 10:
                payload['topten'] = "{:.1f}%".format(cumpercentage)
            if cumpercentage >= 50.0 and 'fifty' not in payload:
                payload['fifty'] = ctr - 1
            user['cumpercentage'] = "{:.1f}".format(cumpercentage)
            user['rphm'] = "{:.1f}".format(reaction_percentage)
            user['wpm'] = "{:.1f}".format(wpm)

        authors = self.reaction_percentage.keys()
        authors.sort(key=lambda x: self.reaction_percentage[x])
        authors.reverse()
        authors = authors[0:10]
        for author in authors:
            # blob += "<td>{}</td>".format(author)
            # blob += "<td>{:.1f}</td>".format(self.reaction_percentage[author])
            pass

        payload['days'] = []
        for day in ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]:
            payload['days'].append({'name': day, 'count': self.days.get(day, 0)})

        payload['hours'] = []
        for hour in sorted(self.hours.keys()):
            payload['hours'].append({'name': hour, 'count': self.hours[hour]})

        payload['reacted_messages'] = []
        for message, count in self.popular_messages:
            a = message['ts'].replace(".", "")
            t = asciify(message['text'])
            u = self.users[message['user']]
            c = message['channel']
            message = {}
            message['url'] = "https://rands-leadership.slack.com/archives/{}/p{}".format(c, a)
            message['reaction_count'] = count
            message['text'] = self.detokenize(t)
            message['author'] = u
            message['channel'] = c
            payload['reacted_messages'].append(message)

        # blob += "<b>Warning:</b>Gender detection is manual and at risk for misgendering.  Please let @royrapoport know if you notice an error<p/>"
        genders = sorted(self.gendercount.keys(), key=lambda x: self.gendercount[x])
        total = 0
        for gender in genders:
            total += self.gendercount[gender]

        for gender in genders:
            per = self.gendercount[gender] * 100.0 / total
            payload['{}_gender_message_count'.format(gender)] = self.gendercount[gender]
            payload['{}_gender_message_percentage'.format(gender)] = "{:.1f}".format(per)

        payload['unknown_authors'] = [u"{} ({})".format(x, self.users_real_name[x]) for x in sorted(self.unknown)]

        users = [(x, self.get_gender(x)) for x in self.sorted_users]
        total_authors = len(users)
        female_authors = len([x for x in users if x[1] == "female"])
        undetermined_authors = len([x for x in users if x[1] == "undetermined"])
        male_authors = total_authors - (female_authors + undetermined_authors)
        female_percent = "{:.1f}%".format((female_authors * 100.0) / total_authors)
        undetermined_percent = "{:.1f}%".format((undetermined_authors * 100.0) / total_authors)
        male_percent = "{:.1f}%".format((male_authors * 100.0) / total_authors)
        payload['female_authors_percent'] = female_percent
        payload['undetermined_authors_percent'] = undetermined_percent
        payload['male_authors_percent'] = male_percent

        for label in ["female", "undetermined"]:
            authors = [x for x in users if x[1] == label]
            if authors:
                top_author = authors[0][0]
                payload['highest_{}_name'.format(label)] = top_author
                payload['highest_{}_rank'.format(label)] = self.rank[top_author]

        report = self.template.render(payload=payload)
        self.payload = payload
        report = self.minify(report)
        return report

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

        payload = {
            'start': self.start_date,
            'end': self.end_date,
            'statistics': self.activity_by_channel
        }
        self.payload = payload

        if not self.report_flag:
            return

        fname = "output/activity_{}_to_{}".format(self.start_date, self.end_date)
        html_fname = fname + ".html"
        zip_fname = fname + ".zip"
        json_fname = fname + ".json"

        if self.produce_html:
            blob = self.create_report()
            f = open(html_fname, "w")
            f.write(blob.encode("utf8"))
            f.close()
            if open_browser:
                subprocess.call(["/usr/bin/open", html_fname])

        f = open(json_fname, "wb")
        f.write(json.dumps(payload, indent=4))
        f.close()

        zf = zipfile.ZipFile(zip_fname, mode="w")
        if self.produce_html:
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

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--week", type=int, default=0, help="Fetch messages from n weeks ago, default 0")
    parser.add_argument("--upload", action="store_true", help="Upload results back into the slack, default FALSE")
    parser.add_argument("--nocache", action="store_true", help="Don't cache downloaded messages")
    parser.add_argument("--noreport", action="store_true", help="Don't produce summary reports")
    parser.add_argument("--nohtml", action="store_true", help="Produce summary figures as json, skip HTML output")
    parser.add_argument("--nobrowser", action="store_true", help="Don't open browser with HTML report")
    args = parser.parse_args()
    upload = args.upload
    report = not args.noreport
    produce_html = not args.nohtml
    open_browser = not args.nobrowser
    cache = not args.nocache
    print "upload: {}".format(upload)
    lw = LastWeek(weeks_ago=args.week, debug=args.debug, upload=upload, cache=cache, produce_html=produce_html, report=report)
    lw.run()
