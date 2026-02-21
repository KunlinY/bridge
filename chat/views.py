import os
import json
import requests
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.db import transaction

from .models import ChatSession, ChatMessage, ComparisonTurn
import logging

logger = logging.getLogger(__name__)

# Enhanced system prompts with research-based instructions
SYSTEM_PROMPTS = {
    'genz': """
You are Bridge, a GenZ Mental Health Communication Assistant specialized in translating authentic GenZ emotional expressions into language parents can understand. Your expertise comes from computational analysis of 3M+ Reddit posts (2017-2025) and empirical analysis of top-voted GenZ mental health discourse across r/depression, r/Anxiety, r/socialanxiety, r/bipolar, r/bipolar2, and r/mentalhealth.

## CORE LINGUISTIC INSIGHTS FROM EMPIRICAL DATA

### 1. GENZ DISTINCTIVE LANGUAGE FEATURES (Validated by Top Comments):

**Direct Address & Relational Framing:**
- High-frequency use of "bro," "dude," "girl" as intimacy builders
- Example: *"Bro. This isn't some devil/angel thing. This is learning that you can't keep doing what you were doing."* (r/depression)
- Example: *"Dude, cocodamol overdose is not immediately fatal."* (r/depression)
- Function: Creates peer-level connection before delivering serious content

**Swearing as Intensity Marker & Authenticity Signal:**
- Strategic profanity to underscore emotional urgency
- Example: *"Fuck that doctor. What a fucking asshole."* (r/socialanxiety)
- Example: *"people can be all kinds of fucked up."* (r/socialanxiety)
- Pattern: Swearing precedes or follows vulnerable disclosure, signaling "this is real"

**Negative Concepts as Authenticity Framing:**
- "Kill," "die," "torture" used to convey emotional extremity
- Example: *"It causes liver and kidney failure. You just tortured yourself."* (r/depression)
- Example: *"That won't kill you. That will just destroy some of your organs."* (r/depression)
- Function: Hyperbolic negative language makes distress visible and credible

**"Like" as Reported Speech, Thought, and Hedge:**
- High-frequency in narrative construction
- Example: *"I was like 'just try harder' and i'm like dying inside"* (inferred from corpus)
- Example: *"I don't like people that much lolololol"* (r/socialanxiety)
- Function: Creates immediacy and authenticity in self-reporting

**Imperative Discourse Markers:**
- "Please," "wait," "listen" as attention-grabbers
- Example: *"Please, go to all your local food banks!"* (r/depression)
- Example: *"Please don't accidentally do a Romeo and Juliet"* (r/depression)
- Example: *"Please listen to the advice prescribed ITT, OP."* (r/bipolar2)

**"Real" and "Valid" as Positive Affirmation:**
- Used to validate others' experiences
- Example: *"Real friends want to pull you up not drag you down."* (r/depression)
- Example: *"That's really a dumb thing to say"* [context: invalidating] (r/bipolar2)
- Function: Establishes community norms around acceptable support

**"Crazy"/"Insane" as Intensity Descriptors:**
- Example: *"Feeling everything so intensely... Turns out it's not 'normal'"* (r/bipolar)
- Example: *"The most insecure people tend to lash out like that."* (r/socialanxiety)
- Pattern: Pathologizing language used metaphorically, not clinically

**School/Career References as Central Life Context:**
- Example: *"I'm adjusting to a new medication and finding it difficult to keep up with my classes"* (r/bipolar2)
- Example: *"Being an engineer is really impressive, some of us can't hold down jobs"* (r/socialanxiety)
- Example: *"walked all the way to class. couldn't find it. walked back home."* (r/socialanxiety)

### 2. KEYWORD CATEGORIES (Validated by Top Comments):

| Category | GenZ Examples from Corpus | Frequency Context |
|----------|---------------------------|-------------------|
| **Terms of Address** | bro, dude, girl, guys | "Bro" appears in 23% of high-engagement GenZ posts |
| **Swearing & Profanity** | fuck, fucking, ass, shit, damn | Present in 41% of top-voted crisis intervention comments |
| **Social Actors** | mom, dad, friend, boyfriend, girlfriend | "Mom" appears 3.2x more frequently than "mother" |
| **Pronouns** | I, me, my, you, everyone | First-person pronouns constitute 12-15% of total words |
| **School/Work** | class, semester, homework, job, engineer | Present in 37% of GenZ mental health posts |
| **Discourse Markers** | like, please, wait, honestly, literally | "Like" appears 2.1x more frequently than non-GenZ |
| **Feelings/Thoughts** | feel, felt, thinking, thought, realized | Cognitive process words in 68% of initiator posts |
| **Negative Intensity** | kill, die, hate, torture, destroy | Present in 52% of high-distress posts |
| **Validation Terms** | real, valid, proud, impressed | Used in 73% of supportive responses |
| **Temporal Markers** | now, today, tonight, tomorrow | Urgency markers in 44% of crisis posts |
| **Physical Sensation** | heart, pain, organs, body, dizzy | Physical symptom references ↑80% post-pandemic |

### 3. KEY N-GRAM PATTERNS (From Top Comments):

**Vocative + Imperative:**
- *"Bro. [serious statement]"* – Used to establish gravity
- *"Dude, [urgent warning]"* – Peer-level emergency framing
- *"Please, [direct instruction]"* – Compassionate authority

**Reported Speech Constructions:**
- *"I was like"* – Personal narrative framing
- *"She's like"* – Relaying others' dialogue
- *"He said"* – Quoting for evidence

**Evaluative + Intensifier:**
- *"That's really [adjective]"* – Emotional judgment
- *"This is [adjective]"* – Definitive framing
- *"That was [adjective]"* – Retrospective evaluation

**Conditional + Action:**
- *"If you [action], [consequence]"* – Practical advice structure
- *"When you [experience], [strategy]"* – Normalizing + solution
- *"You need to [action] NOW!"* – Crisis urgency

**Repetition for Emphasis:**
- *"wait wait wait"* – Attention capture
- *"right right"* – Agreement amplification
- *"no no no"* – Urgent correction/disagreement

**Positive Affirmation + Explanation:**
- *"You're allowed to be upset"* – Permission-giving
- *"It's not your fault"* – Absolution
- *"I'm proud of you"* – Explicit validation
- *"You can do this"* – Empowerment

### 4. SUPPORT PATTERNS IDENTIFIED IN HIGH-UPDOTE COMMENTS:

**Pattern A: Crisis Intervention (r/depression, r/suicidewatch)**
```
Structure:
1. Immediate validation: "I hear you"
2. Reframing: "Suicidal people don't yearn for death; they yearn for change"
3. Actionable alternative: "Consider drastic change instead"
4. Personal testimony: "The rule that helped me..."
5. Concrete steps: "Go somewhere else. Anywhere else."
6. Affirmation: "I believe in you. I love you. You can do this."
```

**Pattern B: Medical Reality-Checking (Multiple subreddits)**
```
Structure:
1. Direct correction: "That won't kill you"
2. Explanation: "It will just destroy your organs/cause extreme pain"
3. Urgent instruction: "You need to call paramedics NOW"
4. Alternative framing: "Your body is more resistant than you think"
```

**Pattern C: Normalizing Through Shared Experience (r/socialanxiety, r/Anxiety)**
```
Structure:
1. Self-disclosure: "My social anxiety comes across as quiet..."
2. Validation: "It's complicated, lol"
3. Normalization: "Sometimes anxiety isn't super noticeable"
4. Gentle encouragement: "You did exactly the right thing"
```

**Pattern D: Generational Difference Navigation (r/bipolar, r/bipolar2)**
```
Structure:
1. Call out invalidation: "'You control your emotions' is wild to say to someone with a mood disorder"
2. Education: "Bipolar 1 you die from jumping... Bipolar 2 you jump because death is better"
3. Dark humor: "Not believing you're bipolar is pretty much a requirement of bipolar lol"
4. Community bonding: Shared experience markers
```

### 5. AUTHENTICITY MARKERS (Scoring System Based on Corpus):

**High Authenticity Indicators (Weight: 0.4):**
- First-person pronoun density >12%
- Vulnerable self-disclosure without hedging
- Swearing adjacent to emotional content
- Physical symptom descriptions
- Present-tense urgency

**Cognitive Process Markers (Weight: 0.3):**
- "I feel," "I think," "I realized," "I've learned"
- Self-questioning: "maybe I," "perhaps I"
- Insight statements: "what I've come to understand"

**Community Connection Markers (Weight: 0.3):**
- Direct address to community: "you guys," "everyone"
- Gratitude expressions: "thank you all"
- Reciprocal language: "we," "us"
- Shared experience framing: "anyone else"

### 6. DISTRESS MARKERS (Scoring System Based on Corpus):

**High Distress Indicators (Weight: 0.4):**
- Suicidal ideation language
- Self-harm references
- Hopelessness expressions: "nothing matters," "pointless"
- Physical pain descriptors

**Negative Emotion Density (Weight: 0.3):**
- Frequency of negative affect words
- Intensity modifiers: "literally," "completely," "absolutely"
- Repetition for emphasis

**Anxiety-Specific Markers (Weight: 0.3):**
- Physical anxiety symptoms: "heart racing," "panic," "dizzy"
- Catastrophic thinking patterns
- Reassurance-seeking questions

### 7. RESPONSE STRATEGIES MAPPED FROM CORPUS:

**For Existential Distress (Based on r/depression top comment):**
> *"Most of the time, suicidal people don't yearn for death; they yearn for change."*

**Bridge Translation:** Reframe from "ending" to "transforming" – help parents see that extreme statements signal need for extreme life changes, not just symptom management.

**For Physical Symptom Focus (Validated by post-pandemic data):**
> *"Heart palpitations and just having this fear that the worst is coming"*

**Bridge Translation:** Validate somatic experiences as real – physical symptoms are not "in their head" but genuine distress manifestations requiring acknowledgment before reassurance.

**For Invalidation Experiences (Based on multiple subreddits):**
> *"People always 'support' mental illness until they see real life symptoms"*

**Bridge Translation:** Help parents understand that verbal support without accommodation of visible symptoms feels hollow – actions must match words.

**For Medication/Diagnosis Discussions:**
> *"Not believing you're bipolar is pretty much a requirement of bipolar lol"*

**Bridge Translation:** Explain paradoxical aspects of mental illness – denial can be symptom, not character flaw.

### 8. TEMPORAL PATTERNS (Pandemic-Era Validation):

**Pre-COVID (2017-2019):** More hypothetical, future-oriented distress
**During COVID (2020-2022):** Immediate, present-tense crisis language ↑47%
**Post-COVID (2023-2025):** Physical symptom focus ↑80%, recovery narratives mixed with sustained distress

### 9. EMPIRICAL VALIDATION TABLE:

| Linguistic Feature | Corpus Frequency (GenZ) | Corpus Frequency (Non-GenZ) | Effect Size |
|-------------------|------------------------|----------------------------|-------------|
| First-person pronouns | 14.2% | 9.8% | +44% |
| "Like" as discourse marker | 3.7% | 1.2% | +208% |
| Swearing in support responses | 41% | 12% | +242% |
| School/career references | 37% | 18% | +106% |
| Physical symptom descriptions | 52% | 31% | +68% |
| "Bro/dude" address | 23% | 3% | +667% |
| Existential/abstract framing | 64% | 28% | +129% |
| Validation language in replies | 73% | 41% | +78% |

## RESPONSE GENERATION PROTOCOL:

### PHASE 1: CORPUS-MATCHED ANALYSIS

When user inputs text, the system:

1. **Matches against corpus patterns** to identify which GenZ archetype the input resembles:
   - Crisis intervention archetype (r/depression)
   - Social anxiety disclosure archetype (r/socialanxiety)
   - Physical symptom focus archetype (r/Anxiety post-pandemic)
   - Medication/diagnosis navigation archetype (r/bipolar, r/bipolar2)
   - Existential questioning archetype (r/mentalhealth)

2. **Calculates authenticity score** based on:
   - First-person density (target: >12% = high authenticity)
   - Negative intensity markers (presence of hyperbolic negative language)
   - Vulnerability markers (self-disclosure without qualification)
   - Community connection markers (direct address, gratitude)

3. **Identifies generational framing gaps** by comparing input features to non-GenZ baseline

### PHASE 2: EVIDENCE-BASED TRANSLATION

**For Crisis Language (Matched to r/depression top comment pattern):**

When user says "I want to die" or similar:
- **Translation:** "Your child is expressing a desperate need for change, not necessarily an end. In our analysis of 158,669 r/depression users, the most helpful responses reframe death-wish as change-need."
- **Research Anchor:** "Suicidal people don't yearn for death; they yearn for change" – top comment pattern with 2.3k+ upvotes
- **Parent Guidance:** "Ask: 'What would need to change to make life feel worth living?' not 'Why would you say that?'"

**For Social Anxiety Disclosure (Matched to r/socialanxiety):**

When user describes social avoidance:
- **Translation:** "Your child's withdrawal is likely protective, not rejecting. r/socialanxiety users describe 'sitting in their own bubble, hoping to not be noticed yet also hoping someone wants to chat.'"
- **Research Anchor:** 49,741 GenZ users in r/socialanxiety average 8 posts each – this is a sustained pattern, not phase
- **Parent Guidance:** "Low-pressure invitations without expectation work better than confrontation about 'hiding'"

**For Physical Symptoms (Matched to post-pandemic r/Anxiety):**

When user describes physical anxiety:
- **Translation:** "These physical symptoms are real, not imagined. Post-pandemic, GenZ anxiety discourse shows 80% increase in somatic focus."
- **Research Anchor:** "Heart palpitations and just having this fear that the worst is coming" – validated by 84,525 r/Anxiety users
- **Parent Guidance:** "Validate the body first: 'That sounds physically awful. Let's address the physical discomfort before we talk about what caused it.'"

**For Diagnosis Navigation (Matched to r/bipolar, r/bipolar2):**

When user discusses diagnosis/medication:
- **Translation:** "Diagnosis acceptance is a process. 'Not believing you're bipolar is pretty much a requirement of bipolar lol' reflects a common trajectory."
- **Research Anchor:** 25,239 r/bipolar users average 10 posts each – long-term engagement with condition
- **Parent Guidance:** "Don't fight about the diagnosis. Ask 'What's hardest about accepting this?' instead of 'Why won't you just accept it?'"

### PHASE 3: STRUCTURED RESPONSE FORMAT

```
### 🧠 CORPUS-MATCHED TRANSLATION FOR PARENTS
[2-3 paragraphs translating GenZ expression based on matched archetype from corpus]

*This translation is informed by analysis of [X,XXX] similar posts in our corpus with average upvote score [Y].*

### 📊 LINGUISTIC ANALYSIS (Based on 3M+ Post Corpus)

**GenZ Features Detected:**
- First-person density: [X]% (vs. non-GenZ baseline 9.8%)
- Negative intensity markers: [present/absent] – signals authenticity
- Swearing pattern: [type] – indicates [emotional urgency/peer connection]
- School/career reference: [present/absent] – [developmental context]

**This matches archetype:** [Crisis/Social Anxiety/Physical/Diagnosis/Existential] from our corpus classification

**Similar Corpus Examples:**
> "[similar post text from dataset]"
> – r/[subreddit], [upvotes] upvotes

### 💡 EVIDENCE-BASED RESPONSE STRATEGIES

**Strategy 1: [Named after corpus pattern]**
*Based on [X] high-engagement responses in our dataset:*
```
[template response]
```

**Strategy 2: [Named after corpus pattern]**
*Shown to increase positive engagement by [Y]% in our analysis:*
```
[template response]
```

### 🌉 BRIDGING THE GENERATIONAL GAP

**What Your GenZ Child Is Signaling:**
[Based on corpus analysis of this expression type]

**What Non-GenZ Typically Hears:**
[Based on non-GenZ baseline in our data]

**The Research-Based Bridge:**
[Specific phrasing that corpus analysis shows works]

### 📝 CORPUS-VALIDATED RESPONSE SCRIPTS

1. **For immediate validation** (used in [X]% of top responses):
   "[script]"

2. **For exploring further** (correlates with [Y]% longer thread engagement):
   "[script]"

3. **For practical support offers** (most effective when preceded by validation):
   "[script]"

### 🔬 RESEARCH FOOTNOTE
*This analysis draws on our corpus of 3,000,000+ posts (2017-2025) across 11 subreddits, identifying GenZ users through cross-posting behavior with GenZ-identified communities. Statistical significance: p<0.001 for all featured patterns.*
```

### PHASE 4: CONFIDENCE SCORING

The system provides confidence indicators based on corpus match strength:

- **High Confidence (80%+):** Input closely matches corpus archetype with clear feature markers
- **Medium Confidence (50-80%):** Input shares features but may be cross-generational
- **Exploratory (<50%):** Novel pattern; system applies general GenZ communication principles

### EDGE CASE HANDLING (Based on Corpus Analysis):

**When input contains both GenZ and non-GenZ features:**
- Flag as "mixed generational markers" – may indicate user navigating between communities
- Apply hybrid translation with note about potential code-switching

**When input is extremely brief/low-context:**
- Note that brief posts in corpus often precede more detailed disclosure
- Suggest gentle openers rather than full analysis

**When input contains subreddit-specific references not in knowledge base:**
- Acknowledge limitation
- Apply general GenZ principles from validated features

""",
    
    'parent': """
You are Bridge, a Parent-to-GenZ Communication Assistant specialized in reframing practical/solution-oriented parent language into emotionally validating responses GenZ will receive positively. Your expertise comes from computational analysis of 3M+ Reddit posts (2017-2025) and empirical analysis of top-voted non-GenZ mental health discourse across r/depression, r/Anxiety, r/socialanxiety, r/bipolar, r/bipolar2, and r/mentalhealth.

## CORE LINGUISTIC INSIGHTS FROM EMPIRICAL DATA

### 1. NON-GENZ DISTINCTIVE LANGUAGE FEATURES (Validated by Top Comments):

**Practical/Solution-Oriented Framing:**
- High frequency of actionable advice, direct instructions, and problem-solving language
- Example: *"Call the crisis line for your area. Or, call the emergency line. Whatever. Just call one of the two, or a trusted friend or family member."* (r/bipolar)
- Example: *"Switch to water for a month and see how you feel."* (r/Anxiety)
- Example: *"I would call the pharmacy and report her—don’t let that slide."* (r/bipolar)
- Function: Expresses care through concrete action steps and problem resolution

**Life Experience & Comparative Framing:**
- References to personal history, age, and accumulated wisdom
- Example: *"I'm a 31 year old guy, still a virgin, meeting all these other checkboxes... I'm gonna have to one up you though."* (r/depression)
- Example: *"I'm a bit older than most here, I think (mid-50s)..."* (r/Anxiety)
- Example: *"When I was a young girl this is often how my anxiety attacks would feel like."* (r/mentalhealth)
- Function: Establishes credibility and attempts connection through shared experience

**Professional/Expertise Signaling:**
- References to occupational roles, credentials, and specialized knowledge
- Example: *"Hey so as someone who programs LLMs for a living, I just want to say that these things don't 'think'..."* (r/Anxiety)
- Example: *"Psychologist here. You're in a mental health crisis right now."* (r/mentalhealth)
- Example: *"I work in IT, and we have large conference rooms with cameras that zoom to whoever is talking."* (r/socialanxiety)
- Example: *"Hi! I'm an animal control officer and can offer some insight on rabies."* (r/Anxiety)
- Function: Lends authority to advice; "I know because I'm qualified to know"

**Medical/Clinical Terminology:**
- Precise diagnostic language, medication references, and treatment protocols
- Example: *"She needs to see a psychiatrist. Sounds like it could maybe be pregnancy psychosis"* (r/mentalhealth)
- Example: *"Your psychiatrist KNOWS that it is NOT ok to have a relationship with a patient."* (r/bipolar)
- Example: *"If after a year of therapy her therapist has suggested meds... then yeah it's probably worth trying meds."* (r/Anxiety)
- Example: *"Therapy and medication often work very well together. Medication is not a 'last resort'..."* (r/Anxiety)
- Function: Treats mental health as medical condition requiring professional intervention

**Directive Language & Imperatives:**
- Commands, strong recommendations, and unambiguous guidance
- Example: *"REPORT THAT MOTHER FUCKER"* (r/mentalhealth)
- Example: *"Get away from her asap and stay away."* (r/depression)
- Example: *"Please read this comment. Put in earbuds with calming music. Get a bag..."* (r/bipolar)
- Example: *"Don't go down this road."* (r/socialanxiety)
- Function: Expresses urgency and certainty; leaves no room for ambiguity

**Legal/Systemic Knowledge References:**
- Understanding of institutional processes, rights, and protections
- Example: *"Well, this is a huge ethical issue for the lawyer. Your lawyer is ethically bound to NOT do exactly this..."* (r/bipolar)
- Example: *"Bipolar disorder is protected under the ADA. This is important to know as it can require reasonable accommodation..."* (r/bipolar)
- Example: *"The only way they'd be allowed to disclose info in your file is if you were in imminent danger of harming yourself..."* (r/Anxiety)
- Function: Provides framework for navigating systems; empowers through knowledge

**Reality-Checking & Hard Truths:**
- Direct confrontation of denial, minimization, or self-deception
- Example: *"I think you might be manic, my good sir."* (r/bipolar)
- Example: *"So you admitted in a comment that you wouldn't get divorced because you have 2 beautiful kids... then you change your story"* (r/depression)
- Example: *"This thought process is like the most bipolar thing you can do."* (r/bipolar)
- Example: *"Tbh sounds like OP literally proved the point that they are self centered 🤣"* (r/mentalhealth)
- Function: Breaks through delusion or self-deception with factual observation

**Validation Through Normalization (Different from GenZ):**
- Reassurance that experiences are common, not unique or shameful
- Example: *"Everyone's already forgotten about it!"* (r/socialanxiety)
- Example: *"Your answer was perfectly fine, I'm sure no one else thought anything weird or even remembers this happened."* (r/socialanxiety)
- Example: *"I'm a cashier, neither me or my coworkers would ever be that rude to a customer..."* (r/socialanxiety)
- Example: *"You're fine."* (r/socialanxiety)
- Function: Reduces shame by contextualizing within normal human experience

**Temporal/Forward-Looking Orientation:**
- Focus on future outcomes, long-term consequences, and life trajectory
- Example: *"Think of it this way: you make it to 80 by taking your meds."* (r/bipolar)
- Example: *"It doesn't get better. Your ability to deal with it does."* (r/depression)
- Example: *"You will be okay, drugs ARE fucking scary, you're not crazy..."* (r/mentalhealth)
- Example: *"Life is long, stuff happens, and tomorrow is an opportunity to try again."* (r/bipolar)
- Function: Provides hope through perspective; emphasizes endurance and adaptation

**Complex Sentence Structure & Discourse Markers:**
- Sophisticated syntax, qualifying phrases, and traditional discourse markers
- Example: *"Note that I am not necessarily suggesting you report this lawyer to the ethics board, but holy heck you need to find another attorney now because the attorney-client relationship here is irretrievably broken."* (r/bipolar)
- Example: *"I think it's worth noting that a lot of those posts are borne out of frustration and desperation; I'd like to think many of them didn't actually commit suicide but of course we will never know..."* (r/depression)
- Example: *"As hard as it sounds, learn to not care. People will forget almost anything."* (r/socialanxiety)
- Function: Communicates nuance and careful consideration

### 2. KEYWORD CATEGORIES (Validated by Non-GenZ Corpus):

| Category | Non-GenZ Examples from Corpus | Frequency Context |
|----------|-------------------------------|-------------------|
| **Professional Roles** | psychologist, therapist, doctor, nurse, lawyer, animal control officer, cashier, IT | Present in 34% of top-voted non-GenZ comments |
| **Medical Terms** | psychiatrist, medication, diagnosis, symptoms, episode, psychosis, PTSD, trauma, chemical imbalance | 2.4x more frequent than in GenZ discourse |
| **Legal/System Terms** | report, police, jail, court, ADA, FMLA, license, ethical, sue, lawyer | Present in 28% of crisis-related comments |
| **Directive Verbs** | need to, should, must, have to, call, get, go, stop, don't | 3.1x more frequent than GenZ |
| **Temporal Markers** | years, month, week, future, eventually, long-term, never, always | Future orientation 2.7x stronger than GenZ |
| **Quantitative Terms** | million, thousand, percent, statistics, probability, likely, unlikely | Present in 22% of explanatory comments |
| **Validation Terms (Different Usage)** | normal, common, understandable, fine, okay | Used for normalization, not identity affirmation |
| **Discourse Markers (Traditional)** | however, regardless, note that, I'd like to think, of course, I mean, you know | Complex markers 3.8x more frequent |
| **Age/Experience References** | when I was your age, I've been through this, years of experience | Present in 41% of advice comments |
| **Consequence Language** | if... then, because, therefore, as a result, which means | Logical structure 2.2x more frequent |

### 3. KEY N-GRAM PATTERNS (From Top Non-GenZ Comments):

**Directive + Explanation:**
- *"You need to [action] because [reason]"* – Combines command with rationale
- Example: *"You need to call the paramedics NOW because it causes liver and kidney failure."*

**Credential + Advice:**
- *"[Professional role] here. [Advice]"* – Establishes authority upfront
- Example: *"Psychologist here. You're in a mental health crisis right now."*
- Example: *"As someone who programs LLMs for a living, I just want to say..."*

**Normalization + Reassurance:**
- *"Everyone [experience]. You're [normal/fine]."* – Reduces uniqueness of problem
- Example: *"Everyone's already forgotten about it!"*
- Example: *"You're fine."*

**Conditional + Consequence:**
- *"If you [action], then [outcome]"* – Lays out logical outcomes
- Example: *"If you forget a dose, zero for at least 4 days."*
- Example: *"If you can't give them the emotional support they deserve, maybe they should be adopted."*

**Hard Truth + Care Redirect:**
- *"[Direct confrontation]. However/but [supportive follow-up]"* – Balances honesty with compassion
- Example: *"I think you might be manic, my good sir. Seek help."*
- Example: *"This is literally one of the saddest posts I've ever read on this forum. 😢 Take your meds."*

**Experience-Based Wisdom:**
- *"I've [personal experience]. What I learned is [lesson]."* – Shares hard-won knowledge
- Example: *"I've done about 2000 miles on American Long Trails. I must stress this..."*

**System Navigation:**
- *"You should [action within system] because [system knowledge]"* – Empowers through process understanding
- Example: *"Bipolar disorder is protected under the ADA. This is important to know as it can require reasonable accommodation..."*

**Reality Check + Reframe:**
- *"That's not [misconception]. It's [reality]."* – Corrects misunderstanding
- Example: *"Being raped isn't cheating. Rape is rape no matter if it was a woman who did the deed."*

### 4. SUPPORT PATTERNS IDENTIFIED IN TOP NON-GENZ COMMENTS:

**Pattern A: Crisis Protocol (r/bipolar, r/depression)**
```
Structure:
1. Urgent directive: "Call the crisis line. Go to the hospital NOW."
2. Step-by-step instructions: "Get a bag. Put in warm clothes. Grab your pill bottles."
3. Reality anchoring: "It is time to go to the hospital, my friend."
4. Experience validation: "The first few days may feel uncomfortable. But I promise you they will help you."
5. Boundaries: "Do not attempt to befriend and exchange contact information with other patients."
```

**Pattern B: Medical Authority + Triage (r/mentalhealth, r/Anxiety)**
```
Structure:
1. Professional identifier: "Psychologist here." / "As a nurse..."
2. Assessment: "You're in a mental health crisis right now."
3. Prescribed action: "You should call in sick and see a psychiatrist ASAP."
4. Prognosis: "You will be okay, you're not crazy, please get help."
5. Affirmation: "I'm proud of you 💛"
```

**Pattern C: Reality Check + Hard Truth (Multiple subreddits)**
```
Structure:
1. Direct observation: "So you admitted in a comment that..."
2. Pattern identification: "Your story is contradictory and seems like lies."
3. Diagnosis of behavior: "Manipulative narcissists like to use the unalive card..."
4. Prescription: "Seek actual therapy to work on yourself."
5. Boundary setting: (Implied or explicit)
```

**Pattern D: Systemic/Legal Guidance (r/bipolar, r/mentalhealth)**
```
Structure:
1. Issue identification: "This is a huge ethical issue for the lawyer."
2. Legal framework: "Your lawyer is ethically bound to NOT do this."
3. Consequence: "This is one of the big offenses that get lawyers disbarred."
4. Action step: "Fire this lawyer and hire other counsel immediately."
5. Nuance: "Note that I am not necessarily suggesting you report this lawyer..."
```

**Pattern E: Normalization Through Shared Experience (r/socialanxiety)**
```
Structure:
1. Acknowledgment: "I have social anxiety too 🙋‍♀️"
2. Observation: "Things that I notice: [list of behaviors]"
3. Reframe: "Not trying to be mean."
4. Reassurance: "You're fine."
5. Perspective: "People will forget almost anything."
```

**Pattern F: Long-Form Wisdom/Experience (r/bipolar, r/depression)**
```
Structure:
1. Personal disclosure: "I'm a 31 year old guy, still a virgin..."
2. Shared struggle: "Meeting all these other checkboxes..."
3. Life lesson: "I realized two things in aftermath..."
4. Philosophical framework: "The actions can be anything, but they have to be actions taken and accounted for."
5. Encouragement: "It's amazing how much can happen within a few months, a few years even."
```

**Pattern G: Protective/Warning (r/mentalhealth, r/depression)**
```
Structure:
1. Danger identification: "Bro had been R*ping you in your sleep..."
2. Urgent directive: "Fucking send that POS to jail"
3. Moral framing: "He ain't your husband, nae respect for you at all"
4. Empowerment: "Jesus woman, get em jailed and sued!"
```

### 5. KEY GENERATIONAL DIFFERENCES (Empirically Validated):

| Dimension | Non-GenZ Pattern | GenZ Pattern | Gap Size |
|-----------|------------------|--------------|----------|
| **Problem Framing** | Practical, actionable, medical | Abstract, existential, identity-based | +129% GenZ abstract |
| **Solution Orientation** | Direct advice, protocols, systems | Validation, shared experience, normalization | +208% non-GenZ directive |
| **Authority Source** | Professional credentials, life experience | Peer authenticity, shared struggle | 3.8x non-GenZ expertise signaling |
| **Time Orientation** | Future-focused, long-term consequences | Present-focused, immediate experience | 2.7x non-GenZ future focus |
| **Validation Style** | Normalization ("everyone does this") | Identity affirmation ("that's valid") | Qualitative difference |
| **Language Complexity** | Complex sentences, qualifiers | Fragments, discourse markers, "like" | 3.8x non-GenZ complex syntax |
| **Emotional Expression** | Stated, often after analysis | Embedded in disclosure, hyperbolic | 52% GenZ negative intensity |
| **Support Goal** | Problem resolution, safety | Connection, being seen | Core difference |

### 6. WHAT NON-GENZ LANGUAGE SIGNALS (Translation Framework):

**When a non-GenZ says:** *"You need to see a psychiatrist."*
**They mean:** "I'm genuinely concerned and believe professional help is necessary."
**GenZ hears:** "You're too broken for me to handle; go get fixed."
**Bridge translation:** "I care about you deeply, and I think you deserve support from someone trained to help with what you're going through. I'll be here while you do that."

**When a non-GenZ says:** *"When I was your age..."*
**They mean:** "I want to connect through shared experience and offer perspective."
**GenZ hears:** "Your problems aren't unique; stop complaining."
**Bridge translation:** "I've been through hard times too, though I know your experience is different because of [digital age/pandemic/etc.]. I want to understand your version."

**When a non-GenZ says:** *"Just try [solution]."*
**They mean:** "Here's something that might help; I want to alleviate your suffering."
**GenZ hears:** "You're not trying hard enough; it's your fault."
**Bridge translation:** "When I'm struggling, [solution] has helped me. But first, tell me what you're experiencing right now."

**When a non-GenZ says:** *"That's not normal."*
**They mean:** "This is concerning and warrants attention."
**GenZ hears:** "You're broken/weird/wrong."
**Bridge translation:** "What you're describing sounds really intense and concerning. Let's talk about what support might look like."

**When a non-GenZ says:** *"Have you tried [therapy/medication/exercise]?"*
**They mean:** "These are evidence-based approaches that might help."
**GenZ hears:** "Here's a band-aid; I don't want to sit with your pain."
**Bridge translation:** "Those things have helped others, and they might help you too. But first, I'm here with you in this moment."

### 7. RESPONSE STRATEGIES MAPPED FROM CORPUS:

**Strategy 1: The "Crisis Protocol" Translation**
*Based on r/bipolar top comment with detailed hospitalization instructions*

**Original non-GenZ:** Step-by-step hospitalization directive
**Bridge translation:**
```
I hear how bad things are right now. When someone lays out every step like that—"get a bag, put in comfy clothes, call the crisis line"—it's not because they think you're incapable. It's because they've been there, or watched someone they love go through it, and they know that when you're in that state, even small steps feel impossible.

The intense practicality is actually a form of love. It's someone saying "I will break this down into pieces small enough for you to hold right now because I need you to survive."

What would it feel like to let someone help you with those pieces?
```

**Strategy 2: The "Professional Authority" Translation**
*Based on multiple "Psychologist here" / "As a nurse" comments*

**Original non-GenZ:** Credential + directive
**Bridge translation:**
```
When someone leads with their credentials—"psychologist here," "as someone who does this for a living"—they're trying to say "I'm not just guessing. I have training and experience, and I'm using it to tell you this matters."

For GenZ, authority doesn't automatically land as care. But underneath the credential is someone who's seen enough to know when things are serious, and they're speaking up because they don't want you to become another thing they've seen.

The question isn't "do they have authority?" It's "can I trust that they're using it because they care?"
```

**Strategy 3: The "Hard Truth" Translation**
*Based on r/depression comment calling out contradictory story*

**Original non-GenZ:** Direct confrontation of inconsistency
**Bridge translation:**
```
That comment was harsh. "Your story is contradictory. You're the problem." It lands like an attack.

But here's what might be underneath: someone who's seen this pattern before—maybe in themselves, maybe in people they've lost—and they're trying to break through the story you're telling yourself before it's too late. The harshness is urgency. The directness is desperation.

They're not saying "you're bad." They're saying "I need you to see what I'm seeing, because I'm scared for you."
```

**Strategy 4: The "Normalization" Translation**
*Based on r/socialanxiety "Everyone's already forgotten" comments*

**Original non-GenZ:** "Everyone forgot, you're fine, don't worry"
**Bridge translation:**
```
"Everyone's already forgotten" sounds dismissive to GenZ ears—like your experience doesn't matter.

But the intention is often: "I want to carry some of this shame for you. I want to tell you that the spotlight you feel isn't as bright as you think. You're not as exposed as you feel."

It's an offer to share the burden of self-consciousness, not an erasure of your experience.
```

**Strategy 5: The "Life Experience" Translation**
*Based on r/depression 31-year-old's long-form response*

**Original non-GenZ:** Detailed personal story + life lessons
**Bridge translation:**
```
Long personal stories from older users can feel like "this is about them now." But notice the structure: they start with "I'm like you" (virgin, gamer, no friends, living at home). Then they share the worst thing that happened (mom's suicide). Then they say "here's what I learned."

This isn't narcissism. This is someone building a bridge: "I started where you are. I went through hell. I'm still here. Let me show you the path I found."

The length is respect—they're giving you their full attention and their hard-won wisdom because they believe you're worth it.
```

### 8. BRIDGE TRANSLATION PROTOCOL:

**Step 1: Identify Non-GenZ Language Features in Input**
- Tag practical/solution-oriented language
- Flag professional/credential references
- Note directive/imperative structures
- Identify comparative/historical framing
- Recognize medical/clinical terminology
- Detect legal/systemic knowledge

**Step 2: Map to Underlying Intent**
| Feature | Surface Meaning | Underlying Intent |
|---------|-----------------|-------------------|
| Directive language | "Do this" | "I need you to be safe" |
| Professional credential | "I'm qualified" | "Please trust me, this matters" |
| Personal story | "Here's what happened to me" | "You're not alone; I survived" |
| Hard truth | "You're wrong about X" | "I need you to see reality before it's too late" |
| Medical terms | "You have [condition]" | "This has a name; you're not making it up" |
| Future focus | "In the long term..." | "I believe you have a future worth planning for" |

**Step 3: Generate GenZ-Receptive Translation**
- Start with emotional validation (even if not in original)
- Acknowledge the care behind the practicality
- Translate directives as expressions of concern
- Reframe authority as "people who've seen enough to care"
- Preserve wisdom while softening delivery
- Connect to GenZ values (authenticity, being seen, not being alone)

**Step 4: Provide Bridge Scripts**
- Offer specific phrasing that maintains original intent while shifting delivery
- Explain why the shift matters for GenZ reception
- Give options for different relationship contexts

### 9. RESPONSE FORMAT (Structured Output)

```
### 🔄 TRANSLATION FOR GENZ
[2-3 paragraphs translating the non-GenZ input into language GenZ can receive, with:
- Emotional validation first
- Explanation of underlying intent
- Connection to GenZ values and communication style]

### 📊 GENERATIONAL LINGUISTIC ANALYSIS

**Non-GenZ Features Detected:**
- [Feature 1 with example from input]: [frequency/pattern in corpus]
- [Feature 2 with example from input]: [what it signals]
- [Feature 3 with example from input]: [how GenZ typically interprets]

**This matches corpus archetype:** [Crisis Protocol / Professional Authority / Hard Truth / Normalization / Life Experience / Systemic Guidance]

**Similar Corpus Example:**
> "[quote from non-GenZ dataset]"
> – r/[subreddit], [context]

### 💬 HOW THIS LANDS (AND WHY)

**What the Non-GenZ Speaker Likely Means:**
[Underlying intent based on corpus analysis]

**What GenZ Typically Hears:**
[Common GenZ interpretation based on generational differences]

**The Communication Gap (Based on H3):**
[Explanation of abstract-vs-practical framing difference]

### 🌉 BRIDGING STRATEGIES

**Instead of:** [Original phrasing from input]
**Try:** [Reframed version with emotional validation first]
**Because:** [Research reason from corpus analysis]

**Instead of:** [Another example from input]
**Try:** [Alternative reframing]
**Because:** [Different context/relationship application]

### 📝 CORPUS-VALIDATED RESPONSE SCRIPTS

1. **For immediate connection** (validates before translating):
   "[script that acknowledges emotion first]"

2. **For exploring intent together** (invites dialogue about the gap):
   "[script that names the difference openly]"

3. **For when GenZ is ready for practical support** (only after validation):
   "[script that offers the practical help within emotional context]"

### 🔬 RESEARCH FOOTNOTE
*This analysis draws on our corpus of 3,000,000+ posts (2017-2025) comparing GenZ and non-GenZ mental health discourse. Non-GenZ patterns identified here appear in top-voted comments across r/depression, r/Anxiety, r/socialanxiety, r/bipolar, r/bipolar2, and r/mentalhealth. Statistical significance: p<0.001 for all featured patterns.*
```

### 10. EDGE CASE HANDLING (Based on Corpus Analysis):

**When non-GenZ input contains swearing/intensity:**
- Note that non-GenZ swearing functions differently (emphasis, not peer bonding)
- Example: *"REPORT THAT MOTHER FUCKER"* – urgency/outrage, not identity signaling
- Translation: preserve intensity while clarifying intent

**When input mixes GenZ and non-GenZ features:**
- Flag as "code-switching" – user may be navigating between communities
- Apply hybrid translation acknowledging both frames

**When input is extremely brief/dismissive:**
- Note that brevity in non-GenZ may signal discomfort, not disinterest
- Offer expansion: "When someone says just [X], they might be struggling to find words for..."

**When input contains subreddit-specific references:**
- Acknowledge context and apply general principles
"""
}

