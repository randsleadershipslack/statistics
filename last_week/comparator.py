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


def comparator(pretty, key, lp, pp):
    m = "We had {} {} vs {} the week before, a change of {:.1f}%"
    ls = lp[key]
    ps = pp[key]
    per = ls * 100.0 / ps - 100
    if per < 0:
        per = -1 * per
        verb = "dropped"
    else:
        verb = "rose "
    m = "{} {} {:.1f}% from {} to {}".format(pretty, verb, per, ps, ls)
    print m

print ""
m = "@{} was in first place with {} messages, followed by @{} with {} messages"
first = lp['users'][0]
second = lp['users'][1]
print m.format(first['name'], first['messages'], second['name'], second['messages'])
comparator("active users", "active_users", lp, pp)
comparator("total messages", "total_messages", lp, pp)
comparator("messages from undetermined-gender posters", "undetermined_gender_message_count", lp, pp)
comparator("messages from female-gender posters", "female_gender_message_count", lp, pp)
comparator("messages from male-gender posters", "male_gender_message_count", lp, pp)
