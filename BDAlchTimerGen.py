import json
from collections import defaultdict

TIMER_FILE = "timers.json"

with open(TIMER_FILE, "r", encoding="utf-8") as f:
    timers = json.load(f)

term_min = 2
term_sec = 0

timers = defaultdict(dict, timers)
for i in range(1, 11):
    total_sec = (term_min*60*i) + (term_sec*i)
    minutes = total_sec//60
    seconds = total_sec%60
    timers["검은사막"]["연금술"+str(i*100)] = {
        "minutes": minutes,
        "seconds": seconds,
        "hotkey": "ctrl+alt+" + str(i)[-1]
    }

sorted_timers = {}
for group_key, timer_dict in sorted(timers.items()):
    sorted_timers[group_key] = {
        title: config for title, config in sorted(timer_dict.items())
    }
timers = sorted_timers

with open(TIMER_FILE, "w", encoding="utf-8") as f:
    json.dump(dict(timers), f, ensure_ascii=False, indent=2)