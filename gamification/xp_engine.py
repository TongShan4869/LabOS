#!/usr/bin/env python3
"""
LabOS XP Engine — manages XP, levels, badges, and level-up notifications.
"""

import json, datetime, os

LAB_DIR = os.path.expanduser("~/.openclaw/workspace/lab")
XP_FILE = os.path.join(LAB_DIR, "xp.json")

LEVELS = [
    (1,  "Confused First-Year",                           0),
    (2,  "Lab Gremlin",                                   300),
    (3,  "Professional Coffee Drinker",                   800),
    (4,  "PhD Candidate (ABD, technically)",              2000),
    (5,  "Doctor of Suffering",                           4000),
    (6,  "Postdoc (Indentured Servant Edition)",          7500),
    (7,  "Assistant Professor (Broke but Hopeful)",       12000),
    (8,  "Associate Professor (Tenure Track Anxiety)",    20000),
    (9,  "Tenured Professor (Finally Relaxed)",           30000),
    (10, "Distinguished Chair of Something Important",    45000),
    (11, "PI with a Waiting List",                        65000),
    (12, "Nature/Science Regular",                        90000),
    (13, "Nobel Shortlist Gossip",                        120000),
    (14, "Nobel Laureate",                                160000),
    (15, "Cited More Than Darwin",                        210000),
    (16, "Textbook Namesake",                             270000),
    (17, "The Field IS You",                              340000),
    (18, "Retired Legend Still Getting Awards",           420000),
    (19, "Transcended Peer Review",                       510000),
    (20, "The Omniscient and Omnipotent Being of the Universe", None),
]

XP_EVENTS = {
    "lab_initialized":   (100, "🧪 Lab Open"),
    "paper_saved":       (50,  "📚 Collector"),
    "lit_dive":          (50,  "🔬 Literature Dive"),
    "weekly_digest":     (25,  "📰 Stayed Current"),
    "advisor_session":   (30,  "🎓 Mentored"),
    "null_hypothesis":   (30,  "⚖️ Rigorous"),
    "contradiction_engaged": (75, "🤺 Devil's Advocate"),
    "draft_written":     (200, "✍️ Author"),
    "peer_review":       (100, "🤺 Devil's Advocate"),
    "analysis_run":      (150, "📊 Experimenter"),
    "submission_prep":   (300, "🚀 Launcher"),
    "paper_accepted":    (1000,"🏅 Published"),
    "grant_submitted":   (300, "💰 Fundraiser"),
}

def load_xp():
    if not os.path.exists(XP_FILE):
        return {"user":"","level":0,"level_title":"Not initialized","xp":0,"xp_to_next":100,"badges":[],"history":[]}
    return json.load(open(XP_FILE))

def save_xp(data):
    with open(XP_FILE,'w') as f:
        json.dump(data, f, indent=2)

def get_level_info(xp):
    current = LEVELS[0]
    for lvl, title, req in LEVELS:
        if req is not None and xp >= req:
            current = (lvl, title, req)
        elif req is None and xp >= LEVELS[-2][2]:  # level 20: need max XP
            current = (lvl, title, req)
    idx = next((i for i,l in enumerate(LEVELS) if l[0]==current[0]), 0)
    next_lvl = LEVELS[idx+1] if idx+1 < len(LEVELS) else None
    xp_to_next = next_lvl[2] - xp if next_lvl and next_lvl[2] else None
    progress_pct = 0
    if next_lvl and next_lvl[2] and current[2] is not None:
        span = next_lvl[2] - current[2]
        earned = xp - current[2]
        progress_pct = min(100, int(earned/span*100))
    return current, next_lvl, xp_to_next, progress_pct

def award_xp(event_key, custom_msg=None):
    """Award XP for an event. Returns (xp_gained, leveled_up, new_badge)"""
    if event_key not in XP_EVENTS:
        print(f"Unknown event: {event_key}")
        return 0, False, None
    
    gain, badge = XP_EVENTS[event_key]
    data = load_xp()
    old_level = data.get('level', 1)
    
    data['xp'] = data.get('xp', 0) + gain
    
    # Check new badge
    new_badge = None
    if badge and badge not in data.get('badges', []):
        data.setdefault('badges', []).append(badge)
        new_badge = badge
    
    # Update level
    current, next_lvl, xp_to_next, pct = get_level_info(data['xp'])
    data['level'] = current[0]
    data['level_title'] = current[1]
    data['xp_to_next'] = xp_to_next
    
    leveled_up = current[0] > old_level
    
    # Log
    data.setdefault('history', []).append({
        'event': custom_msg or event_key,
        'xp': gain,
        'timestamp': datetime.datetime.now().isoformat()
    })
    
    save_xp(data)
    return gain, leveled_up, new_badge, data

