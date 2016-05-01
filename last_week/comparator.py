#! /usr/bin/env python2.7

import sys

import last_week

ln = 0
pn = 1

if len(sys.argv) == 2 and sys.argv[1] == "now":
    ln = -1
    pn = 0

last = last_week.LastWeek(weeks_ago=ln)
previous = last_week.LastWeek(weeks_ago=pn)

for obj in [last, previous]:
    obj.get_all_messages()
    obj.create_aggregates()
    obj.create_report()

lp = last.payload
pp = previous.payload


def comparator(pretty, key, lp, pp, show_percent=True, is_percent=False):
    m = "We had {} {} vs {} the week before, a change of {:.1f}%"
    ls = float(lp[key])
    ps = float(pp[key])
    if ls == ps:
        m = "{} remained the same at {}".format(pretty, ps)
        print m
        return
    per = ls * 100.0 / ps - 100
    if per < 0:
        per = -1 * per
        verb = "dropped"
    else:
        verb = "rose"
    if is_percent:
        ps = "{}%".format(ps)
        ls = "{}%".format(ls)
    m = "{} {} from {} to {}".format(pretty, verb, ps, ls)
    if show_percent:
        m = "{} {} *{:.1f}%* from {} to {}".format(pretty, verb, per, ps, ls)
    print m

print ""
print "I just posted last week's stats in #zmeta-statistics.  A brief summary:"
print ""
m = "@{} was in first place with {} messages, followed by @{} with {} messages"
first = lp['users'][0]
second = lp['users'][1]
print m.format(first['name'], first['messages'], second['name'], second['messages'])

m = "\nThis is in comparison to the week prior, where "
m += "@{} was in first place with {} messages, followed by @{} with {} messages"
first = pp['users'][0]
second = pp['users'][1]
print m.format(first['name'], first['messages'], second['name'], second['messages'])
print ""

channels = lp['channels']
new = [x for x in channels if x['new']]
if new:
    print "New channels created this week include:"
    for i in new:
        print " * #{}".format(i['name'])
    print ""


comparator("active users", "active_users", lp, pp)
comparator("total messages", "total_messages", lp, pp)
comparator("messages from undetermined-gender posters", "undetermined_gender_message_count", lp, pp)
comparator("messages from undetermined-gender posters as percentage of total", "undetermined_gender_message_percentage", lp, pp, show_percent=False, is_percent=True)
comparator("messages from female posters", "female_gender_message_count", lp, pp)
comparator("messages from female posters as percentage of total", "female_gender_message_percentage", lp, pp, show_percent=False, is_percent=True)
comparator("messages from male posters", "male_gender_message_count", lp, pp)
comparator("messages from male posters as percentage of total", "male_gender_message_percentage", lp, pp, show_percent=False, is_percent=True)