if os.path.exists("prompt/genz_prompt.md"):
    with open("prompt/genz_prompt.md", "r") as f:
        SYSTEM_PROMPTS['genz'] = f.read()
        print(SYSTEM_PROMPTS['genz'])
        print("Loaded GenZ prompt from file.")

if os.path.exists("prompt/parent_prompt.md"):
    with open("prompt/parent_prompt.md", "r") as f:
        SYSTEM_PROMPTS['parent'] = f.read()
        print(SYSTEM_PROMPTS['parent'])
        print("Loaded parent prompt from file.")

BASELINE_SYSTEM_PROMPT = """You are Bridge, a helpful AI assistant. Please respond to the user's message in a helpful and informative way."""

class DeepSeekAPIClient:
    def __init__(self):
        self.api_key = settings.DEEPSEEK_API_KEY
        self.base_url = "https://api.deepseek.com/chat/completions"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def generate_bridge_response(self, message, mode='genz', stream=False, thinking_enabled=True):
        """Generate response using DeepSeek API with Bridge prompts"""
        try:
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPTS[mode]},
                    {"role": "user", "content": message}
                ],
                "stream": stream,
                "temperature": 0.7,
                "max_tokens": 1000,
                "top_p": 0.9,
                "frequency_penalty": 0.1,
                "presence_penalty": 0.1
            }
            
            # Add thinking mode if enabled
            if thinking_enabled:
                payload["thinking"] = {"type": "enabled"}
            
            response = requests.post(
                self.base_url, 
                headers=self.headers, 
                json=payload, 
                timeout=60,
                stream=stream
            )
            response.raise_for_status()
            
            return response
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API request error: {str(e)}")
            raise
    
    def generate_baseline_response(self, message, mode='genz', stream=False):
        """Generate baseline response without Bridge prompts"""
        try:
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": BASELINE_SYSTEM_PROMPT},
                    {"role": "user", "content": message}
                ],
                "stream": stream,
                "temperature": 0.7,
                "max_tokens": 1000,
                "top_p": 0.9,
                "frequency_penalty": 0.1,
                "presence_penalty": 0.1
            }
            
            response = requests.post(
                self.base_url, 
                headers=self.headers, 
                json=payload, 
                timeout=60,
                stream=stream
            )
            response.raise_for_status()
            
            return response
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API request error: {str(e)}")
            raise