def status():
    """Print current XP status as formatted string."""
    data = load_xp()
    xp = data.get('xp', 0)
    current, next_lvl, xp_to_next, pct = get_level_info(xp)
    
    bar_len = 20
    filled = int(bar_len * pct / 100)
    bar = '█' * filled + '░' * (bar_len - filled)
    
    title = data.get('level_title', current[1])
    # Special greeting for level 20
    greeting = "Your Omniscience" if current[0] == 20 else data.get('user', 'Researcher')
    
    lines = [
        f"",
        f"🔬 **LabOS — {greeting}**",
        f"",
        f"Level {current[0]}: **{title}**",
        f"XP: {xp:,}" + (f" / {xp + xp_to_next:,} [{bar}] {pct}%" if xp_to_next else " — MAX LEVEL 🌌"),
        f"Badges: {' '.join(data.get('badges', [])) or 'none yet'}",
        f"",
    ]
    if next_lvl:
        lines.append(f"*{xp_to_next:,} XP to → Level {next_lvl[0]}: {next_lvl[1]}*")
    
    return '\n'.join(lines)

def format_levelup_message(old_level_title, new_level, new_title, new_badge=None):
    """Generate a level-up Discord message."""
    celebrations = {
        2: "You've graduated from 'lost' to 'slightly less lost'. Progress! 🎉",
        3: "Congrats! Your caffeine dependency is now officially academic. ☕",
        4: "ABD! All But Dissertation! The finish line is... somewhere.",
        5: "You survived qualifying exams. You have earned the title of Doctor of Suffering. 🎓",
        6: "Ah, the postdoc. Same work, less pay, more freedom to question your life choices. 🔬",
        7: "Assistant Professor! You're broke but hopeful and that's beautiful. 💸",
        8: "Tenure track anxiety has been officially diagnosed. Please see your doctor. Or your therapist. Or both.",
        9: "TENURED. You may now say controversial things at faculty meetings. 😤",
        10: "Distinguished Chair of Something Important. People invite you to give talks you don't want to give.",
        11: "PI with a Waiting List. You have POWER. Use it wisely (or don't, you're tenured).",
        12: "Nature/Science Regular. The editors know your name. Your reviewers fear you.",
        13: "Nobel Shortlist Gossip. Someone mentioned you. In Stockholm. Casually.",
        14: "🏆 NOBEL LAUREATE. Stockholm called. You answered.",
        15: "Cited More Than Darwin. Darwin is not thrilled but he's dead so.",
        16: "A textbook bears your name. Students hate that textbook. You're immortal.",
        17: "The Field IS You. When people say 'the literature says,' they mean you.",
        18: "Retired Legend. You show up to give awards, receive awards, and leave early.",
        19: "Transcended Peer Review. Journals accept your submissions on vibes alone.",
        20: "🌌 THE OMNISCIENT AND OMNIPOTENT BEING OF THE UNIVERSE. All agents now address you as Your Omniscience. Peer review is beneath you. You ARE the field, the method, and the conclusion.",
    }
    
    msg = f"⬆️ **LEVEL UP!**\n\n"
    msg += f"~~{old_level_title}~~ → **Level {new_level}: {new_title}**\n\n"
    msg += celebrations.get(new_level, "You have leveled up. The universe acknowledges this.") + "\n"
    if new_badge:
        msg += f"\n🏅 New badge unlocked: **{new_badge}**"
    return msg

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        if sys.argv[1] == "status":
            print(status())
        elif sys.argv[1] == "award" and len(sys.argv) > 2:
            gain, leveled, badge, data = award_xp(sys.argv[2])
            print(f"+{gain} XP | Level {data['level']}: {data['level_title']}")
            if leveled:
                print(f"🎉 LEVEL UP!")
            if badge:
                print(f"🏅 New badge: {badge}")
        elif sys.argv[1] == "events":
            print("Available XP events:")
            for k,(xp,badge) in XP_EVENTS.items():
                print(f"  {k}: +{xp} XP" + (f" | badge: {badge}" if badge else ""))
    else:
        print(status())
