#! /usr/bin/env python2.7

import json

import last_week

# How many weeks back do we want to go? 
weeks=2

# Sample function that, for a given message, returns the user's name
def get_user(message, lw):
    user = message['user']
    return lw.users[user]

# Sample function that tells us whether a given message references the :raccoon: 
# emoji
def is_raccoon(message):
    if message['text'].find(":raccoon:") != -1:
        return True
    return False

# One possible way we might want to print the content of a message
def print_message(message, lw):
    text = message['text'].encode('ascii', 'ignore')
    print "{}/{}: {}".format(get_user(message, lw), message['channel'], text)

# weeks_ago isn't particularly important here -- we're going to be resetting it for
# each week we look at
lw = last_week.LastWeek(report=False, produce_html=False, weeks_ago=0)

for week in range(weeks):
    lw.set_weeks(week)
    lw.get_all_messages()
    messages = lw.messages
    raccoon_counter = 0
    for message in messages:
        if is_raccoon(message):
            print_message(message, lw)
            raccoon_counter += 1
    print "Overall, found {} :raccoon: mentions in week {}".format(raccoon_counter, week)