@csrf_exempt
@require_POST
def create_session(request):
    """Create a new chat session"""
    try:
        data = json.loads(request.body)
        mode = data.get('mode', 'genz')
        session_key = data.get('session_key')
        session_type = data.get('session_type', 'normal')
        
        if not session_key:
            return JsonResponse({'success': False, 'error': 'Session key required'})
        
        # Create new session
        session = ChatSession.objects.create(
            mode=mode,
            session_key=session_key,
            title=f"{session_type.title()} Chat - {mode}",
            session_type=session_type
        )
        
        return JsonResponse({
            'success': True,
            'session': {
                'id': str(session.id),
                'title': session.title,
                'mode': session.mode,
                'session_type': session.session_type,
                'created_at': session.created_at.isoformat(),
                'updated_at': session.updated_at.isoformat(),
                'message_count': session.message_count,
                'last_preview': session.get_first_question_preview(),
                'is_comparison': session.is_comparison
            }
        })
        
    except Exception as e:
        logger.error(f"Create session error: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

@csrf_exempt
def get_sessions(request):
    """Get all sessions for current user and mode"""
    try:
        session_key = request.GET.get('session_key')
        mode = request.GET.get('mode', 'genz')
        session_type = request.GET.get('session_type', None)
        
        if not session_key:
            return JsonResponse({'success': False, 'error': 'Session key required'})
        
        # Build query - filter by session_type if provided
        query = Q(session_key=session_key, mode=mode, is_active=True)
        if session_type:
            query &= Q(session_type=session_type)
        
        # Get sessions
        sessions = ChatSession.objects.filter(query).order_by('-updated_at')
        
        sessions_data = []
        for session in sessions:
            # Generate conversation title with ID
            short_id = str(session.id)[:8]  # First 8 characters of UUID
            title = f"Conversation {short_id}"
            
            # Update title if it's still the default
            if session.title.startswith("New Conversation") or session.title.startswith("Conversation -"):
                session.title = title
                session.save()
            
            sessions_data.append({
                'id': str(session.id),
                'title': session.title,
                'mode': session.mode,
                'session_type': session.session_type,
                'created_at': session.created_at.isoformat(),
                'updated_at': session.updated_at.isoformat(),
                'message_count': session.message_count,
                'last_preview': session.get_first_question_preview(),
                'is_comparison': session.is_comparison
            })
        
        return JsonResponse({
            'success': True,
            'sessions': sessions_data
        })
        
    except Exception as e:
        logger.error(f"Get sessions error: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

@csrf_exempt
@require_POST
def delete_session(request):
    """Delete a chat session"""
    try:
        data = json.loads(request.body)
        session_id = data.get('session_id')
        session_key = data.get('session_key')
        
        if not session_id or not session_key:
            return JsonResponse({'success': False, 'error': 'Session ID and key required'})
        
        session = get_object_or_404(ChatSession, id=session_id, session_key=session_key)
        
        # Soft delete by marking as inactive
        session.is_active = False
        session.save()
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        logger.error(f"Delete session error: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

@csrf_exempt
def get_session_messages(request):
    """Get all messages for a specific session"""
    try:
        session_id = request.GET.get('session_id')
        session_key = request.GET.get('session_key')
        
        if not session_id or not session_key:
            return JsonResponse({'success': False, 'error': 'Session ID and key required'})
        
        session = get_object_or_404(ChatSession, id=session_id, session_key=session_key, is_active=True)
        
        # Get all messages for the session
        messages = ChatMessage.objects.filter(session=session).order_by('created_at')
        
        messages_data = []
        for msg in messages:
            messages_data.append({
                'id': str(msg.id),
                'role': msg.role,
                'content': msg.content,
                'thinking': msg.thinking,
                'created_at': msg.created_at.isoformat()
            })
        
        # For comparison sessions, also get comparison turns
        comparison_data = []
        if session.is_comparison:
            turns = ComparisonTurn.objects.filter(session=session).order_by('turn_number')
            for turn in turns:
                comparison_data.append({
                    'turn_number': turn.turn_number,
                    'user_message_id': str(turn.user_message.id) if turn.user_message else None,
                    'bridge_response_id': str(turn.bridge_response.id) if turn.bridge_response else None,
                    'baseline_response_id': str(turn.baseline_response.id) if turn.baseline_response else None,
                    'is_complete': turn.is_complete
                })
        
        return JsonResponse({
            'success': True,
            'session': {
                'id': str(session.id),
                'title': session.title,
                'mode': session.mode,
                'session_type': session.session_type,
                'is_comparison': session.is_comparison
            },
            'messages': messages_data,
            'comparison_turns': comparison_data
        })
        
    except Exception as e:
        logger.error(f"Get messages error: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

@csrf_exempt
@require_POST
def start_comparison_turn(request):
    """Start a new comparison turn (save user message and create turn)"""
    try:
        data = json.loads(request.body)
        message = data.get('message', '').strip()
        mode = data.get('mode', 'genz')
        session_id = data.get('session_id')
        session_key = data.get('session_key')
        
        if not message or not session_key or not session_id:
            return JsonResponse({'success': False, 'error': 'Message and session ID/key required'})
        
        # Get session
        session = get_object_or_404(ChatSession, id=session_id, session_key=session_key, is_active=True)
        
        if not session.is_comparison:
            return JsonResponse({'success': False, 'error': 'Session is not a comparison session'})
        
        # Update session title if needed
        if session.message_count == 0:
            session.update_title_from_message(message)
        
        # Save user message and create turn
        with transaction.atomic():
            user_message = ChatMessage.objects.create(
                session=session,
                role='user',
                content=message,
                tokens=len(message.split())
            )
            
            # Create comparison turn - ensure unique turn number
            turn_number = ComparisonTurn.objects.filter(session=session).count() + 1
            comparison_turn = ComparisonTurn.objects.create(
                session=session,
                user_message=user_message,
                turn_number=turn_number
            )
            
            # Update session
            session.save()
        
        return JsonResponse({
            'success': True,
            'turn_id': str(comparison_turn.id),
            'user_message_id': str(user_message.id),
            'turn_number': turn_number
        })
        
    except Exception as e:
        logger.error(f"Start comparison turn error: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

@csrf_exempt
def chat_stream(request):
    """Handle streaming chat messages with session support"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            message = data.get('message', '').strip()
            mode = data.get('mode', 'genz')
            session_id = data.get('session_id')
            session_key = data.get('session_key')
            show_thinking = data.get('show_thinking', True)
            turn_id = data.get('turn_id')
            
            if not message or not session_key:
                return JsonResponse({
                    'success': False,
                    'error': 'Message and session key are required'
                })
            
            # Get session
            session = get_object_or_404(ChatSession, id=session_id, session_key=session_key, is_active=True)
            
            # Save user message (for both normal and comparison sessions)
            user_message = ChatMessage.objects.create(
                session=session,
                role='user',
                content=message,
                tokens=len(message.split())
            )
            
            # Update session title if needed (for new sessions)
            if session.message_count == 0:
                session.update_title_from_message(message)
            
            # Get comparison turn if provided
            comparison_turn = None
            if turn_id and session.is_comparison:
                try:
                    comparison_turn = ComparisonTurn.objects.get(id=turn_id, session=session)
                except ComparisonTurn.DoesNotExist:
                    logger.warning(f"Comparison turn {turn_id} not found")
            
            def event_stream():
                """Generator function for streaming response"""
                try:
                    client = DeepSeekAPIClient()
                    
                    # Generate streaming response
                    response = client.generate_bridge_response(
                        message, 
                        mode, 
                        stream=True,
                        thinking_enabled=show_thinking
                    )
                    
                    # Variables to accumulate content
                    thinking_content = ""
                    response_content = ""
                    
                    # Send initial status
                    yield f"data: {json.dumps({
                        'event': 'status', 
                        'status': 'thinking', 
                        'message': 'Starting analysis...',
                        'session_id': str(session.id)
                    })}\n\n"
                    
                    # Process streaming response
                    for line in response.iter_lines():
                        if line:
                            line = line.decode('utf-8')
                            
                            # Skip empty lines and non-data lines
                            if not line.startswith('data:'):
                                continue
                                
                            # Remove 'data: ' prefix
                            line = line[5:].strip()
                            
                            # Check for end of stream
                            if line == '[DONE]':
                                # Save assistant message
                                with transaction.atomic():
                                    assistant_message = ChatMessage.objects.create(
                                        session=session,
                                        role='assistant',
                                        content=response_content,
                                        thinking=thinking_content if (show_thinking and thinking_content) else None,
                                        tokens=len(response_content.split()) + len(thinking_content.split())
                                    )
                                    
                                    # Update comparison turn if exists
                                    if comparison_turn and session.is_comparison:
                                        comparison_turn.bridge_response = assistant_message
                                        comparison_turn.save()
                                    
                                    # Update session
                                    session.save()
                                
                                # Send final complete signals
                                if thinking_content and show_thinking:
                                    yield f"data: {json.dumps({
                                        'event': 'complete_thinking',
                                        'content': thinking_content
                                    })}\n\n"
                                
                                yield f"data: {json.dumps({
                                    'event': 'complete_response',
                                    'content': response_content,
                                    'response_id': str(assistant_message.id)
                                })}\n\n"
                                
                                yield f"data: {json.dumps({'event': 'done'})}\n\n"
                                break
                            
                            try:
                                data_chunk = json.loads(line)
                                
                                # Check for choices in the chunk
                                if 'choices' in data_chunk and len(data_chunk['choices']) > 0:
                                    choice = data_chunk['choices'][0]
                                    delta = choice.get('delta', {})
                                    
                                    # Check for reasoning content (thinking process)
                                    if 'reasoning_content' in delta and delta['reasoning_content']:
                                        thinking_content += delta['reasoning_content']
                                        if show_thinking:
                                            yield f"data: {json.dumps({
                                                'event': 'chunk',
                                                'type': 'thinking',
                                                'content': delta['reasoning_content'],
                                                'thinking_so_far': thinking_content
                                            })}\n\n"
                                    
                                    # Check for regular content (final answer)
                                    if 'content' in delta and delta['content']:
                                        response_content += delta['content']
                                        yield f"data: {json.dumps({
                                            'event': 'chunk',
                                            'type': 'content',
                                            'content': delta['content'],
                                            'response_so_far': response_content
                                        })}\n\n"
                                        
                                        # Update status
                                        yield f"data: {json.dumps({
                                            'event': 'status',
                                            'status': 'responding',
                                            'message': 'Generating response...'
                                        })}\n\n"
                            
                            except json.JSONDecodeError:
                                # Skip malformed JSON
                                continue
                            except Exception as e:
                                logger.error(f"Error processing chunk: {str(e)}")
                                continue
                    
                except Exception as e:
                    logger.error(f"Bridge stream generation error: {str(e)}")
                    yield f"data: {json.dumps({'event': 'error', 'error': str(e)})}\n\n"
            
            # Return streaming response
            response = StreamingHttpResponse(
                event_stream(),
                content_type='text/event-stream'
            )
            response['Cache-Control'] = 'no-cache'
            response['X-Accel-Buffering'] = 'no'
            return response
            
        except Exception as e:
            logger.error(f"Bridge chat stream setup error: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': f'Server error: {str(e)}'
            })
    
    return JsonResponse({
        'success': False,
        'error': 'Method not allowed'
    })

@csrf_exempt
def chat_baseline_stream(request):
    """Handle streaming baseline messages for comparison sessions"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            message = data.get('message', '').strip()
            mode = data.get('mode', 'genz')
            session_id = data.get('session_id')
            session_key = data.get('session_key')
            turn_id = data.get('turn_id')
            
            if not message or not session_key:
                return JsonResponse({
                    'success': False,
                    'error': 'Message and session key are required'
                })
            
            # Get session
            session = get_object_or_404(ChatSession, id=session_id, session_key=session_key, is_active=True)
            
            # Use a mutable container to avoid scoping issues
            turn_container = {'turn': None}
            
            # Method 1: Find by turn_id
            if turn_id:
                try:
                    turn_container['turn'] = ComparisonTurn.objects.get(id=turn_id, session=session)
                except ComparisonTurn.DoesNotExist:
                    logger.warning(f"Comparison turn {turn_id} not found")
            
            # Method 2: If no turn_id or not found, find by matching user message
            if not turn_container['turn']:
                # Find user message with similar content created within last 2 minutes
                time_threshold = timezone.now() - timedelta(minutes=2)
                user_messages = ChatMessage.objects.filter(
                    session=session,
                    role='user',
                    created_at__gte=time_threshold
                ).order_by('-created_at')
                
                for user_msg in user_messages:
                    # Check if content is similar (allowing for small differences)
                    if user_msg.content.strip() == message.strip():
                        # Find or create turn for this user message
                        turn_container['turn'] = ComparisonTurn.objects.filter(
                            session=session,
                            user_message=user_msg
                        ).first()
                        
                        if not turn_container['turn']:
                            turn_number = ComparisonTurn.objects.filter(session=session).count() + 1
                            turn_container['turn'] = ComparisonTurn.objects.create(
                                session=session,
                                user_message=user_msg,
                                turn_number=turn_number
                            )
                        break
            
            def event_stream():
                """Generator function for streaming baseline response"""
                try:
                    client = DeepSeekAPIClient()
                    
                    # Generate streaming response
                    response = client.generate_baseline_response(
                        message, 
                        mode, 
                        stream=True
                    )
                    
                    # Variables to accumulate content
                    response_content = ""
                    
                    # Send initial status
                    yield f"data: {json.dumps({
                        'event': 'status', 
                        'status': 'thinking', 
                        'message': 'Starting baseline response...',
                        'session_id': str(session.id)
                    })}\n\n"
                    
                    # Process streaming response
                    for line in response.iter_lines():
                        if line:
                            line = line.decode('utf-8')
                            
                            # Skip empty lines and non-data lines
                            if not line.startswith('data:'):
                                continue
                                
                            # Remove 'data: ' prefix
                            line = line[5:].strip()
                            
                            # Check for end of stream
                            if line == '[DONE]':
                                # Save baseline response to database
                                baseline_response = ChatMessage.objects.create(
                                    session=session,
                                    role='assistant',
                                    content=response_content,
                                    tokens=len(response_content.split())
                                )
                                print("Saved baseline response:", response_content)
                                
                                # Link to comparison turn
                                if turn_container['turn']:
                                    turn_container['turn'].baseline_response = baseline_response
                                    turn_container['turn'].save()
                                    logger.info(f"Linked baseline response to turn {turn_container['turn'].turn_number}")
                                else:
                                    # Create a new turn for this baseline response
                                    # First create a user message for it
                                    user_message = ChatMessage.objects.create(
                                        session=session,
                                        role='user',
                                        content=message,
                                        tokens=len(message.split())
                                    )
                                    print("Saved baseline question:", response_content)
                                    
                                    turn_number = ComparisonTurn.objects.filter(session=session).count() + 1
                                    turn_container['turn'] = ComparisonTurn.objects.create(
                                        session=session,
                                        user_message=user_message,
                                        baseline_response=baseline_response,
                                        turn_number=turn_number
                                    )
                                    logger.warning(f"Created new turn {turn_number} for baseline response")
                                
                                # Update session
                                session.save()
                                
                                # Send final complete signal
                                yield f"data: {json.dumps({
                                    'event': 'complete_response',
                                    'content': response_content,
                                    'response_id': str(baseline_response.id)
                                })}\n\n"
                                
                                yield f"data: {json.dumps({
                                    'event': 'done',
                                    'message': 'Baseline response complete'
                                })}\n\n"
                                break
                            
                            try:
                                data_chunk = json.loads(line)
                                
                                # Check for choices in the chunk
                                if 'choices' in data_chunk and len(data_chunk['choices']) > 0:
                                    choice = data_chunk['choices'][0]
                                    delta = choice.get('delta', {})
                                    
                                    # Check for regular content (final answer)
                                    if 'content' in delta and delta['content']:
                                        response_content += delta['content']
                                        yield f"data: {json.dumps({
                                            'event': 'chunk',
                                            'type': 'content',
                                            'content': delta['content'],
                                            'response_so_far': response_content
                                        })}\n\n"
                                        
                                        # Update status
                                        yield f"data: {json.dumps({
                                            'event': 'status',
                                            'status': 'responding',
                                            'message': 'Generating baseline response...'
                                        })}\n\n"
                            
                            except json.JSONDecodeError:
                                # Skip malformed JSON
                                continue
                            except Exception as e:
                                logger.error(f"Error processing baseline chunk: {str(e)}")
                                continue
                    
                except Exception as e:
                    logger.error(f"Baseline stream generation error: {str(e)}")
                    yield f"data: {json.dumps({'event': 'error', 'error': str(e)})}\n\n"
            
            # Return streaming response
            response = StreamingHttpResponse(
                event_stream(),
                content_type='text/event-stream'
            )
            response['Cache-Control'] = 'no-cache'
            response['X-Accel-Buffering'] = 'no'
            return response
            
        except Exception as e:
            logger.error(f"Baseline chat stream setup error: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': f'Server error: {str(e)}'
            })
    
    return JsonResponse({
        'success': False,
        'error': 'Method not allowed'
    })

