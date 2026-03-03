# lab-research-advisor — Execution Script

## Step 1: Load context

Read:
- `LAB_CONFIG.json` → user name, fields
- `LAB_MEMORY.md` → preferences, known blind spots, interaction patterns
- `research-graph.jsonl` → targeted project (or all active projects if no --project flag)

Extract from project(s):
- Hypotheses (H1, H0, status)
- Linked papers (especially contradicting ones)
- Experiments (status, results)
- Last advisor session date
- Stale nodes (not updated in >2 weeks)

---

## Step 2: Pre-session diagnostics

Before asking questions, quietly scan for issues to surface:

**Hypothesis checks:**
- [ ] H0 (null hypothesis) defined?
- [ ] Falsification criteria defined? ("What would prove you wrong?")
- [ ] Contradicting papers acknowledged in graph?
- [ ] Hypothesis updated since last lit-scout?

**Literature checks:**
- [ ] Last lit-scout > 3 weeks ago?
- [ ] Papers linked but never summarized?
- [ ] High-relevance papers from field-trend not linked to project?

**Methods checks:**
- [ ] Experimental design logged?
- [ ] Sample size / power analysis done? (cross-check with lab-biostat)
- [ ] Controls documented?

**Progress checks:**
- [ ] Project stale (no updates in >2 weeks)?
- [ ] Blocked tasks with no notes?

---

## Step 3: Open the session

Greet based on LAB_MEMORY context:

**Hard mode (default):**
```
"Alright {user}, let's talk about {project}. 
Last session was {X days ago}. Here's what I'm seeing:

{list 2-3 most pressing issues from diagnostics}

Let's start with the biggest one: {top issue}. {First hard question}."
```

**Supportive mode:**
```
"Hey {user}, let's check in on {project}. 
You've made some good progress — {what's been done}.

I want to help you think through {area}. {Gentler opening question}."
```

---

## Step 4: Question bank by focus area

### `--focus hypothesis` (or default if hypotheses incomplete)
- "What would falsify your H1? Be specific."
- "Have you defined H0? If not, what is it?"
- "You've cited [paper X] 3 times but [paper Y] contradicts it directly. How do you address that?"
- "If your H1 is true, what's the mechanism? Is it testable?"
- "What's the effect size you're expecting, and why?"

### `--focus gaps`
- "What's the most important paper you haven't read yet?"
- "Who are the 3 labs doing the closest work to yours right now?"
- "What question in your field is nobody asking? Is that an opportunity?"
- "Your lit review is {n} papers. Is that enough to claim you know the field?"

### `--focus methods`
- "Walk me through your study design. What are your controls?"
- "What's your N? Have you done a power analysis? (If not, run lab-biostat --mode power)"
- "What are the top 3 confounds in your design? How are you handling them?"
- "If you ran this experiment and got a null result, would it be informative? Why?"

### `--focus writing`
- "Who is your target reader? Generalist or specialist?"
- "What's the one sentence this paper is about?"
- "What's the gap in the literature your paper fills? Say it in one sentence."
- "Your abstract says {X}. Does your data actually support that claim?"

### `--focus next-steps`
- "What's the one thing that would move this project forward the most right now?"
- "What are you avoiding? Why?"
- "If you had to submit this in 30 days, what would you cut?"

---

## Step 5: Conduct the session

Run as a conversation. After each user response:
- Acknowledge briefly (1 sentence)
- Follow up with a deeper question OR move to next issue
- Don't let vague answers slide — push for specifics

Session ends when:
- User says "done", "thanks", "exit", "that's enough"
- 5+ substantive exchanges have happened
- All diagnostic issues have been addressed

---

## Step 6: Session summary

At end of session, output:

```
📋 **Session Summary — {project} — {date}**

**Questions addressed:**
- {question 1} → {user's answer summary}
- ...

**Action items identified:**
- [ ] {action 1}
- [ ] {action 2}

**Graph updates needed:**
- {e.g. "Log null hypothesis for proj_X"}
- {e.g. "Link paper Y to hypothesis H1"}

**Next advisor check-in suggested:** {in 2 weeks or when X is done}
```

---

## Step 7: Update research graph

Based on session, update graph nodes:
- Add H0 if defined during session
- Link new papers mentioned
- Update project "last_advisor_session" timestamp
- Flag action items as Task nodes

---

## Step 8: Update LAB_MEMORY.md

Note any new patterns:
- User consistently avoids methods critique → flag as blind spot
- User prefers shorter sessions → note preference
- User logged H0 unprompted today → positive pattern

---

## Step 9: Award XP

+30 XP. Badge: "🎓 Mentored" (first time). Log to xp.json.