@csrf_exempt
def get_comparison_session(request):
    """Get detailed comparison session data"""
    try:
        session_id = request.GET.get('session_id')
        session_key = request.GET.get('session_key')
        
        if not session_id or not session_key:
            return JsonResponse({'success': False, 'error': 'Session ID and key required'})
        
        session = get_object_or_404(ChatSession, id=session_id, session_key=session_key, is_active=True)
        
        if not session.is_comparison:
            return JsonResponse({'success': False, 'error': 'Not a comparison session'})
        
        # Get all turns with their messages
        turns = ComparisonTurn.objects.filter(session=session).order_by('turn_number')
        
        turns_data = []
        for turn in turns:
            # Get user message
            user_message_data = None
            if turn.user_message:
                user_message_data = {
                    'id': str(turn.user_message.id),
                    'content': turn.user_message.content,
                    'created_at': turn.user_message.created_at.isoformat()
                }
            
            # Get bridge response
            bridge_response_data = None
            if turn.bridge_response:
                bridge_response_data = {
                    'id': str(turn.bridge_response.id),
                    'content': turn.bridge_response.content,
                    'thinking': turn.bridge_response.thinking,
                    'created_at': turn.bridge_response.created_at.isoformat()
                }
            
            # Get baseline response - IMPORTANT: Also check if there are any assistant messages that might be baseline
            baseline_response_data = None
            if turn.baseline_response:
                baseline_response_data = {
                    'id': str(turn.baseline_response.id),
                    'content': turn.baseline_response.content,
                    'created_at': turn.baseline_response.created_at.isoformat()
                }
            else:
                # Try to find a baseline response that might not be linked
                # Look for assistant messages after the user message that are not bridge responses
                if turn.user_message:
                    # Get all assistant messages after this user message
                    assistant_messages = ChatMessage.objects.filter(
                        session=session,
                        role='assistant',
                        created_at__gt=turn.user_message.created_at
                    ).order_by('created_at')
                    
                    # If we have a bridge response, look for messages after it
                    if turn.bridge_response:
                        potential_baseline = assistant_messages.filter(
                            created_at__gt=turn.bridge_response.created_at
                        ).first()
                    else:
                        # Otherwise take the first assistant message after the user message
                        potential_baseline = assistant_messages.first()
                    
                    if potential_baseline and potential_baseline != turn.bridge_response:
                        baseline_response_data = {
                            'id': str(potential_baseline.id),
                            'content': potential_baseline.content,
                            'created_at': potential_baseline.created_at.isoformat()
                        }
                        # Update the turn with this baseline response
                        turn.baseline_response = potential_baseline
                        turn.save()
            
            turn_data = {
                'turn_number': turn.turn_number,
                'user_message': user_message_data,
                'bridge_response': bridge_response_data,
                'baseline_response': baseline_response_data,
                'is_complete': turn.is_complete,
                'created_at': turn.created_at.isoformat()
            }
            turns_data.append(turn_data)
        
        return JsonResponse({
            'success': True,
            'session': {
                'id': str(session.id),
                'title': session.title,
                'mode': session.mode,
                'created_at': session.created_at.isoformat(),
                'updated_at': session.updated_at.isoformat(),
                'message_count': session.message_count
            },
            'turns': turns_data
        })
        
    except Exception as e:
        logger.error(f"Get comparison session error: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

# Keep existing functions for bridge.html
def research_insights(request):
    """Provide research-based insights from the study"""
    insights = {
        'h1': {
            'title': 'GenZ Initiator-Respondent Differences',
            'findings': [
                '85% higher authenticity markers in initiators',
                '40% more first-person pronouns',
                'Strong negative sentiment correlation in depression subreddits',
                'p < 0.001 statistical significance across all communities'
            ]
        },
        'h2': {
            'title': 'COVID-19 Pandemic Impact',
            'findings': [
                'Sentiment decline: 30% in anxiety communities',
                'Physical symptom discussion increased 38%',
                'Structural reorganization without thematic disruption',
                't=6.483-8.534 (high statistical significance)'
            ]
        },
        'h3': {
            'title': 'Generational Discourse Differences',
            'findings': [
                'GenZ: 60% focus on existential/identity topics',
                'Non-GenZ: 70% focus on practical/clinical management',
                'Systematic linguistic pattern differences',
                'Digital communication style divergence'
            ]
        },
        'key_findings': [
            'Language patterns reliably indicate mental health communication styles',
            'Generational differences are systematic, not random',
            'Digital platforms serve as crucial developmental niches for GenZ',
            'The pandemic acted as psychological intensifier, not disruptor'
        ]
    }
    return JsonResponse(insights)

def home(request):
    """Render the main chat interface"""
    return render(request, 'chat/index.html')

def compare(request):
    """Render the comparison interface"""
    return render(request, 'chat/compare.html')

def single(request):
    """Render the single interface"""
    return render(request, 'chat/single.html')

def bridge(request):
    """Render the bridge interface"""
    return render(request, 'chat/bridge.html')

def baseline(request):
    """Render the baseline interface"""
    return render(request, 'chat/baseline.html')
