import json
import re
import random
import html
import os
import hashlib
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timedelta
import streamlit as st
import streamlit.components.v1 as components

DAY_ROLLOVER_HOUR = 2
HISTORY_FILE = Path("momentum_history.json")
TODAY_TASKS_FILE = Path("today_tasks_state.json")
WORKOUT_PB_FILE = Path("workout_personal_bests.json")
QUOTES_FILE = Path("momentum_quotes.json")

# ElevenLabs secrets belong in Render Environment Variables or .streamlit/secrets.toml.
# Never commit the API key to GitHub.
def runtime_secret(name, fallback=""):
    try:
        return str(st.secrets.get(name, os.getenv(name, fallback))).strip()
    except Exception:
        return str(os.getenv(name, fallback)).strip()


ELEVENLABS_API_KEY = runtime_secret("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = runtime_secret("ELEVENLABS_VOICE_ID")
ELEVENLABS_MODEL_ID = runtime_secret("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
ELEVENLABS_OUTPUT_FORMAT = "mp3_44100_128"

WORK_EXERCISES = [
    {"name": "Jump Rope", "unit": "m", "icon": "⟳"},
    {"name": "Pull-ups", "unit": "reps", "icon": "⇧"},
    {"name": "Chin-ups", "unit": "reps", "icon": "↟"},
    {"name": "Squats", "unit": "reps", "icon": "⇩"},
    {"name": "Leg Raises", "unit": "reps", "icon": "⌃"},
]

DAILY_TASKS = [
    {"display": "Coding", "canonical": "Coding Core Task", "difficulty": "Hard", "xp_by_minutes": {20: 40, 30: 60, 40: 80}},
    {"display": "Spanish", "canonical": "Spanish Review", "difficulty": "Medium", "xp_by_minutes": {20: 30, 30: 45, 40: 60}},
    {"display": "Exercise", "canonical": "Complete Workout", "difficulty": "Hard", "xp_by_minutes": {20: 40, 30: 60, 40: 80}},
    {"display": "Networking", "canonical": "Networking / LinkedIn", "difficulty": "Medium", "xp_by_minutes": {10: 15, 20: 35, 30: 50}},
    {"display": "Reading", "canonical": "Reading", "difficulty": "Easy", "xp_by_minutes": {10: 10, 20: 20, 30: 30}},
]

TASK_LINKS = {"Spanish Review": "https://spanish-flashcards-voice.onrender.com/"}
DURATION_LABELS = {0: "Not logged", 10: "10m", 20: "20m", 30: "30m+", 40: "40m+"}
ENERGY_OPTIONS = ["Low", "Normal"]
LOCATION_OPTIONS = ["Work", "Home"]

# Phase 1: history intelligence imported from the original desktop app.
# These canonical names match the mobile task/history format.
GROWTH_TASKS = [t["canonical"] for t in DAILY_TASKS]

TASK_CATEGORIES = {
    "Complete Workout": "Physical",
    "Coding Core Task": "Career",
    "Networking / LinkedIn": "Career",
    "Spanish Review": "Learning",
    "Reading": "Learning",
}

FALLBACK_QUOTES = {
    "inspiration": [
        {"text": "Focus on recovery. Progress > perfection.", "author": "Momentum", "source": "Original"},
        {"text": "The standard is not a perfect day. The standard is returning.", "author": "Momentum", "source": "Original"},
        {"text": "You do not need the whole mountain. You need the next rep.", "author": "Momentum", "source": "Original"},
    ],
    "early_quit": [
        {"text": "The mission isn't over because motivation left the room.", "author": "Momentum", "source": "Original"},
        {"text": "The standard tonight is not excellence. The standard is keeping the contract.", "author": "Momentum", "source": "Original"},
        {"text": "Rest is earned by completion, not negotiation.", "author": "Momentum", "source": "Original"},
    ],
    "finished": [
        {"text": "Another vote cast for the person you intend to become.", "author": "Momentum", "source": "Original"},
        {"text": "Everything after this point belongs to future you.", "author": "Momentum", "source": "Original"},
        {"text": "The fight is rarely won by the strongest. Usually it is won by the one who remains.", "author": "Momentum", "source": "Original"},
    ],
}


def load_quote_library():
    """Load categorized quotes from momentum_quotes.json with a safe fallback."""
    try:
        if QUOTES_FILE.exists():
            data = json.loads(QUOTES_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cleaned = {}
                for category in ("inspiration", "early_quit", "finished"):
                    entries = data.get(category, [])
                    valid = []
                    for entry in entries if isinstance(entries, list) else []:
                        if isinstance(entry, str) and entry.strip():
                            valid.append({"text": entry.strip(), "author": "", "source": ""})
                        elif isinstance(entry, dict) and str(entry.get("text", "")).strip():
                            valid.append({
                                "text": str(entry.get("text", "")).strip(),
                                "author": str(entry.get("author", "")).strip(),
                                "source": str(entry.get("source", "")).strip(),
                            })
                    cleaned[category] = valid or FALLBACK_QUOTES[category]
                return cleaned
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    return FALLBACK_QUOTES


QUOTE_LIBRARY = load_quote_library()


def format_quote(entry):
    """Format one quote as natural Companion dialogue.

    Attribution stays in the JSON for organization, but the mobile Companion
    keeps the author out of the spoken response so the line feels personal.
    """
    if not entry:
        return "Keep moving."
    return str(entry.get("text", "")).strip() or "Keep moving."


def quote_intro(command_text):
    """Give inspiration requests a small, natural lead-in."""
    low = (command_text or "").lower()
    if "wake me up" in low:
        return "You asked for a push. Take this with you."
    if "don't feel" in low or "dont feel" in low:
        return "Then we keep the standard small and move anyway."
    if "get me going" in low or "motivate" in low or "inspire" in low:
        return "Here's one I think you need tonight."
    return "Here's one worth carrying into the next move."


def compact_quote_memory(text, limit=150):
    """Keep self-references readable when the source quote is a long speech."""
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    first_sentence = re.split(r"(?<=[.!?])\s+", cleaned, maxsplit=1)[0]
    if len(first_sentence) <= limit:
        return first_sentence
    return cleaned[: limit - 1].rstrip() + "…"


def categorized_quote(state, category):
    """Return a non-repeating quote until the selected category is exhausted."""
    pool = list(QUOTE_LIBRARY.get(category) or FALLBACK_QUOTES.get(category) or [])
    if not pool:
        return "Keep moving."

    state.setdefault("quote_history", {})
    used = list(state["quote_history"].get(category, []))
    available = [entry for entry in pool if entry.get("text") not in used]

    if not available:
        used = []
        available = pool

    entry = random.choice(available)
    used.append(entry.get("text", ""))
    state["quote_history"][category] = used
    spoken = format_quote(entry)
    state["last_quote"] = {
        "text": spoken,
        "category": category,
        "shown_at": datetime.now().isoformat(timespec="seconds"),
        "recalled": False,
    }
    save_state(state)
    return spoken

st.set_page_config(page_title="Momentum Mobile", page_icon="⚡", layout="centered")

st.markdown("""
<style>
:root{
  --bg:#000000; --panel:#070b13; --card:#0d1422; --card2:#111b2d;
  --purple:#8b4dff; --purple2:#b55cff; --text:#f7f4ff; --muted:#a9b5ca;
  --line:#24324c; --gold:#ffd84d; --red:#ff4d57; --green:#62f0b2;
}
.stApp{background:var(--bg); color:var(--text);}
.block-container{padding:.55rem .85rem 4.25rem .85rem; max-width:480px;}
[data-testid="stHeader"]{background:rgba(0,0,0,0);}
.hero{border:1px solid var(--purple); border-radius:18px; padding:12px 14px; background:linear-gradient(180deg,#11182a,#05070d); box-shadow:0 0 18px rgba(139,77,255,.18); margin-bottom:9px;}
.logoRow{display:flex; align-items:center; gap:10px;}
.logo{width:42px; height:42px; border-radius:12px; display:flex; align-items:center; justify-content:center; background:#170b2f; color:var(--purple); font-size:28px; font-weight:900;}
.title{font-size:1.16rem; font-weight:900; letter-spacing:.5px; line-height:1.05;}
.sub{color:var(--muted); margin-top:3px; font-size:.82rem;}
.modePill{display:none!important;}
.card{border:1px solid var(--line); border-radius:16px; padding:13px; background:var(--card); margin:8px 0;}
.companion{border:1px solid rgba(139,77,255,.40); border-radius:18px; padding:14px; background:linear-gradient(180deg,#0e1727,#070b13); margin:9px 0;}
.label{color:var(--purple2); font-size:.78rem; font-weight:900; text-transform:uppercase; letter-spacing:.6px; margin-bottom:8px;}
.big{font-size:1.45rem; font-weight:900;}
.muted{color:var(--muted);}
.statGrid{display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px; margin:9px 0;}
.stat{border:1px solid var(--line); background:#07101f; border-radius:14px; padding:8px; text-align:center;}
.stat .n{font-size:1.62rem; font-weight:900; color:var(--gold); line-height:1.05;}
.stat .t{font-size:.72rem; color:var(--muted); font-weight:800;}
.progressWrap{margin:2px 0 14px 0;}
.progressTitle{color:#f7f4ff; font-size:.80rem; font-weight:900; letter-spacing:.35px; margin:0 0 5px 2px;}
.progressMeta{display:flex; justify-content:space-between; gap:10px; color:#a9b5ca; font-size:.76rem; font-weight:800; margin:5px 2px 0 2px;}
.focusCard{
  border:1px solid rgba(139,77,255,.72);
  border-radius:16px;
  padding:12px 13px;
  margin:9px 0 10px 0;
  background:radial-gradient(circle at top right, rgba(139,77,255,.24), transparent 38%), linear-gradient(180deg,#0d1526,#070b13);
  box-shadow:0 0 16px rgba(139,77,255,.12);
  position:relative;
  overflow:hidden;
}
.focusCard.animateMission{
  animation:missionLift .45s ease both;
}
.focusCard.animateMission::after{
  content:"";
  position:absolute;
  inset:-40% auto -40% -35%;
  width:28%;
  transform:skewX(-18deg);
  background:linear-gradient(90deg,transparent,rgba(255,255,255,.11),transparent);
  animation:missionShine 1.15s ease-out 1 both;
  pointer-events:none;
}
@keyframes missionLift{from{opacity:0; transform:translateY(6px)}to{opacity:1; transform:translateY(0)}}
@keyframes missionShine{0%{left:-35%;opacity:0}18%{opacity:1}100%{left:125%;opacity:0}}

.bonusUnlock{
  position:relative;
  overflow:hidden;
  margin:10px 0 12px;
  padding:12px 14px;
  border:1px solid #f3c73f;
  border-radius:15px;
  background:linear-gradient(135deg,rgba(181,92,255,.18),rgba(243,199,63,.08));
  color:#ffe56a;
  text-align:center;
  font-size:.83rem;
  font-weight:950;
  letter-spacing:.65px;
  text-transform:uppercase;
  animation:bonusUnlockPop .75s ease both;
}
.bonusUnlock::after{
  content:"";
  position:absolute;
  top:0;
  bottom:0;
  width:30%;
  left:-35%;
  transform:skewX(-18deg);
  background:linear-gradient(90deg,transparent,rgba(255,255,255,.45),transparent);
  animation:bonusUnlockShine 1.05s ease .08s 1 forwards;
}
@keyframes bonusUnlockPop{
  0%{opacity:0;transform:scale(.94) translateY(5px)}
  65%{opacity:1;transform:scale(1.025) translateY(0)}
  100%{opacity:1;transform:scale(1)}
}
@keyframes bonusUnlockShine{
  0%{left:-35%;opacity:0}
  18%{opacity:1}
  100%{left:125%;opacity:0}
}

.bonusCompleteCard{
  margin:12px 0;
  padding:18px 16px;
  border:1px solid #f3c73f;
  border-radius:18px;
  background:linear-gradient(135deg,rgba(181,92,255,.16),rgba(243,199,63,.07));
  text-align:center;
  animation:bonusCompleteEnter .7s ease both;
}
.bonusCompleteLabel{
  color:#c66cff;
  font-size:.72rem;
  font-weight:950;
  letter-spacing:.8px;
  text-transform:uppercase;
}
.bonusCompleteTitle{
  margin-top:8px;
  color:#ffe56a;
  font-size:1.28rem;
  font-weight:950;
}
.bonusCompleteText{
  margin-top:8px;
  color:#d7def0;
  font-size:.9rem;
  line-height:1.45;
}
.bonusFinalWord{
  margin:12px 0 10px;
  padding:15px 16px;
  border:1px solid #9d45ff;
  border-radius:16px;
  background:#0b1020;
  color:#f4f6fb;
  line-height:1.55;
}
.bonusFinalWord .label{
  color:#c66cff;
  font-size:.72rem;
  font-weight:950;
  letter-spacing:.7px;
  text-transform:uppercase;
  margin-bottom:8px;
}
@keyframes bonusCompleteEnter{
  0%{opacity:0;transform:translateY(7px) scale(.98)}
  100%{opacity:1;transform:translateY(0) scale(1)}
}
.focusLabel{color:#b55cff; font-size:.70rem; font-weight:950; letter-spacing:.65px; text-transform:uppercase;}
.focusMain{display:flex; align-items:center; justify-content:space-between; gap:12px; margin-top:5px;}
.focusTask{color:#ffffff; font-size:1.05rem; font-weight:950;}
.focusTime{color:#dbe7ff; font-size:.82rem; font-weight:800; margin-top:2px;}
.focusReward{color:#ffd84d; font-size:.80rem; font-weight:950; white-space:nowrap;}
.missionBadge{display:inline-flex; align-items:center; gap:5px; margin-top:9px; padding:5px 8px; border-radius:999px; font-size:.69rem; font-weight:950; letter-spacing:.35px; text-transform:uppercase; background:rgba(139,77,255,.18); border:1px solid rgba(181,92,255,.62); color:#fff;}
.missionStart{margin-top:9px; color:#dbe7ff; font-size:.78rem; font-weight:850;}
.missionReason{margin-top:4px; color:#a9b5ca; font-size:.74rem; line-height:1.35;}

.nextMove{border:1px solid var(--purple); border-radius:18px; padding:16px; background:radial-gradient(circle at top right, rgba(139,77,255,.25), transparent 35%), #0b1020; margin:12px 0;}
.nextTitle{font-size:1.7rem; font-weight:900;}
.nextSub{color:var(--muted); margin-top:4px;}
.taskCard{border:1px solid var(--line); border-radius:16px; padding:14px; background:#080d16; margin:10px 0;}
.taskName{font-size:1.1rem; font-weight:900;}
.suggestion button{font-size:.85rem!important;}
.stButton>button{border-radius:14px!important; font-weight:900!important; min-height:44px; background:#111b2d!important; color:#f7f4ff!important; border:1px solid #45618d!important; box-shadow:0 0 10px rgba(139,77,255,.12)!important;}
.stButton>button:hover{border-color:var(--purple)!important; color:#fff!important; background:#18243a!important;}
.stButton>button[kind="primary"]{background:linear-gradient(90deg,#ff4d57,#8b4dff)!important; color:#fff!important; border:0!important;}
.stTextInput>div>div>input{
  background:#f2f4f8!important;
  color:#10131d!important;
  border:2px solid #8b4dff!important;
  border-radius:14px!important;
  min-height:48px;
  font-weight:700!important;
}
.stTextInput>div>div>input::placeholder{color:#6b7280!important; opacity:1!important;}
.stTextInput>div>div>input:focus::placeholder{color:transparent!important;}
.stTextInput>div>div>input:focus{box-shadow:0 0 0 2px rgba(139,77,255,.25)!important;}
.homeShell{border:1px solid rgba(139,77,255,.48); border-radius:18px; padding:12px; background:linear-gradient(180deg,#080d18,#05070d); margin-top:14px; box-shadow:0 0 18px rgba(139,77,255,.10);}
.chatBox{max-height:455px; overflow-y:auto; padding:12px 14px; margin:0 0 8px 0; border:1px solid rgba(139,77,255,.65); border-radius:16px; background:#070b13; box-shadow:0 0 14px rgba(139,77,255,.10);}
.chatMsg{display:block; padding:0; margin:0 0 8px 0; border:0!important; background:transparent!important;}
.chatMsg:last-child{margin-bottom:0;}
.chatMsg.you{border:0!important; background:transparent!important;}
.chatMsg.companion{border:0!important; background:transparent!important;}
.chatWho{display:inline; font-weight:900; margin-right:7px; font-size:.9rem;}
.chatMsg.you .chatWho{color:#9fc0ff;}
.chatMsg.companion .chatWho{color:#b55cff;}
.chatText{display:inline; color:#f1f6ff; line-height:1.5; font-size:1rem;}
.companionQuoteCard{margin-top:12px; padding:15px 16px; border:1px solid rgba(139,77,255,.72); border-radius:15px; background:linear-gradient(180deg,#101326,#080b14); box-shadow:0 0 16px rgba(139,77,255,.13);}
.companionQuoteHead{font-size:.72rem; font-weight:900; letter-spacing:.08em; text-transform:uppercase; color:#b55cff; margin-bottom:8px;}
.companionQuoteText{font-size:.95rem; line-height:1.5; color:#f4f1ff;}
.nextMove{margin-top:12px;}



.closeoutHero{border:1px solid rgba(139,77,255,.75);border-radius:18px;padding:18px 14px;text-align:center;background:radial-gradient(circle at top,rgba(139,77,255,.22),transparent 45%),#0b1020;margin:10px 0;position:relative;overflow:hidden;animation:debriefRise .42s ease both;}
.closeoutHero.missionComplete{border-color:rgba(255,216,77,.78);box-shadow:0 0 20px rgba(255,216,77,.12);}
.closeoutHero.missionComplete::after{content:"";position:absolute;inset:-45% auto -45% -30%;width:24%;transform:skewX(-18deg);background:linear-gradient(90deg,transparent,rgba(255,255,255,.16),transparent);animation:debriefShine 1.15s ease-out .12s 1 both;pointer-events:none;}
.closeoutEyebrow{color:#b55cff;font-size:.72rem;font-weight:950;text-transform:uppercase;letter-spacing:.09em;margin-bottom:7px;}
.closeoutStars{color:#ffd84d;font-size:1.35rem;letter-spacing:.18em;font-weight:900;animation:starsSettle .7s ease .08s both;}
@keyframes debriefRise{from{opacity:0;transform:translateY(7px)}to{opacity:1;transform:translateY(0)}}
@keyframes starsSettle{0%{opacity:0;transform:scale(.88)}65%{opacity:1;transform:scale(1.06)}100%{opacity:1;transform:scale(1)}}
@keyframes debriefShine{0%{left:-30%;opacity:0}20%{opacity:1}100%{left:125%;opacity:0}}
.closeoutStatus{font-size:1.35rem;font-weight:950;margin-top:5px;}
.closeoutScore{color:#c8d5ea;font-size:.85rem;font-weight:800;margin-top:5px;}
.closeoutCompare{color:#62f0b2;font-size:.78rem;font-weight:850;margin-top:8px;}
.closeoutGrid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:10px 0;}
.closeoutMetric{border:1px solid #24324c;border-radius:14px;background:#07101f;padding:10px 5px;text-align:center;}
.closeoutMetric b{display:block;color:#ffd84d;font-size:1.05rem;}
.closeoutMetric span{display:block;color:#a9b5ca;font-size:.68rem;font-weight:800;margin-top:2px;}
.closeoutPanel{border:1px solid #24324c;border-radius:16px;background:#0d1422;padding:14px;margin:10px 0;}
.closeoutChips{display:flex;flex-wrap:wrap;gap:7px;}
.closeoutChip{display:inline-block;border:1px solid rgba(255,216,77,.45);background:rgba(255,216,77,.08);border-radius:999px;padding:6px 9px;color:#f4e5a0;font-size:.73rem;font-weight:800;}
.closeoutGood{color:#62f0b2;font-size:.83rem;font-weight:850;}
.closeoutSectionTitle{font-size:.72rem;font-weight:950;letter-spacing:.07em;text-transform:uppercase;margin-bottom:8px;}
.closeoutSectionTitle.good{color:#62f0b2;}
.closeoutSectionTitle.attention{color:#ffd84d;}
.closeoutList{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:10px;}
.closeoutList:last-child{margin-bottom:0;}
.closeoutTomorrow{font-size:1.05rem;font-weight:950;color:#fff;margin-bottom:3px;}

/* Custom mobile nav */
.mobileNav{display:none!important;
  display:grid;
  grid-template-columns:repeat(3,1fr);
  gap:8px;
  margin:14px 0 6px 0;
}
.mobileNavBottom{display:none!important;
  display:grid;
  grid-template-columns:repeat(2,1fr);
  gap:8px;
  margin:8px 0 14px 0;
}
.navPill{
  border:1px solid #45618d;
  background:#10192a;
  color:#f7f4ff;
  border-radius:14px;
  padding:9px 5px;
  text-align:center;
  font-weight:900;
  font-size:.83rem;
  box-shadow:0 0 10px rgba(139,77,255,.10);
}
.navPill.active{
  background:linear-gradient(90deg,#ff4d57,#8b4dff);
  border-color:transparent;
  color:#ffffff;
  box-shadow:0 0 14px rgba(139,77,255,.35);
}
.navPill.idle{
  color:#dbe7ff;
}

/* Hide Streamlit's default submit-button white styling inside forms */
div[data-testid="stFormSubmitButton"] button{
  width:100%;
  border-radius:14px!important;
  font-weight:900!important;
  min-height:44px!important;
}
div[data-testid="stFormSubmitButton"] button[kind="secondary"]{
  background:#111b2d!important;
  color:#f7f4ff!important;
  border:1px solid #45618d!important;
}
div[data-testid="stFormSubmitButton"] button[kind="secondary"]:hover{
  background:#18243a!important;
  color:#ffffff!important;
  border-color:#8b4dff!important;
}


/* Force all form submit buttons dark except primary Send */
div[data-testid="stForm"] button:not([kind="primary"]){
  background:#111b2d!important;
  color:#f7f4ff!important;
  border:1px solid #45618d!important;
  box-shadow:0 0 10px rgba(139,77,255,.12)!important;
}
div[data-testid="stForm"] button:not([kind="primary"] *){
  color:#f7f4ff!important;
}
div[data-testid="stForm"] button:not([kind="primary"]):hover{
  background:#18243a!important;
  color:#ffffff!important;
  border-color:#8b4dff!important;
}
div[data-testid="stForm"] button:not([kind="primary"]) p{
  color:#f7f4ff!important;
}

.thinkingRow{
  display:flex;
  align-items:center;
  gap:8px;
  color:var(--muted);
  font-size:.88rem;
  margin:2px 0 10px 0;
}
.thinkingDots{display:inline-flex; gap:4px;}
.thinkingDots span{
  width:5px; height:5px; border-radius:50%;
  background:var(--purple2);
  animation:momentumPulse 1s infinite ease-in-out;
}
.thinkingDots span:nth-child(2){animation-delay:.15s;}
.thinkingDots span:nth-child(3){animation-delay:.30s;}
@keyframes momentumPulse{
  0%,80%,100%{opacity:.25; transform:translateY(0);}
  40%{opacity:1; transform:translateY(-2px);}
}
div[data-testid="stForm"] div[data-testid="stFormSubmitButton"]:last-of-type button{
  min-height:38px!important;
  font-size:.82rem!important;
  opacity:.92;
}

.chatMsg.newReply .chatText .word{
  opacity:0;
  display:inline;
  animation:wordReveal .16s ease forwards;
}
@keyframes wordReveal{
  from{opacity:0; filter:blur(1.5px);}
  to{opacity:1; filter:blur(0);}
}

/* ---------- TASKS TAB POLISH ---------- */

/* Energy / Location labels */
div[data-testid="stWidgetLabel"] p{
  color:#dbe7ff!important;
  font-weight:800!important;
  opacity:1!important;
}

/* Segmented controls: readable dark pills */
div[data-testid="stSegmentedControl"]{
  margin-bottom:10px!important;
}

div[data-testid="stSegmentedControl"] button{
  background:#10192a!important;
  color:#f7f4ff!important;
  border:1px solid #45618d!important;
  min-height:42px!important;
  font-weight:800!important;
  box-shadow:0 0 8px rgba(139,77,255,.08)!important;
}

div[data-testid="stSegmentedControl"] button:hover{
  background:#18243a!important;
  color:#ffffff!important;
  border-color:#8b4dff!important;
}

div[data-testid="stSegmentedControl"] button[aria-pressed="true"]{
  background:linear-gradient(90deg,#ff4d57,#8b4dff)!important;
  color:#ffffff!important;
  border-color:transparent!important;
  box-shadow:0 0 14px rgba(139,77,255,.34)!important;
}

div[data-testid="stSegmentedControl"] button p{
  color:inherit!important;
  font-weight:800!important;
}

/* Stronger task cards */
.taskCard{
  border:1px solid #2f4569!important;
  background:linear-gradient(180deg,#0d1524,#080d16)!important;
  padding:15px!important;
  margin:16px 0 8px 0!important;
  box-shadow:0 0 12px rgba(42,86,150,.08)!important;
}

.taskName{
  color:#ffffff!important;
  font-size:1.08rem!important;
}

.taskCard .muted{
  color:#b9c8df!important;
  margin-top:4px!important;
}

/* Radio choices: visible, tappable pills */
div[role="radiogroup"]{
  display:flex!important;
  flex-wrap:wrap!important;
  gap:8px!important;
  margin:2px 0 14px 0!important;
}

div[role="radiogroup"] label{
  background:#0d1422!important;
  border:1px solid #334b73!important;
  border-radius:999px!important;
  padding:7px 11px!important;
  margin:0!important;
  min-height:36px!important;
  display:flex!important;
  align-items:center!important;
  box-shadow:0 0 8px rgba(0,0,0,.16)!important;
}

div[role="radiogroup"] label:hover{
  background:#152138!important;
  border-color:#8b4dff!important;
}

div[role="radiogroup"] label p{
  color:#e7efff!important;
  font-weight:750!important;
  font-size:.88rem!important;
  opacity:1!important;
}

div[role="radiogroup"] label:has(input:checked){
  background:rgba(139,77,255,.24)!important;
  border-color:#a86cff!important;
  box-shadow:0 0 12px rgba(139,77,255,.25)!important;
}

div[role="radiogroup"] label:has(input:checked) p{
  color:#ffffff!important;
  font-weight:900!important;
}

/* Make radio circles easier to see */
div[role="radiogroup"] input[type="radio"]{
  accent-color:#ff4d72!important;
}

/* Spanish app button */
.stLinkButton>a{
  background:#111b2d!important;
  color:#f7f4ff!important;
  border:1px solid #45618d!important;
  border-radius:14px!important;
  min-height:44px!important;
  font-weight:900!important;
  box-shadow:0 0 10px rgba(139,77,255,.10)!important;
}

.stLinkButton>a:hover{
  background:#18243a!important;
  color:#ffffff!important;
  border-color:#8b4dff!important;
  box-shadow:0 0 12px rgba(139,77,255,.22)!important;
}

/* Slightly separate final action row from task controls */
div[data-testid="stHorizontalBlock"]:has(button[kind="primary"]){
  margin-top:8px!important;
}

/* Small-screen spacing */
@media (max-width:480px){
  div[role="radiogroup"] label{
    padding:7px 9px!important;
  }

  div[role="radiogroup"] label p{
    font-size:.84rem!important;
  }
}

/* Energy / Location rebuilt as the same readable pill controls */
.controlLabel{
  color:#dbe7ff;
  font-size:.78rem;
  font-weight:900;
  letter-spacing:.35px;
  margin:10px 0 6px 2px;
}

.taskTopRow{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:10px;
}

.taskAppLink{
  display:inline-flex;
  align-items:center;
  gap:5px;
  padding:6px 9px;
  border-radius:999px;
  background:rgba(139,77,255,.18);
  border:1px solid rgba(139,77,255,.60);
  color:#ffffff!important;
  text-decoration:none!important;
  font-size:.78rem;
  font-weight:900;
  white-space:nowrap;
  box-shadow:0 0 10px rgba(139,77,255,.14);
}

.taskAppLink:hover{
  background:rgba(139,77,255,.30);
  border-color:#b55cff;
  color:#ffffff!important;
}

/* Completed tasks collapse into one compact row with Edit inside */
div[data-testid="stVerticalBlockBorderWrapper"]:has(.completedTaskMarker){
  border:1px solid rgba(98,240,178,.45)!important;
  border-radius:16px!important;
  background:linear-gradient(180deg,rgba(18,49,47,.72),#080f16)!important;
  margin:12px 0 8px 0!important;
  box-shadow:0 0 12px rgba(98,240,178,.08)!important;
}

div[data-testid="stVerticalBlockBorderWrapper"]:has(.completedTaskMarker) > div{
  padding:10px 12px!important;
}

.completedTaskMarker{display:none;}
.completedTaskName{
  color:#ffffff;
  font-size:1rem;
  font-weight:900;
  line-height:1.2;
}
.completedTaskReceipt{
  color:#93f5c9;
  font-size:.82rem;
  font-weight:850;
  white-space:nowrap;
  margin-top:3px;
}

div[data-testid="stVerticalBlockBorderWrapper"]:has(.completedTaskMarker) .stButton>button,
div[data-testid="stVerticalBlockBorderWrapper"]:has(.completedTaskMarker) .stLinkButton>a{
  min-height:36px!important;
  border-radius:999px!important;
  padding:5px 10px!important;
  font-size:.78rem!important;
  margin-top:0!important;
}

/* ---------- DARK WORKOUT DIALOG ---------- */

/* Keep the Exercise task card identical to the other blue task cards */
div[data-testid="stVerticalBlockBorderWrapper"]:has(.exerciseTaskMarker){
  border:1px solid #2f4569!important;
  border-radius:16px!important;
  background:linear-gradient(180deg,#0d1524,#080d16)!important;
  margin:16px 0 8px 0!important;
  box-shadow:0 0 12px rgba(42,86,150,.08)!important;
}

div[data-testid="stVerticalBlockBorderWrapper"]:has(.exerciseTaskMarker) > div{
  padding:13px 14px!important;
}

.exerciseTaskMarker{display:none;}

.exerciseHeaderRow{
  display:flex;
  align-items:center;
  gap:9px;
}

.workoutSavedSummary{
  color:#62f0b2;
  font-size:.74rem;
  font-weight:850;
  margin-top:3px;
}

/* Small Log button shown before Exercise */
div[data-testid="stVerticalBlockBorderWrapper"]:has(.exerciseTaskMarker) .stButton>button,
div[data-testid="stVerticalBlockBorderWrapper"]:has(.completedTaskMarker) button[key*="open_workout"]{
  min-height:34px!important;
  border-radius:999px!important;
  padding:4px 10px!important;
  font-size:.78rem!important;
  background:rgba(139,77,255,.18)!important;
  border:1px solid rgba(181,92,255,.72)!important;
  color:#ffffff!important;
  box-shadow:0 0 10px rgba(139,77,255,.15)!important;
}

div[data-testid="stVerticalBlockBorderWrapper"]:has(.exerciseTaskMarker) .stButton>button:hover{
  background:rgba(139,77,255,.32)!important;
  border-color:#c27aff!important;
}

/* Native Streamlit dialog shell */
div[role="dialog"]{
  background:linear-gradient(180deg,#0c1422,#070b13)!important;
  border:1px solid #6f5bd8!important;
  border-radius:20px!important;
  box-shadow:0 22px 60px rgba(0,0,0,.72), 0 0 24px rgba(139,77,255,.18)!important;
  color:#f7f4ff!important;
}

div[role="dialog"] > div{
  background:transparent!important;
}

div[role="dialog"] [data-testid="stDialogHeader"]{
  background:transparent!important;
  border-bottom:1px solid #263653!important;
}

div[role="dialog"] [data-testid="stDialogHeader"] h2{
  color:#ffffff!important;
  font-weight:950!important;
  letter-spacing:.2px!important;
}

div[role="dialog"] [data-testid="stDialogHeader"] button{
  background:#111b2d!important;
  color:#ffffff!important;
  border:1px solid #45618d!important;
  border-radius:11px!important;
}

.workoutDialogIntro{
  color:#9fb0c8;
  font-size:.82rem;
  margin:-2px 0 10px 0;
}

.workoutDialogLocation{
  color:#b55cff;
  font-size:.78rem;
  font-weight:950;
  letter-spacing:.55px;
  text-transform:uppercase;
  margin-bottom:2px;
}

.workoutGridHeader{
  color:#b978ff;
  font-size:.68rem;
  font-weight:950;
  text-align:center;
  padding:5px 0 3px 0;
  white-space:nowrap;
}

.workoutGridHeader.left{text-align:left;}

.workoutPB{
  color:#ffd84d;
  font-size:.88rem;
  font-weight:950;
  text-align:center;
  padding-top:8px;
  white-space:nowrap;
}

div[role="dialog"] [data-testid="stHorizontalBlock"]{
  gap:.42rem!important;
}

div[role="dialog"] [data-testid="stCheckbox"]{
  margin-top:2px!important;
}

div[role="dialog"] [data-testid="stCheckbox"] label{
  min-height:38px!important;
}

div[role="dialog"] [data-testid="stCheckbox"] p{
  color:#f7f4ff!important;
  font-size:.80rem!important;
  font-weight:850!important;
  white-space:nowrap!important;
}

div[role="dialog"] [data-testid="stNumberInput"]{
  margin-bottom:0!important;
}

div[role="dialog"] [data-testid="stNumberInput"] input{
  min-height:38px!important;
  height:38px!important;
  padding:4px 5px!important;
  text-align:center!important;
  font-size:.84rem!important;
  font-weight:950!important;
  background:#111b2d!important;
  color:#ffffff!important;
  border:1px solid #3b5279!important;
  border-radius:10px!important;
  box-shadow:none!important;
}

div[role="dialog"] [data-testid="stNumberInput"] input:focus{
  border-color:#9b63ff!important;
  box-shadow:0 0 0 2px rgba(139,77,255,.18)!important;
}

div[role="dialog"] [data-testid="stNumberInput"] button{
  display:none!important;
}

div[role="dialog"] .stButton>button[kind="primary"]{
  min-height:44px!important;
  margin-top:8px!important;
}

@media (max-width:480px){
  div[role="dialog"]{
    width:94vw!important;
    max-width:410px!important;
  }

  div[role="dialog"] [data-testid="stCheckbox"] p{
    font-size:.73rem!important;
  }

  .workoutGridHeader{
    font-size:.63rem!important;
  }

  .workoutPB{
    font-size:.80rem!important;
  }
}

/* Reliable Exercise card styling */
.st-key-exercise_task_card{
  border:1px solid #2f4569!important;
  border-radius:16px!important;
  background:linear-gradient(180deg,#0d1524,#080d16)!important;
  margin:16px 0 8px 0!important;
  padding:13px 14px!important;
  box-shadow:0 0 12px rgba(42,86,150,.08)!important;
}

.st-key-exercise_task_card [data-testid="stVerticalBlock"]{
  gap:0!important;
}

.st-key-exercise_task_card .stButton>button{
  min-height:34px!important;
  border-radius:999px!important;
  padding:4px 10px!important;
  font-size:.78rem!important;
  background:rgba(139,77,255,.18)!important;
  border:1px solid rgba(181,92,255,.72)!important;
  color:#ffffff!important;
  box-shadow:0 0 10px rgba(139,77,255,.15)!important;
}

/* Condensed workout dialog */
div[role="dialog"]{
  width:min(92vw, 560px)!important;
  max-width:560px!important;
}

div[role="dialog"] [data-testid="stDialogHeader"]{
  padding-bottom:4px!important;
}

div[role="dialog"] [data-testid="stDialogBody"]{
  padding-top:4px!important;
}

div[role="dialog"] [data-testid="stHorizontalBlock"]{
  gap:.28rem!important;
}

div[role="dialog"] [data-testid="stCheckbox"] label{
  min-height:34px!important;
}

div[role="dialog"] [data-testid="stNumberInput"] input{
  min-height:34px!important;
  height:34px!important;
}

.workoutDialogLocation{
  margin:0 0 2px 0!important;
}

.workoutGridHeader{
  padding:2px 0 2px 0!important;
}

/* ---------- FINAL CRISP WORKOUT TABLE ---------- */

div[role="dialog"]{
  width:min(92vw, 500px)!important;
  max-width:500px!important;
}

div[role="dialog"] [data-testid="stDialogHeader"]{
  padding:10px 14px 4px 14px!important;
}

div[role="dialog"] [data-testid="stDialogBody"]{
  padding:2px 14px 12px 14px!important;
}

/* Pull the exercise name and Set 1 closer together */
div[role="dialog"] [data-testid="stHorizontalBlock"]{
  gap:.18rem!important;
}

/* Compact row rhythm */
div[role="dialog"] [data-testid="stCheckbox"]{
  margin:0!important;
}

div[role="dialog"] [data-testid="stCheckbox"] label{
  min-height:32px!important;
  padding:0!important;
}

div[role="dialog"] [data-testid="stCheckbox"] p{
  font-size:.78rem!important;
  font-weight:850!important;
  letter-spacing:0!important;
}

div[role="dialog"] [data-testid="stNumberInput"] input{
  min-height:32px!important;
  height:32px!important;
  padding:2px 4px!important;
  border-radius:9px!important;
}

.workoutGridHeader{
  font-size:.64rem!important;
  padding:0 0 3px 0!important;
}

.workoutPB{
  font-size:.82rem!important;
  padding-top:6px!important;
}

div[role="dialog"] .stButton>button[kind="primary"]{
  min-height:40px!important;
  margin-top:7px!important;
}

/* Tiny checkboxes, still easy to tap because the label remains tall */
div[role="dialog"] [data-testid="stCheckbox"] input{
  width:14px!important;
  height:14px!important;
}

@media (max-width:480px){
  div[role="dialog"]{
    width:94vw!important;
    max-width:455px!important;
  }

  div[role="dialog"] [data-testid="stCheckbox"] p{
    font-size:.72rem!important;
  }
}


@media (max-width:480px){
  .block-container{padding-top:.4rem!important;}
  .hero{padding:10px 12px!important;margin-bottom:8px!important;}
  .statGrid{margin:8px 0!important;}
  .progressWrap{margin-bottom:10px!important;}
  .focusCard{margin-top:8px!important;margin-bottom:9px!important;}
  .taskCard{margin-top:12px!important;}
  .chatText{font-size:1.01rem!important;}
}

/* ---------- PHASE 3: COMPACT TREND ALERTS ---------- */
.trendSummary{
  border:1px solid rgba(139,77,255,.55); border-radius:16px; padding:13px 14px;
  background:linear-gradient(180deg,#0d1524,#080d16); margin:10px 0 12px 0;
}
.trendSummaryTitle{color:#b55cff; font-size:.72rem; font-weight:950; letter-spacing:.6px; text-transform:uppercase;}
.trendSummaryText{color:#f7f4ff; font-size:.92rem; font-weight:850; margin-top:5px; line-height:1.35;}
.trendCard{
  border:1px solid #2f4569; border-radius:15px; padding:12px 13px; margin:9px 0;
  background:linear-gradient(180deg,#0d1524,#080d16); box-shadow:0 0 10px rgba(42,86,150,.08);
}
.trendTop{display:flex; align-items:center; justify-content:space-between; gap:10px;}
.trendHabit{color:#fff; font-size:.94rem; font-weight:950;}
.trendBadge{font-size:.68rem; font-weight:950; border-radius:999px; padding:4px 8px; white-space:nowrap; border:1px solid #45618d; color:#dbe7ff; background:#111b2d;}
.trendBadge.warn{border-color:#d6a94d; color:#ffd76a; background:rgba(214,169,77,.10);}
.trendBadge.up{border-color:#4fbf8f; color:#7ff0bd; background:rgba(79,191,143,.10);}
.trendBadge.strong{border-color:#5b8fe6; color:#9fc0ff; background:rgba(91,143,230,.10);}
.trendBadge.stable{border-color:#9b63ff; color:#c8a8ff; background:rgba(139,77,255,.12);}
.trendObs{color:#dbe7ff; font-size:.84rem; line-height:1.38; margin-top:7px;}
.trendMeta{color:#8fa2bf; font-size:.72rem; font-weight:800; margin-top:6px;}
.trendAction{margin-top:9px; padding-top:8px; border-top:1px solid rgba(69,97,141,.38); color:#f7f4ff; font-size:.76rem; font-weight:850; line-height:1.35;}
.trendAction span{color:#b55cff; font-size:.67rem; letter-spacing:.45px; text-transform:uppercase; margin-right:5px;}

/* ---------- QUICK MISSION MODE ---------- */
.st-key-quick_mission_controls{
  margin:0 0 14px 0!important;
  padding:10px 10px 11px 10px!important;
  border:1px solid rgba(139,77,255,.48)!important;
  border-radius:15px!important;
  background:linear-gradient(180deg,rgba(15,23,40,.98),rgba(8,12,21,.98))!important;
  box-shadow:0 8px 18px rgba(139,77,255,.09)!important;
}
.st-key-quick_mission_controls [data-testid="stHorizontalBlock"]{gap:.40rem!important;}
.st-key-quick_mission_controls .stButton>button{
  min-height:34px!important;
  height:34px!important;
  border-radius:999px!important;
  padding:4px 7px!important;
  font-size:.75rem!important;
  background:#10192a!important;
  color:#f7f4ff!important;
  border:1px solid #45618d!important;
  box-shadow:0 0 8px rgba(139,77,255,.08)!important;
}
.st-key-quick_mission_controls .stButton>button:hover{
  background:rgba(139,77,255,.24)!important;
  border-color:#b55cff!important;
  transform:translateY(-1px);
}
.quickMissionHint{
  color:#8fa2bf; font-size:.67rem; font-weight:800; letter-spacing:.35px;
  text-transform:uppercase; margin:0 0 7px 2px;
}
.quickMissionFlash{
  border:1px solid rgba(98,240,178,.55); border-radius:13px; padding:9px 11px;
  margin:0 0 10px 0; color:#93f5c9; background:rgba(18,49,47,.72);
  font-size:.82rem; font-weight:900; animation:missionLift .35s ease both;
}

</style>
""", unsafe_allow_html=True)



# -----------------------------
# PHASE 8 - COMPANION VOICE
# -----------------------------
VOICE_PERSONALITY = {
    "tone": "calm, observant, confident, slightly warm",
    "rules": [
        "Keep spoken lines brief.",
        "Never read the whole screen aloud.",
        "Use Terrence's name sparingly.",
        "Give direction without lecturing or shaming.",
        "Speak only when voice adds emotion, direction, encouragement, or closure.",
    ],
}


def elevenlabs_ready():
    return bool(ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID)


def spoken_companion_line(event, **context):
    """Create the short line ElevenLabs speaks while the screen keeps full detail."""
    task = str(context.get("task") or "the next move")
    minutes = int(context.get("minutes", 0) or 0)
    quote = str(context.get("quote") or "").strip()
    status = str(context.get("status") or "").strip()
    remaining = int(context.get("remaining", 0) or 0)

    if event == "opening":
        mode = str(context.get("mode") or "Steady Build")
        if task and minutes:
            return f"Welcome back, Terrence. {task} is the priority. Give me {minutes} focused minutes."
        return f"Welcome back, Terrence. {mode} mode is active. Let's protect the next move."

    if event == "target":
        if minutes:
            return f"{task} is the Companion Target. Let's protect {minutes} minutes."
        return f"{task} is next."

    if event == "task_logged":
        next_task = str(context.get("next_task") or "").strip()
        if next_task:
            return f"{task} is handled. {next_task} is next."
        return f"{task} is handled. Keep moving."

    if event == "quote":
        return f"You asked for a push. Take this with you. {quote}" if quote else "You asked for a push. Take this with you."

    if event == "early_quit":
        return quote or "The day is not finished yet. One small loop can still protect it."

    if event == "minimums_complete":
        return "Every promise is protected. Bonus Round is now available."

    if event == "bonus_target":
        return f"Bonus target: {task}. Add {minutes} more minutes while the momentum is warm."

    if event == "bonus_complete":
        return "Every available upgrade is complete. There's nothing left to prove tonight. Go enjoy your evening."

    if event == "end_day":
        if status:
            return f"{status}. The day is sealed. We'll continue from here tomorrow."
        return "The day is sealed. We'll continue from here tomorrow."

    if event == "remaining":
        return f"{remaining} promises are still open. We only need the next one."

    return str(context.get("fallback") or "Keep moving.").strip()


@st.cache_data(show_spinner=False, ttl=60 * 60 * 24, max_entries=80)
def generate_elevenlabs_audio(text, api_key, voice_id, model_id):
    """Generate MP3 bytes through ElevenLabs' REST API and cache repeated lines."""
    clean = " ".join(str(text or "").split()).strip()
    if not clean:
        return b""

    endpoint = (
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        f"?output_format={ELEVENLABS_OUTPUT_FORMAT}"
    )
    payload = json.dumps({
        "text": clean,
        "model_id": model_id or "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.58,
            "similarity_boost": 0.78,
            "style": 0.18,
            "use_speaker_boost": True,
        },
    }).encode("utf-8")

    request = urllib.request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:300]
        raise RuntimeError(f"ElevenLabs returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach ElevenLabs: {exc.reason}") from exc


def queue_companion_voice(state, text, event_key, autoplay=True, force=False):
    """Queue one meaningful spoken line and prevent duplicate Streamlit reruns."""
    clean = " ".join(str(text or "").split()).strip()
    if not clean or not state.get("voice_enabled", True) or not elevenlabs_ready():
        return

    fingerprint = hashlib.sha1(f"{event_key}|{clean}".encode("utf-8")).hexdigest()
    spoken = st.session_state.setdefault("spoken_voice_events", set())
    if not isinstance(spoken, set):
        spoken = set(spoken or [])
        st.session_state["spoken_voice_events"] = spoken
    if fingerprint in spoken and not force:
        return

    spoken.add(fingerprint)
    st.session_state["pending_companion_voice"] = {
        "text": clean,
        "event_key": event_key,
        "autoplay": bool(autoplay and state.get("voice_auto", True)),
    }
    state["last_spoken_text"] = clean
    save_state(state)


def render_pending_companion_voice(state):
    """Play queued ElevenLabs audio invisibly, with no visible audio player."""
    pending = st.session_state.pop("pending_companion_voice", None)
    if not pending or not state.get("voice_enabled", True):
        return

    try:
        audio = generate_elevenlabs_audio(
            pending["text"],
            ELEVENLABS_API_KEY,
            ELEVENLABS_VOICE_ID,
            ELEVENLABS_MODEL_ID,
        )
        if not audio:
            return

        import base64
        encoded = base64.b64encode(audio).decode("ascii")
        autoplay = "true" if bool(pending.get("autoplay")) else "false"

        components.html(
            f"""
            <audio id="momentum-companion-voice"
                   src="data:audio/mpeg;base64,{encoded}"
                   preload="auto"
                   style="display:none"></audio>
            <script>
            (() => {{
              const audio = document.getElementById("momentum-companion-voice");
              if (!audio) return;

              const shouldAutoplay = {autoplay};

              const playNow = () => {{
                audio.play().catch(() => {{
                  // iOS/Safari may require a real user gesture first.
                  const parentDoc = window.parent.document;
                  const unlock = () => {{
                    audio.play().catch(() => {{}});
                    parentDoc.removeEventListener("click", unlock, true);
                    parentDoc.removeEventListener("touchstart", unlock, true);
                  }};
                  parentDoc.addEventListener("click", unlock, true);
                  parentDoc.addEventListener("touchstart", unlock, true);
                }});
              }};

              if (shouldAutoplay) {{
                setTimeout(playNow, 80);
              }} else {{
                // For tap-to-play events, the Streamlit button click just occurred.
                setTimeout(playNow, 80);
              }}
            }})();
            </script>
            """,
            height=0,
        )
    except Exception as exc:
        # Keep failures quiet in normal use, but store the latest error for diagnostics.
        st.session_state["last_voice_error"] = str(exc)


def render_voice_controls(state):
    st.markdown("<div class='card'><div class='label'>Companion Voice</div>", unsafe_allow_html=True)
    if not elevenlabs_ready():
        st.warning(
            "Voice is coded but not connected yet. Add ELEVENLABS_API_KEY and "
            "ELEVENLABS_VOICE_ID in Render Environment Variables."
        )
        st.markdown("</div>", unsafe_allow_html=True)
        return

    enabled = st.toggle("Voice enabled", value=bool(state.get("voice_enabled", True)), key="voice_enabled_toggle")
    auto = st.toggle(
        "Automatically speak major moments",
        value=bool(state.get("voice_auto", True)),
        key="voice_auto_toggle",
        disabled=not enabled,
    )
    if enabled != state.get("voice_enabled") or auto != state.get("voice_auto"):
        state["voice_enabled"] = enabled
        state["voice_auto"] = auto
        save_state(state)

    c1, c2 = st.columns(2)
    if c1.button("▶ Test voice", use_container_width=True, disabled=not enabled):
        line = "Voice online. Calm, focused, and ready when you are."
        queue_companion_voice(state, line, "voice_test", autoplay=True, force=True)
        st.rerun()
    if c2.button("↻ Replay last", use_container_width=True, disabled=not enabled or not state.get("last_spoken_text")):
        queue_companion_voice(
            state,
            state.get("last_spoken_text", ""),
            "voice_replay",
            autoplay=True,
            force=True,
        )
        st.rerun()

    st.caption("Automatic voice is reserved for openings, quotes, major completions, and day closeout.")
    st.markdown("</div>", unsafe_allow_html=True)


def load_json(path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def save_json(path, data):
    path.write_text(json.dumps(data, indent=4), encoding="utf-8")


def momentum_now():
    now = datetime.now()
    if now.hour < DAY_ROLLOVER_HOUR:
        now -= timedelta(days=1)
    return now


def today_key():
    return momentum_now().strftime("%Y-%m-%d")


def normalize_duration(value):
    try:
        value = int(value or 0)
    except Exception:
        return 0
    if value >= 40: return 40
    if value >= 30: return 30
    if value >= 20: return 20
    if value >= 10: return 10
    return 0


def get_task(canonical):
    return next((t for t in DAILY_TASKS if t["canonical"] == canonical), None)


def duration_options(canonical):
    task = get_task(canonical)
    return sorted(task["xp_by_minutes"].keys()) if task else [10, 20, 30]


def normalize_task_duration(canonical, value):
    d = normalize_duration(value)
    opts = duration_options(canonical)
    valid = [x for x in opts if d >= x]
    return max(valid) if valid else 0


def task_xp(canonical, minutes):
    task = get_task(canonical)
    if not task: return 0
    minutes = normalize_task_duration(canonical, minutes)
    return int(task["xp_by_minutes"].get(minutes, 0))


def max_daily_xp():
    return sum(max(t["xp_by_minutes"].values()) for t in DAILY_TASKS)


def default_state():
    return {
        "date": today_key(),
        "updated_at": datetime.now().strftime("%Y-%m-%d %I:%M %p"),
        "energy": "Normal",
        "location": "Work",
        "durations": {t["canonical"]: 0 for t in DAILY_TASKS},
        "collapsed_tasks": [],
        "workout": {
            exercise["name"]: {"done": False, "set1": 0, "set2": 0}
            for exercise in WORK_EXERCISES
        },
        "day_closed": False,
        "bonus_round_announced": False,
        "voice_enabled": True,
        "voice_auto": True,
        "last_spoken_text": "",
        "chat_log": [],
    }


def load_state():
    state = load_json(TODAY_TASKS_FILE, None)
    if not isinstance(state, dict) or state.get("date") != today_key():
        state = default_state()
        save_json(TODAY_TASKS_FILE, state)
    state.setdefault("durations", {})
    state.setdefault("chat_log", [])
    state.setdefault("collapsed_tasks", [])
    state.setdefault("workout", {})
    state.setdefault("voice_enabled", True)
    state.setdefault("voice_auto", True)
    state.setdefault("last_spoken_text", "")
    if not isinstance(state.get("collapsed_tasks"), list):
        state["collapsed_tasks"] = []
    if not isinstance(state.get("workout"), dict):
        state["workout"] = {}
    for exercise in WORK_EXERCISES:
        name = exercise["name"]
        row = state["workout"].setdefault(name, {})
        row["done"] = bool(row.get("done", False))
        try:
            row["set1"] = max(0, int(row.get("set1", 0) or 0))
        except Exception:
            row["set1"] = 0
        try:
            row["set2"] = max(0, int(row.get("set2", 0) or 0))
        except Exception:
            row["set2"] = 0
    valid_tasks = {t["canonical"] for t in DAILY_TASKS}
    state["collapsed_tasks"] = [c for c in state["collapsed_tasks"] if c in valid_tasks]
    for t in DAILY_TASKS:
        c = t["canonical"]
        state["durations"][c] = normalize_task_duration(c, state["durations"].get(c, 0))
    return state


def save_state(state):
    state["date"] = today_key()
    state["updated_at"] = datetime.now().strftime("%Y-%m-%d %I:%M %p")
    save_json(TODAY_TASKS_FILE, state)


def save_progress_to_history(state):
    history = load_json(HISTORY_FILE, {})
    tasks_payload, missed = [], []
    completed, xp = 0, 0
    for t in DAILY_TASKS:
        c = t["canonical"]
        d = normalize_task_duration(c, state["durations"].get(c, 0))
        done = d > 0
        earned = task_xp(c, d)
        completed += 1 if done else 0
        xp += earned
        if not done: missed.append(c)
        tasks_payload.append({"text": c, "display": t["display"], "done": done, "duration_minutes": d, "xp": earned})
    history[today_key()] = {
        "date": today_key(), "saved_at": datetime.now().strftime("%Y-%m-%d %I:%M %p"),
        "location": state.get("location", "Work"), "energy": state.get("energy", "Normal"),
        "completed": completed, "total": len(DAILY_TASKS), "finished_all": completed == len(DAILY_TASKS),
        "missed_tasks": missed, "tasks": tasks_payload, "xp_earned": xp,
        "xp_possible": max_daily_xp(), "day_closed": bool(state.get("day_closed", False)),
        "bonus_upgrades": [
            {
                "text": t["canonical"],
                "display": t["display"],
                "tier": task_tier(t["canonical"], state["durations"].get(t["canonical"], 0)),
                "duration_minutes": normalize_task_duration(
                    t["canonical"], state["durations"].get(t["canonical"], 0)
                ),
            }
            for t in DAILY_TASKS
            if task_tier(t["canonical"], state["durations"].get(t["canonical"], 0))
            in {"growth", "mastery"}
        ],
    }
    save_json(HISTORY_FILE, history)


def totals():
    history = load_json(HISTORY_FILE, {})
    rows = [v for v in history.values() if isinstance(v, dict) and not v.get("is_inactive")]
    total_xp = sum(int(r.get("xp_earned", 0) or 0) for r in rows)
    tasks_done = sum(int(r.get("completed", 0) or 0) for r in rows)
    days_logged = len(rows)
    streak = 0
    day = momentum_now().date()
    while True:
        r = history.get(day.strftime("%Y-%m-%d"))
        if not r or int(r.get("completed", 0) or 0) == 0:
            break
        streak += 1
        day -= timedelta(days=1)
    return {"xp": total_xp, "tasks": tasks_done, "days": days_logged, "streak": streak}



# -----------------------------
# PHASE 1 - REAL HISTORY ANALYSIS
# -----------------------------
def normalize_history_task_name(text):
    """Normalize old and new history labels to the mobile app's canonical task names."""
    key = str(text or "").strip().lower()
    aliases = {
        "networking": "Networking / LinkedIn",
        "linkedin": "Networking / LinkedIn",
        "linked in": "Networking / LinkedIn",
        "networking / linkedin": "Networking / LinkedIn",
        "spanish": "Spanish Review",
        "spanish review": "Spanish Review",
        "review spanish notes": "Spanish Review",
        "complete workout": "Complete Workout",
        "workout": "Complete Workout",
        "exercise": "Complete Workout",
        "exercised": "Complete Workout",
        "excercise": "Complete Workout",
        "excercised": "Complete Workout",
        "coding": "Coding Core Task",
        "coding task": "Coding Core Task",
        "coding core task": "Coding Core Task",
        "reading": "Reading",
        "read": "Reading",
    }
    return aliases.get(key, str(text or "").strip())


def history_completion_percent(record):
    total = int(record.get("total", 0) or 0)
    completed = int(record.get("completed", 0) or 0)
    return int((completed / total) * 100) if total else 0


def history_task_done(record, task_name):
    target = normalize_history_task_name(task_name).lower()
    for item in record.get("tasks", []):
        name = normalize_history_task_name(item.get("text") or item.get("display", "")).lower()
        if name == target and bool(item.get("done")):
            return True
    return False


def get_last_saved_history_day(history):
    valid = []
    for key, record in history.items():
        if not isinstance(record, dict):
            continue
        try:
            datetime.strptime(key, "%Y-%m-%d")
            valid.append(key)
        except (TypeError, ValueError):
            continue
    if not valid:
        return None, {}
    latest_key = sorted(valid)[-1]
    return latest_key, history.get(latest_key, {})


def get_recent_logged_history(history, limit=7):
    """Latest saved sessions only; generated inactive placeholders are ignored."""
    rows = []
    for key, record in history.items():
        if not isinstance(record, dict):
            continue
        try:
            datetime.strptime(key, "%Y-%m-%d")
        except (TypeError, ValueError):
            continue
        if record.get("is_inactive"):
            continue
        rows.append((key, record, history_completion_percent(record)))
    rows.sort(key=lambda row: row[0], reverse=True)
    return rows[:limit]


def get_growth_history_stats(history, limit=7):
    """Measure each habit from real logged opportunities, not empty calendar placeholders."""
    recent = get_recent_logged_history(history, limit=limit)
    stats = {
        task: {"done": 0, "missed": 0, "expected": 0, "rate": 0}
        for task in GROWTH_TASKS
    }

    for _, record, _ in recent:
        mentioned = {
            normalize_history_task_name(item.get("text") or item.get("display", "")).lower()
            for item in record.get("tasks", [])
        }
        missed_names = {
            normalize_history_task_name(name).lower()
            for name in record.get("missed_tasks", [])
        }

        for task_name in GROWTH_TASKS:
            target = task_name.lower()
            if target not in mentioned and target not in missed_names:
                continue
            stats[task_name]["expected"] += 1
            if history_task_done(record, task_name):
                stats[task_name]["done"] += 1
            else:
                stats[task_name]["missed"] += 1

    for row in stats.values():
        expected = row["expected"]
        row["rate"] = int((row["done"] / expected) * 100) if expected else 0

    usable = {name: row for name, row in stats.items() if row["expected"] > 0}
    if not usable:
        return stats, "Unknown", "Unknown"

    strongest = max(
        usable.items(),
        key=lambda item: (item[1]["rate"], item[1]["done"], -item[1]["missed"]),
    )[0]
    weakest = min(
        usable.items(),
        key=lambda item: (item[1]["rate"], -item[1]["missed"], item[1]["done"]),
    )[0]

    if strongest == weakest and len(usable) > 1:
        alternatives = {name: row for name, row in usable.items() if name != strongest}
        weakest = max(
            alternatives.items(),
            key=lambda item: (item[1]["missed"], -item[1]["rate"]),
        )[0]

    return stats, strongest, weakest


def get_history_category_stats(growth_stats):
    category_stats = {}
    for task_name, row in growth_stats.items():
        category = TASK_CATEGORIES.get(task_name)
        if not category:
            continue
        target = category_stats.setdefault(
            category, {"done": 0, "missed": 0, "expected": 0, "rate": 0}
        )
        target["done"] += int(row.get("done", 0) or 0)
        target["missed"] += int(row.get("missed", 0) or 0)
        target["expected"] += int(row.get("expected", 0) or 0)

    for row in category_stats.values():
        expected = row["expected"]
        row["rate"] = int((row["done"] / expected) * 100) if expected else 0
    return category_stats


def strongest_and_weakest_category(category_stats):
    usable = {name: row for name, row in category_stats.items() if row["expected"] > 0}
    if not usable:
        return "Unknown", "Unknown"

    strongest = max(
        usable.items(),
        key=lambda item: (item[1]["rate"], item[1]["done"], -item[1]["missed"]),
    )[0]
    weakest = min(
        usable.items(),
        key=lambda item: (item[1]["rate"], -item[1]["missed"], item[1]["done"]),
    )[0]
    if strongest == weakest and len(usable) > 1:
        alternatives = {name: row for name, row in usable.items() if name != strongest}
        weakest = max(
            alternatives.items(),
            key=lambda item: (item[1]["missed"], -item[1]["rate"]),
        )[0]
    return strongest, weakest


def build_history_timeline(history):
    """Fill calendar gaps with inactive-day records without changing the saved JSON."""
    dates = []
    for key, record in history.items():
        if not isinstance(record, dict):
            continue
        try:
            dates.append(datetime.strptime(key, "%Y-%m-%d").date())
        except (TypeError, ValueError):
            continue
    if not dates:
        return []

    start = min(dates)
    end = max(max(dates), momentum_now().date())
    timeline = []
    current = start

    while current <= end:
        key = current.strftime("%Y-%m-%d")
        if key in history and isinstance(history[key], dict):
            record = dict(history[key])
            record["is_inactive"] = False
        else:
            record = {
                "date": key,
                "is_inactive": True,
                "completed": 0,
                "total": len(DAILY_TASKS),
                "finished_all": False,
                "missed_tasks": [],
                "tasks": [],
                "xp_earned": 0,
                "energy": "Inactive",
                "location": "Unknown",
            }
        timeline.append((key, record, history_completion_percent(record)))
        current += timedelta(days=1)
    return timeline


def classify_history_day(record):
    if record.get("is_inactive"):
        return "Inactive Day"
    completed = int(record.get("completed", 0) or 0)
    total = int(record.get("total", 0) or 0)
    percent = history_completion_percent(record)
    if total > 0 and completed == 0:
        return "Missed Day"
    if record.get("finished_all"):
        return "Clean Finish"
    if percent >= 75:
        return "Strong"
    if percent >= 50:
        return "Stable"
    if percent > 0:
        return "Recovery Day"
    return "Missed Day"


def analyze_history():
    """Read the last seven calendar days and last seven real logged sessions."""
    history = load_json(HISTORY_FILE, {})
    if not isinstance(history, dict):
        history = {}
    timeline = build_history_timeline(history)

    if not timeline:
        return {
            "current_state": "No Data Yet",
            "last_logged_day": "None",
            "last_result": "No saved momentum history found.",
            "strongest_habit": "Unknown",
            "weakest_habit": "Unknown",
            "growth_task_stats": {
                task: {"done": 0, "missed": 0, "expected": 0, "rate": 0}
                for task in GROWTH_TASKS
            },
            "category_stats": {},
            "strongest_category": "Unknown",
            "weakest_category": "Unknown",
            "inactive_days_recent": 0,
            "missed_days_recent": 0,
            "recovery_days_recent": 0,
            "average_recent_completion": 0,
            "logged_session_average": 0,
            "recommended_move": "Complete and save one core task.",
            "reason": "The history file does not contain a logged day yet.",
        }

    latest_key, latest_record = get_last_saved_history_day(history)
    latest_state = classify_history_day(latest_record)
    latest_percent = history_completion_percent(latest_record)

    recent_calendar = timeline[-7:]
    inactive_days = 0
    missed_days = 0
    recovery_days = 0
    for _, record, _ in recent_calendar:
        label = classify_history_day(record)
        if label == "Inactive Day":
            inactive_days += 1
        elif label == "Missed Day":
            missed_days += 1
        elif label == "Recovery Day":
            recovery_days += 1

    calendar_average = int(
        sum(percent for _, _, percent in recent_calendar) / len(recent_calendar)
    ) if recent_calendar else 0

    recent_logged = get_recent_logged_history(history, limit=7)
    logged_average = int(
        sum(percent for _, _, percent in recent_logged) / len(recent_logged)
    ) if recent_logged else 0

    growth_stats, strongest_habit, weakest_habit = get_growth_history_stats(history, limit=7)
    category_stats = get_history_category_stats(growth_stats)
    strongest_category, weakest_category = strongest_and_weakest_category(category_stats)

    if inactive_days >= 3:
        current_state = "Rebuild Mode"
    elif calendar_average >= 80:
        current_state = "Momentum Rising"
    elif calendar_average >= 50:
        current_state = "Momentum Stable"
    elif calendar_average > 0:
        current_state = "Recovery Mode"
    else:
        current_state = "Danger Zone"

    if inactive_days >= 2:
        recommended_move = "Complete one core task to break the inactive chain."
        reason = f"{inactive_days} inactive calendar days were detected in the recent seven-day window."
    elif weakest_habit == "Networking / LinkedIn":
        recommended_move = "Do one LinkedIn comment or connection."
        reason = "Networking is the weakest habit across recent logged sessions."
    elif weakest_habit == "Coding Core Task":
        recommended_move = "Open the coding project and make one small improvement."
        reason = "Coding is the weakest habit across recent logged sessions."
    elif weakest_habit == "Spanish Review":
        recommended_move = "Complete one short Spanish review."
        reason = "Spanish is the weakest habit across recent logged sessions."
    elif weakest_habit == "Complete Workout":
        recommended_move = "Complete one short movement block."
        reason = "Exercise is the weakest habit across recent logged sessions."
    elif weakest_habit == "Reading":
        recommended_move = "Read one useful section."
        reason = "Reading is the weakest habit across recent logged sessions."
    else:
        recommended_move = "Complete one core task and save progress."
        reason = "More logged task data is needed to rank habits cleanly."

    return {
        "current_state": current_state,
        "last_logged_day": latest_key or "None",
        "last_result": (
            f"{latest_state}: {latest_record.get('completed', 0)}/"
            f"{latest_record.get('total', 0)} core tasks completed ({latest_percent}%)."
        ),
        "strongest_habit": strongest_habit,
        "weakest_habit": weakest_habit,
        "growth_task_stats": growth_stats,
        "category_stats": category_stats,
        "strongest_category": strongest_category,
        "weakest_category": weakest_category,
        "inactive_days_recent": inactive_days,
        "missed_days_recent": missed_days,
        "recovery_days_recent": recovery_days,
        "average_recent_completion": calendar_average,
        "logged_session_average": logged_average,
        "recommended_move": recommended_move,
        "reason": reason,
    }



def build_companion_state():
    """Translate real history into the Companion's current operating state."""
    brain = analyze_history()
    stats = brain.get("growth_task_stats", {}) or {}

    max_missed = 0
    focus_task = brain.get("weakest_habit", "Unknown")
    for task_name, row in stats.items():
        missed = int(row.get("missed", 0) or 0)
        if missed > max_missed:
            max_missed = missed
            focus_task = task_name

    inactive_days = int(brain.get("inactive_days_recent", 0) or 0)
    missed_days = int(brain.get("missed_days_recent", 0) or 0)
    logged_average = int(brain.get("logged_session_average", 0) or 0)

    if inactive_days >= 2 or max_missed >= 2 or missed_days >= 2:
        return {
            "mode": "Urgent Recovery",
            "mood": "Serious",
            "urgency": "High",
            "focus_task": focus_task,
            "reason": "A habit or check-in pattern is lagging by at least two opportunities.",
        }

    if logged_average >= 70 and inactive_days == 0 and max_missed <= 1:
        return {
            "mode": "Momentum Push",
            "mood": "Energetic",
            "urgency": "Medium",
            "focus_task": focus_task,
            "reason": "Recent logged sessions are strong and no major habit is badly behind.",
        }

    return {
        "mode": "Steady Build",
        "mood": "Calm",
        "urgency": "Medium",
        "focus_task": focus_task,
        "reason": "There is movement, but the recent pattern does not justify a hard push yet.",
    }


def format_companion_state():
    state = build_companion_state()
    focus = display_task_name(state.get("focus_task", "Unknown"))
    return (
        "COMPANION STATE\n\n"
        f"Mode: {state.get('mode')}\n"
        f"Mood: {state.get('mood')}\n"
        f"Urgency: {state.get('urgency')}\n"
        f"Focus: {focus}\n\n"
        f"Reason: {state.get('reason')}"
    )


def is_companion_state_request(text):
    low = str(text or "").lower().strip()
    phrases = [
        "companion state", "companion mode", "brain state", "what mode am i in",
        "what mode is this", "current mode", "recovery mode", "momentum push",
        "steady build",
    ]
    return low in {"mode", "brain"} or any(phrase in low for phrase in phrases)

def display_task_name(canonical):
    task = get_task(canonical)
    return task["display"] if task else canonical


def format_history_analysis():
    brain = analyze_history()
    strongest = display_task_name(brain["strongest_habit"])
    weakest = display_task_name(brain["weakest_habit"])

    lines = [
        "MOMENTUM HISTORY",
        "",
        f"State: {brain['current_state']}",
        f"Last logged: {brain['last_logged_day']}",
        f"Last result: {brain['last_result']}",
        "",
        f"7-day calendar average: {brain['average_recent_completion']}%",
        f"Last 7 logged sessions: {brain['logged_session_average']}%",
        f"Inactive days: {brain['inactive_days_recent']}",
        f"Missed days: {brain['missed_days_recent']}",
        f"Recovery days: {brain['recovery_days_recent']}",
        "",
        f"Strongest habit: {strongest}",
        f"Weakest habit: {weakest}",
        "",
        f"Recommended move: {brain['recommended_move']}",
        f"Reason: {brain['reason']}",
    ]
    return "\n".join(lines)


def is_history_analysis_request(text):
    low = str(text or "").lower().strip()
    phrases = [
        "history analysis",
        "analyze history",
        "analyse history",
        "momentum history",
        "history report",
        "how is my momentum",
        "current momentum",
        "strongest habit",
        "weakest habit",
        "where am i slipping",
    ]
    return low in {"history", "analysis", "insights"} or any(phrase in low for phrase in phrases)

def task_by_words(text):
    s = text.lower()
    pairs = [
        (["code", "coding", "program", "python"], "Coding Core Task"),
        (["spanish", "español"], "Spanish Review"),
        (["exercise", "workout", "lift", "squat", "jump rope", "pushup", "pullup"], "Complete Workout"),
        (["network", "linkedin", "comment", "connection"], "Networking / LinkedIn"),
        (["read", "reading", "book"], "Reading"),
    ]
    for words, canonical in pairs:
        if any(w in s for w in words):
            return canonical
    return None


def minutes_from_text(text, canonical):
    m = re.search(r"(\d{1,3})\s*(m|min|minute|minutes)?", text.lower())
    if m:
        return normalize_task_duration(canonical, int(m.group(1)))
    opts = duration_options(canonical)
    return min(opts) if opts else 10


def completed_count(state):
    return sum(1 for t in DAILY_TASKS if state["durations"].get(t["canonical"], 0) > 0)


def xp_today(state):
    return sum(task_xp(t["canonical"], state["durations"].get(t["canonical"], 0)) for t in DAILY_TASKS)


def next_task(state):
    """Legacy ordered fallback. The real recommendation engine is below."""
    for t in DAILY_TASKS:
        if state["durations"].get(t["canonical"], 0) == 0:
            return t
    return None


TASK_PRIORITY_WEIGHTS = {
    "Coding Core Task": 35,
    "Complete Workout": 30,
    "Spanish Review": 28,
    "Networking / LinkedIn": 24,
    "Reading": 12,
}


def weekend_survival_day():
    """User-specific danger window retained from the original app."""
    return momentum_now().weekday() in {0, 5, 6}  # Monday, Saturday, Sunday


def recommendation_minutes(canonical, energy, survival_mode=False):
    if str(energy or "Normal").title() == "Low":
        return 10 if 10 in duration_options(canonical) else min(duration_options(canonical))
    if survival_mode:
        return 10 if canonical in {"Networking / LinkedIn", "Reading"} else min(duration_options(canonical))
    return min(duration_options(canonical))


def recommendation_action(canonical, minutes):
    actions = {
        "Coding Core Task": f"Coding — {minutes} minutes. Make one small improvement.",
        "Spanish Review": f"Spanish — {minutes} minutes. Complete one review or shadowing loop.",
        "Complete Workout": f"Exercise — {minutes} minutes. Movement first; intensity optional.",
        "Networking / LinkedIn": f"Networking — {minutes} minutes. One comment or one connection.",
        "Reading": f"Reading — {minutes} minutes. One useful section counts.",
    }
    return actions.get(canonical, f"{display_task_name(canonical)} — {minutes} minutes.")


def recommendation_start(canonical):
    starts = {
        "Coding Core Task": "Open your current project.",
        "Spanish Review": "Open the Spanish app.",
        "Complete Workout": "Grab the jump rope or start your first movement.",
        "Networking / LinkedIn": "Open LinkedIn.",
        "Reading": "Open the book to your current page.",
    }
    return starts.get(canonical, f"Open {display_task_name(canonical)}.")


def recommendation_badge(rec):
    mode = rec.get("mode", "Next Best Move")
    labels = {
        "Finish The Board": "🏁 Finish Today",
        "Weekend Survival": "⚠ Break The Zero",
        "Recovery Target": "⚠ Recovery Target",
        "Pressure Target": "🔥 High Priority",
        "Next Best Move": "📈 Next Move",
        "Bonus Round": "✨ Bonus Round Active",
    }
    return labels.get(mode, f"🎯 {rec.get('priority', 'Priority')}")


def recommendation_reason_short(rec):
    reason = str(rec.get("reason", "")).strip()
    if not reason:
        return "This is the highest-value unfinished task right now."
    return reason


def score_what_now_candidate(task, state, history_brain, companion_state, survival_mode=False):
    canonical = task["canonical"]
    current = normalize_task_duration(canonical, state.get("durations", {}).get(canonical, 0))
    if current > 0:
        return -10000, []

    score = 100
    reasons = ["unfinished"]
    weight = TASK_PRIORITY_WEIGHTS.get(canonical, 10)
    score += weight
    reasons.append(f"personal priority +{weight}")

    stats = history_brain.get("growth_task_stats", {}) or {}
    row = stats.get(canonical, {}) or {}
    missed = int(row.get("missed", 0) or 0)
    rate = int(row.get("rate", 0) or 0)
    weakest = history_brain.get("weakest_habit", "Unknown")

    if missed:
        score += missed * 8
        reasons.append(f"{missed} missed logged opportunit{'y' if missed == 1 else 'ies'}")
    if canonical == weakest:
        score += 20
        reasons.append("weakest recent habit")
    if row.get("expected", 0) and rate <= 50:
        score += 8
        reasons.append(f"low completion rate ({rate}%)")

    energy = str(state.get("energy", "Normal") or "Normal").title()
    if energy == "Low":
        if canonical in {"Networking / LinkedIn", "Reading"}:
            score += 12
            reasons.append("low-energy friendly")
        else:
            score -= 4

    if companion_state.get("mode") == "Urgent Recovery":
        if canonical == companion_state.get("focus_task"):
            score += 18
            reasons.append("recovery focus")
        else:
            score += 4

    if survival_mode:
        survival_weights = {
            "Complete Workout": 22,
            "Spanish Review": 18,
            "Coding Core Task": 18,
            "Reading": 8,
            "Networking / LinkedIn": 4,
        }
        boost = survival_weights.get(canonical, 0)
        score += boost
        if boost:
            reasons.append("weekend survival weighting")

    return score, reasons



def all_energy_minimums_met(state):
    energy = str(state.get("energy", "Normal") or "Normal").title()
    return all(
        normalize_task_duration(
            task["canonical"],
            state.get("durations", {}).get(task["canonical"], 0),
        ) >= minimum_required_minutes(task["canonical"], energy)
        for task in DAILY_TASKS
    )


def next_duration_tier(canonical, current):
    current = normalize_task_duration(canonical, current)
    for option in duration_options(canonical):
        if option > current:
            return option
    return None


def bonus_upgrade_action(canonical, current, target):
    display = get_task(canonical)["display"]
    extra = target - current
    return f"{display} — add {extra} minutes. Upgrade {current}m to {target}m."


def score_bonus_candidate(task, state, history_brain):
    canonical = task["canonical"]
    current = normalize_task_duration(
        canonical, state.get("durations", {}).get(canonical, 0)
    )
    target = next_duration_tier(canonical, current)
    if target is None:
        return None

    current_xp = task_xp(canonical, current)
    target_xp = task_xp(canonical, target)
    xp_gain = target_xp - current_xp

    stats = (history_brain.get("growth_task_stats", {}) or {}).get(canonical, {}) or {}
    missed = int(stats.get("missed", 0) or 0)
    rate = int(stats.get("rate", 0) or 0)
    expected = int(stats.get("expected", 0) or 0)
    weakest = history_brain.get("weakest_habit", "Unknown")
    tier = task_tier(canonical, current)

    score = xp_gain * 2
    signals = [f"+{xp_gain} available XP", f"currently at {tier} tier"]

    if canonical == weakest:
        score += 35
        signals.append("weakest recent habit")
    if missed:
        boost = min(30, missed * 7)
        score += boost
        signals.append(f"{missed} recent missed opportunit{'y' if missed == 1 else 'ies'}")
    if expected and rate <= 50:
        score += 22
        signals.append(f"low historical rate ({rate}%)")
    elif expected and rate <= 70:
        score += 10
        signals.append(f"historical rate {rate}%")

    # Prefer strengthening a minimum before stacking mastery on an already-strong habit.
    if tier == "minimum":
        score += 18
        signals.append("growth tier is the next clean upgrade")
    elif tier == "growth":
        score += 6
        signals.append("mastery tier is available")

    return {
        "score": score,
        "task": task,
        "canonical": canonical,
        "current_minutes": current,
        "minutes": target,
        "extra_minutes": target - current,
        "current_xp": current_xp,
        "target_xp": target_xp,
        "xp_gain": xp_gain,
        "signals": signals,
        "tier_from": tier,
        "tier_to": task_tier(canonical, target),
    }


def get_bonus_recommendation(state):
    """Choose one intelligent optional upgrade after all minimums are protected."""
    if not all_energy_minimums_met(state):
        return None

    history_brain = analyze_history()
    candidates = []
    for task in DAILY_TASKS:
        candidate = score_bonus_candidate(task, state, history_brain)
        if candidate:
            candidates.append(candidate)

    if not candidates:
        return None

    candidates.sort(key=lambda row: row["score"], reverse=True)
    best = candidates[0]
    task = best["task"]
    display = task["display"]
    weakest = task["canonical"] == history_brain.get("weakest_habit")
    missed = any("missed opportunit" in signal for signal in best.get("signals", []))
    rate_signal = next(
        (signal for signal in best.get("signals", []) if "historical rate" in signal),
        "",
    )

    if weakest:
        reason = (
            f"{display} has been the easiest habit to lose lately. "
            f"One more {best['extra_minutes']}-minute block strengthens it."
        )
    elif missed:
        reason = (
            f"{display} has slipped more than once recently. "
            f"Let's reinforce it while today's momentum is still warm."
        )
    elif rate_signal:
        reason = (
            f"{display} has the most to gain from one more loop today. "
            f"An extra {best['extra_minutes']} minutes moves it forward."
        )
    elif best["tier_from"] == "minimum":
        reason = (
            f"You already protected {display} today. "
            f"One extra {best['extra_minutes']}-minute block turns protection into growth."
        )
    else:
        reason = (
            f"{display} is ready for one more clean step. "
            f"Add {best['extra_minutes']} minutes and push it into {best['tier_to'].title()}."
        )

    return {
        **best,
        "action": bonus_upgrade_action(
            best["canonical"], best["current_minutes"], best["minutes"]
        ),
        "start": recommendation_start(best["canonical"]),
        "mode": "Bonus Round",
        "priority": "Optional",
        "reason": reason,
        "is_bonus": True,
    }


def get_what_now_recommendation(state):
    """Score every unfinished task and return one concrete mobile-friendly move."""
    unfinished = [
        task for task in DAILY_TASKS
        if normalize_task_duration(task["canonical"], state.get("durations", {}).get(task["canonical"], 0)) == 0
    ]
    if not unfinished:
        return get_bonus_recommendation(state)

    history_brain = analyze_history()
    companion_state = build_companion_state()
    survival_mode = bool(weekend_survival_day() and completed_count(state) == 0)

    if len(unfinished) == 1:
        task = unfinished[0]
        minutes = recommendation_minutes(task["canonical"], state.get("energy"), survival_mode)
        return {
            "task": task,
            "canonical": task["canonical"],
            "minutes": minutes,
            "action": recommendation_action(task["canonical"], minutes),
            "start": recommendation_start(task["canonical"]),
            "mode": "Finish The Board",
            "priority": "Critical",
            "reason": f"Only {task['display']} remains, so closing the daily loop takes priority.",
            "score": 999,
        }

    candidates = []
    for task in unfinished:
        score, reasons = score_what_now_candidate(task, state, history_brain, companion_state, survival_mode)
        candidates.append((score, task, reasons))
    candidates.sort(key=lambda item: item[0], reverse=True)
    score, task, reasons = candidates[0]

    canonical = task["canonical"]
    minutes = recommendation_minutes(canonical, state.get("energy"), survival_mode)
    weakest = history_brain.get("weakest_habit", "Unknown")

    if survival_mode:
        mode = "Weekend Survival"
        priority = "Critical"
        reason = "The day is still at zero inside your danger window, so the goal is to restart the system—not optimize it."
    elif companion_state.get("mode") == "Urgent Recovery" and canonical == companion_state.get("focus_task"):
        mode = "Recovery Target"
        priority = "Critical"
        reason = f"{task['display']} is the active recovery focus and an unfinished task today."
    elif canonical == weakest:
        mode = "Pressure Target"
        priority = "High"
        reason = f"{task['display']} is unfinished and currently your weakest recent habit."
    else:
        mode = "Next Best Move"
        priority = "High" if score >= 140 else "Medium"
        reason = f"{task['display']} has the highest combined score from urgency, personal importance, and recent history."

    return {
        "task": task,
        "canonical": canonical,
        "minutes": minutes,
        "action": recommendation_action(canonical, minutes),
        "start": recommendation_start(canonical),
        "mode": mode,
        "priority": priority,
        "reason": reason,
        "score": score,
        "signals": reasons,
    }


def format_what_now(state):
    rec = get_what_now_recommendation(state)
    if not rec:
        return "NEXT MOVE\n\n✅ Core list complete. Clean finish is available."

    return (
        "NEXT MOVE\n\n"
        f"{recommendation_badge(rec)}\n"
        f"{rec['action']}\n\n"
        f"START\n{rec.get('start', recommendation_start(rec['canonical']))}\n\n"
        f"WHY\n{recommendation_reason_short(rec)}"
    )


def format_why_next(state):
    rec = get_what_now_recommendation(state)
    if not rec:
        return "WHY\n\nAll five core tasks are already logged."
    signals = rec.get("signals", [])
    signal_text = " • ".join(signals[:3]) if signals else recommendation_reason_short(rec)
    return (
        f"WHY {rec['task']['display'].upper()}?\n\n"
        f"{recommendation_reason_short(rec)}\n\n"
        f"Signals: {signal_text}"
    )


def get_logged_records_chronological(history=None, limit=7):
    history = history if isinstance(history, dict) else load_json(HISTORY_FILE, {})
    rows = get_recent_logged_history(history, limit=limit)
    return list(reversed(rows))


def record_mentions_growth_task(record, task_name):
    target = normalize_history_task_name(task_name).lower()
    task_names = {
        normalize_history_task_name(item.get("text", "")).lower()
        for item in record.get("tasks", []) if isinstance(item, dict)
    }
    missed_names = {
        normalize_history_task_name(item).lower()
        for item in record.get("missed_tasks", [])
    }
    return target in task_names or target in missed_names


def split_trend_rate(values):
    if not values:
        return 0, 0
    if len(values) == 1:
        rate = 100 if values[0] else 0
        return rate, rate
    midpoint = max(1, len(values) // 2)
    older, newer = values[:midpoint], values[midpoint:]
    older_rate = int((sum(older) / len(older)) * 100) if older else 0
    newer_rate = int((sum(newer) / len(newer)) * 100) if newer else older_rate
    return older_rate, newer_rate


def latest_value_streak(values, target):
    streak = 0
    for value in reversed(values):
        if value != target:
            break
        streak += 1
    return streak


def display_habit_name(task_name):
    task = normalize_history_task_name(task_name)
    labels = {
        "Complete Workout": "Exercise",
        "Coding Core Task": "Coding",
        "Networking / LinkedIn": "Networking",
        "Spanish Review": "Spanish",
        "Reading": "Reading",
    }
    return labels.get(task, task)


def build_task_trend_rows(limit=7):
    history = load_json(HISTORY_FILE, {})
    if not isinstance(history, dict):
        history = {}
    records = get_logged_records_chronological(history, limit=limit)
    rows = []

    for task_name in GROWTH_TASKS:
        values = []
        for _, record, _ in records:
            if not record_mentions_growth_task(record, task_name):
                continue
            values.append(1 if history_task_done(record, task_name) else 0)

        expected = len(values)
        done = sum(values)
        missed = expected - done
        rate = int((done / expected) * 100) if expected else 0
        older_rate, newer_rate = split_trend_rate(values)
        change = newer_rate - older_rate
        completed_streak = latest_value_streak(values, 1)
        missed_streak = latest_value_streak(values, 0)

        if expected < 2:
            status = "DATA BUILDING"
        elif change >= 20:
            status = "IMPROVING"
        elif change <= -20:
            status = "DECLINING"
        elif rate >= 75:
            status = "STRONG"
        elif rate <= 40:
            status = "NEEDS ATTENTION"
        else:
            status = "STABLE"

        if expected == 0:
            observation = "Not enough logged opportunities yet."
        elif missed_streak >= 2:
            observation = f"Missed {missed_streak} logged opportunities in a row."
        elif completed_streak >= 3:
            observation = f"Completed {completed_streak} logged opportunities in a row."
        elif status == "IMPROVING":
            observation = f"Improved from {older_rate}% to {newer_rate}%."
        elif status == "DECLINING":
            observation = f"Dropped from {older_rate}% to {newer_rate}%."
        elif rate >= 75:
            observation = "Holding as one of your strongest habits."
        elif rate <= 40:
            observation = f"Largest issue is consistency: {missed} missed opportunity{'ies' if missed != 1 else ''}."
        else:
            observation = "Moving, but not clearly improving yet."

        rows.append({
            "task": task_name, "expected": expected, "done": done, "missed": missed,
            "rate": rate, "older_rate": older_rate, "newer_rate": newer_rate,
            "change": change, "status": status, "completed_streak": completed_streak,
            "missed_streak": missed_streak, "observation": observation,
        })
    return rows


def trend_recommended_action(task_name):
    actions = {
        "Momentum": "Complete one small action to restart the chain.",
        "Coding": "Open the project and improve one function.",
        "Spanish": "Complete one short review loop.",
        "Exercise": "Complete the minimum workout.",
        "Networking": "Leave one meaningful comment.",
        "Reading": "Read one useful page.",
        "Trends": "Keep logging completed sessions.",
    }
    return actions.get(str(task_name), "Complete one small action today.")


def build_trend_alerts(rows, max_alerts=4):
    """Return compact, deduplicated Companion Insight cards.

    One card per habit. Warning cards come first; a positive card is kept at
    the bottom whenever the history contains a genuine improvement or streak.
    """
    usable = [row for row in rows if row.get("expected", 0) > 0]
    if not usable:
        return [{
            "level": "INFO", "task": "Trends",
            "message": "Log more finished sessions so useful patterns can form.",
            "meta": "History is still building.",
            "action": trend_recommended_action("Trends"),
        }]

    brain = analyze_history()
    cards_by_task = {}

    inactive = int(brain.get("inactive_days_recent", 0) or 0)
    if inactive >= 3:
        cards_by_task["Momentum"] = {
            "level": "WARNING", "task": "Momentum",
            "message": f"{inactive} inactive calendar days recently.",
            "meta": "The chain needs one clean restart.",
            "action": trend_recommended_action("Momentum"),
        }

    # Build one strongest warning card per habit instead of repeating the same task.
    warning_candidates = sorted(
        usable,
        key=lambda r: (r.get("missed_streak", 0), r.get("missed", 0), -r.get("rate", 0)),
        reverse=True,
    )
    for row in warning_candidates:
        task = display_habit_name(row["task"])
        if row.get("missed", 0) <= 0 and row.get("change", 0) > -20:
            continue

        details = []
        if row.get("missed_streak", 0) >= 2:
            details.append(f"Missed {row['missed_streak']} logged opportunities in a row")
        elif row.get("missed", 0) > 0:
            details.append(f"Missed {row['missed']} recent logged opportunit{'y' if row['missed'] == 1 else 'ies'}")

        if row.get("rate", 0) <= 40:
            details.append(f"{row['rate']}% completion rate")
        elif row.get("change", 0) <= -20:
            details.append(f"Dropped from {row['older_rate']}% to {row['newer_rate']}%")

        if not details:
            continue

        cards_by_task[task] = {
            "level": "WARNING", "task": task,
            "message": ". ".join(details) + ".",
            "meta": "This is the clearest recent gap.",
            "action": trend_recommended_action(task),
        }

    # Pick a real positive signal and reserve it for the final card.
    positive_candidates = []
    for row in usable:
        if row.get("change", 0) >= 20:
            positive_candidates.append((row.get("change", 0) + 100, "UP", row))
        elif row.get("completed_streak", 0) >= 3:
            positive_candidates.append((row.get("completed_streak", 0) * 10 + row.get("rate", 0), "STRONG", row))
        elif row.get("rate", 0) >= 75:
            positive_candidates.append((row.get("rate", 0), "STRONG", row))

    positive_card = None
    if positive_candidates:
        _, level, row = max(positive_candidates, key=lambda item: item[0])
        task = display_habit_name(row["task"])
        if level == "UP":
            message = f"Improved from {row['older_rate']}% to {row['newer_rate']}%."
            meta = "Recent sessions are stronger. Keep this momentum."
        elif row.get("completed_streak", 0) >= 3:
            message = f"Completed {row['completed_streak']} logged opportunities in a row."
            meta = f"Current completion rate: {row['rate']}%."
        else:
            message = f"Holding at a {row['rate']}% completion rate."
            meta = "This habit is becoming reliable."
        positive_card = {
            "level": level, "task": task, "message": message,
            "meta": meta, "action": trend_recommended_action(task),
        }
        # Do not repeat the same habit as both warning and positive.
        cards_by_task.pop(task, None)

    warnings = list(cards_by_task.values())
    warnings.sort(key=lambda card: 0 if card["task"] == "Momentum" else 1)

    # Leave room for the positive ending card.
    if positive_card:
        warnings = warnings[:max(0, max_alerts - 1)]
        result = warnings + [positive_card]
    else:
        result = warnings[:max_alerts]

    if not result:
        strongest = max(usable, key=lambda r: (r.get("rate", 0), r.get("done", 0)))
        task = display_habit_name(strongest["task"])
        result = [{
            "level": "STABLE", "task": task,
            "message": f"Holding at a {strongest['rate']}% completion rate.",
            "meta": "No major warning signal right now.",
            "action": trend_recommended_action(task),
        }]

    return result


def format_trend_alerts_answer():
    alerts = build_trend_alerts(build_task_trend_rows(limit=7))
    lines = ["COMPANION INSIGHTS", ""]
    icons = {"WARNING": "⚠", "UP": "↑", "STRONG": "✓", "STABLE": "◆", "INFO": "•"}
    for alert in alerts:
        lines.append(f"{icons.get(alert['level'], '•')} {alert['task']}: {alert['message']}")
        lines.append(f"Next: {alert.get('action', trend_recommended_action(alert['task']))}")
        lines.append("")
    return "\n".join(lines).strip()



# -----------------------------
# PHASE 4C - LIGHTWEIGHT MEMORY
# -----------------------------
def get_previous_logged_session():
    """Return the most recent saved session before today's Momentum date."""
    history = load_json(HISTORY_FILE, {})
    if not isinstance(history, dict):
        return None, {}

    today = today_key()
    candidates = []
    for date_key, record in history.items():
        if date_key == today or not isinstance(record, dict) or record.get("is_inactive"):
            continue
        try:
            datetime.strptime(date_key, "%Y-%m-%d")
        except Exception:
            continue
        candidates.append((date_key, record))

    if not candidates:
        return None, {}
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0]


def build_lightweight_memory():
    """Build factual memory from the previous saved session—no AI inference."""
    date_key, record = get_previous_logged_session()
    if not date_key:
        return {
            "available": False,
            "last_date": None,
            "last_completed": 0,
            "last_total": len(DAILY_TASKS),
            "last_xp": 0,
            "completed_tasks": [],
            "missed_tasks": [],
            "finished_all": False,
        }

    completed_tasks = []
    missed_tasks = []
    seen = set()
    for item in record.get("tasks", []):
        canonical = normalize_history_task_name(item.get("text") or item.get("display") or "")
        task = get_task(canonical)
        if not task or canonical in seen:
            continue
        seen.add(canonical)
        if item.get("done") or int(item.get("duration_minutes", 0) or 0) > 0:
            completed_tasks.append(task["display"])
        else:
            missed_tasks.append(task["display"])

    # Older records may only have missed_tasks or completion counts.
    if not missed_tasks:
        for value in record.get("missed_tasks", []):
            canonical = normalize_history_task_name(value)
            task = get_task(canonical)
            if task and task["display"] not in missed_tasks:
                missed_tasks.append(task["display"])

    if not completed_tasks and not missed_tasks:
        completed_count = int(record.get("completed", 0) or 0)
        completed_tasks = [t["display"] for t in DAILY_TASKS[:completed_count]]
        missed_tasks = [t["display"] for t in DAILY_TASKS[completed_count:]]

    return {
        "available": True,
        "last_date": date_key,
        "last_completed": int(record.get("completed", len(completed_tasks)) or 0),
        "last_total": int(record.get("total", len(DAILY_TASKS)) or len(DAILY_TASKS)),
        "last_xp": int(record.get("xp_earned", 0) or 0),
        "completed_tasks": completed_tasks,
        "missed_tasks": missed_tasks,
        "finished_all": bool(record.get("finished_all", False)),
        "energy": record.get("energy", "Unknown"),
        "location": record.get("location", "Unknown"),
    }


# -----------------------------
# PHASE 4A - COMPANION CORE
# -----------------------------
class CompanionCore:
    """Single read-only snapshot of Momentum's current brain state.

    The Core does not replace the mobile state or history files. It reads the
    existing trusted functions once, assembles their outputs, and gives every
    screen the same answer for mode, progress, next move, and insights.
    """

    def __init__(self, state):
        self.state = state
        self.snapshot = {}
        self.refresh()

    def refresh(self):
        history = analyze_history()
        companion = build_companion_state()
        recommendation = get_what_now_recommendation(self.state)
        trend_rows = build_task_trend_rows(limit=7)
        alerts = build_trend_alerts(trend_rows, max_alerts=4)
        memory = build_lightweight_memory()

        completed = []
        remaining = []
        for task in DAILY_TASKS:
            canonical = task["canonical"]
            duration = normalize_task_duration(
                canonical,
                self.state.get("durations", {}).get(canonical, 0),
            )
            (completed if duration > 0 else remaining).append(task["display"])

        self.snapshot = {
            "date": today_key(),
            "updated_at": datetime.now().strftime("%Y-%m-%d %I:%M:%S %p"),
            "energy": self.state.get("energy", "Normal"),
            "location": self.state.get("location", "Work"),
            "day_closed": bool(self.state.get("day_closed", False)),
            "progress": {
                "completed": len(completed),
                "total": len(DAILY_TASKS),
                "xp": xp_today(self.state),
                "xp_possible": max_daily_xp(),
                "completed_tasks": completed,
                "remaining_tasks": remaining,
            },
            "history": history,
            "companion": companion,
            "next_move": recommendation,
            "trend_rows": trend_rows,
            "alerts": alerts,
            "memory": memory,
            "bonus_status": (
                "active" if recommendation and recommendation.get("is_bonus")
                else "complete" if not remaining and all_energy_minimums_met(self.state)
                else "locked"
            ),
        }
        return self.snapshot

    @property
    def mode(self):
        return self.snapshot["companion"].get("mode", "Steady Build")

    @property
    def mood(self):
        return self.snapshot["companion"].get("mood", "Calm")

    @property
    def urgency(self):
        return self.snapshot["companion"].get("urgency", "Medium")

    def next_move(self):
        return self.snapshot.get("next_move")

    def insights(self):
        return self.snapshot.get("alerts", [])

    def history_summary(self):
        brain = self.snapshot["history"]
        strongest = display_task_name(brain.get("strongest_habit", "Unknown"))
        weakest = display_task_name(brain.get("weakest_habit", "Unknown"))
        return (
            "MOMENTUM HISTORY\n\n"
            f"State: {brain.get('current_state')}\n"
            f"Last logged: {brain.get('last_logged_day')}\n"
            f"Last result: {brain.get('last_result')}\n\n"
            f"7-day calendar average: {brain.get('average_recent_completion', 0)}%\n"
            f"Last 7 logged sessions: {brain.get('logged_session_average', 0)}%\n"
            f"Inactive days: {brain.get('inactive_days_recent', 0)}\n"
            f"Missed days: {brain.get('missed_days_recent', 0)}\n"
            f"Recovery days: {brain.get('recovery_days_recent', 0)}\n\n"
            f"Strongest habit: {strongest}\n"
            f"Weakest habit: {weakest}\n\n"
            f"Recommended move: {brain.get('recommended_move')}\n"
            f"Reason: {brain.get('reason')}"
        )

    def companion_state_summary(self):
        companion = self.snapshot["companion"]
        focus = display_task_name(companion.get("focus_task", "Unknown"))
        return (
            "COMPANION STATE\n\n"
            f"Mode: {self.mode}\n"
            f"Mood: {self.mood}\n"
            f"Urgency: {self.urgency}\n"
            f"Focus: {focus}\n\n"
            f"Reason: {companion.get('reason')}"
        )

    def memory(self):
        return self.snapshot.get("memory", {})

    def memory_summary(self):
        memory = self.memory()
        if not memory.get("available"):
            return "COMPANION MEMORY\n\nNo previous saved session is available yet."

        completed = ", ".join(memory.get("completed_tasks", [])) or "None"
        missed = ", ".join(memory.get("missed_tasks", [])) or "None"
        return (
            "COMPANION MEMORY\n\n"
            f"Last session: {memory.get('last_date')}\n"
            f"Result: {memory.get('last_completed')}/{memory.get('last_total')} • {memory.get('last_xp')} XP\n"
            f"Completed: {completed}\n"
            f"Left open: {missed}\n\n"
            f"Memory line: {self.opening_memory_line()}"
        )

    def opening_memory_line(self):
        memory = self.memory()
        if not memory.get("available"):
            return "This is the first reliable session in memory."
        completed = memory.get("last_completed", 0)
        total = memory.get("last_total", len(DAILY_TASKS))
        missed = memory.get("missed_tasks", [])
        if memory.get("finished_all") or (total and completed >= total):
            return "Last session was a clean finish. Protect that standard."
        if completed == total - 1 and missed:
            return f"Last session stopped at {completed}/{total}, with {missed[0]} still open."
        if completed == 0:
            return "Last session ended at zero. One completed loop changes the direction today."
        if missed:
            return f"Last session ended at {completed}/{total}. {missed[0]} was left open."
        return f"Last session ended at {completed}/{total}."

    def memory_connection_line(self):
        """Connect the current recommendation to the previous session when truthful."""
        memory = self.memory()
        rec = self.next_move()
        if not memory.get("available") or not rec:
            return ""
        task_name = rec["task"]["display"]
        if task_name in memory.get("missed_tasks", []):
            return f"{task_name} was also left open last session."
        if task_name in memory.get("completed_tasks", []):
            return f"You completed {task_name} last session; the Core is asking you to reinforce it."
        return ""

    def progress_comparison_line(self):
        memory = self.memory()
        if not memory.get("available"):
            return "No previous session is available for comparison yet."
        today_done = self.snapshot["progress"]["completed"]
        previous_done = int(memory.get("last_completed", 0) or 0)
        difference = today_done - previous_done
        if difference > 0:
            return f"Today finished {difference} task{'s' if difference != 1 else ''} ahead of the previous session."
        if difference < 0:
            return f"Today finished {abs(difference)} task{'s' if difference != -1 else ''} behind the previous session."
        return f"Today matched the previous session at {today_done}/{self.snapshot['progress']['total']}."

    def opening_message(self):
        progress = self.snapshot["progress"]
        recommendation = self.next_move()
        memory_line = self.opening_memory_line()
        if not recommendation:
            return f"Welcome back. {memory_line} All available tiers are complete. Nothing else is required today."

        action = recommendation["action"]
        if recommendation.get("is_bonus"):
            return (
                f"Welcome back. {memory_line} All minimums are protected. "
                f"Bonus target: {action}"
            )
        if progress["completed"] == 0:
            return f"Welcome back, Terrence. {memory_line} {self.mode} mode is active. {action}"
        return f"Welcome back. {memory_line} {self.mode} mode is active with {progress['completed']}/5 done. {action}"

    def next_move_summary(self):
        rec = self.next_move()
        if not rec:
            return "NEXT MOVE\n\n✅ Every available tier is complete. Nothing else is required today."
        if rec.get("is_bonus"):
            return (
                "BONUS TARGET\n\n"
                + recommendation_badge(rec)
                + "\n"
                + f"{rec['task']['display']}: {rec['current_minutes']}m → {rec['minutes']}m"
                + f"\n+{rec['xp_gain']} additional XP"
                + "\n\nWHY\n"
                + recommendation_reason_short(rec)
            )
        base = (
            "NEXT MOVE\n\n"
            + recommendation_badge(rec)
            + "\n"
            + rec["action"]
            + "\n\nSTART\n"
            + rec.get("start", recommendation_start(rec["canonical"]))
            + "\n\nWHY\n"
            + recommendation_reason_short(rec)
            + (("\n" + self.memory_connection_line()) if self.memory_connection_line() else "")
        )
        recall = self.recalled_quote_line()
        return base + (("\n\n" + recall) if recall else "")

    def why_summary(self):
        rec = self.next_move()
        if not rec:
            return "WHY\n\nEvery available tier is complete. Nothing else is required today."
        signals = rec.get("signals", [])
        if rec.get("is_bonus"):
            return (
                f"WHY BONUS {rec['task']['display'].upper()}?\n\n"
                f"{recommendation_reason_short(rec)}\n\n"
                f"Signals: {' • '.join(signals[:4])}"
            )
        signal_text = " • ".join(signals[:3]) if signals else recommendation_reason_short(rec)
        return (
            f"WHY {rec['task']['display'].upper()}?\n\n"
            f"{recommendation_reason_short(rec)}\n\n"
            f"Signals: {signal_text}"
            + (("\n\nMemory: " + self.memory_connection_line()) if self.memory_connection_line() else "")
        )

    def insights_summary(self):
        lines = ["COMPANION INSIGHTS", ""]
        icons = {"WARNING": "⚠", "UP": "↑", "STRONG": "✓", "STABLE": "◆", "INFO": "•"}
        for alert in self.insights():
            lines.append(f"{icons.get(alert['level'], '•')} {alert['task']}: {alert['message']}")
            lines.append(f"Next: {alert.get('action', trend_recommended_action(alert['task']))}")
            lines.append("")
        return "\n".join(lines).strip()

    def quote(self, category):
        return categorized_quote(self.state, category)

    def inspiration_response(self, command_text):
        return f"{quote_intro(command_text)}\n\n{self.quote('inspiration')}"

    def recalled_quote_line(self):
        """Let the Companion briefly reference its most recent inspiration once."""
        memory = self.state.get("last_quote") or {}
        if memory.get("category") != "inspiration" or memory.get("recalled"):
            return ""
        try:
            shown = datetime.fromisoformat(str(memory.get("shown_at", "")))
            if (datetime.now() - shown).total_seconds() > 30 * 60:
                return ""
        except (TypeError, ValueError):
            return ""

        remembered = compact_quote_memory(memory.get("text", ""))
        if not remembered:
            return ""
        memory["recalled"] = True
        self.state["last_quote"] = memory
        save_state(self.state)
        return f"Remember what I just told you:\n“{remembered}”\n\nNow let's turn it into one action."

    def task_saved_message(self, saved_tasks):
        saved_tasks = list(saved_tasks or [])
        if not saved_tasks:
            return "Progress saved. The Core is up to date."

        names = ", ".join(task["display"] for task in saved_tasks)
        earned = sum(
            task_xp(task["canonical"], self.state.get("durations", {}).get(task["canonical"], 0))
            for task in saved_tasks
        )
        rec = self.next_move()

        if not rec:
            return (
                f"✅ {names} saved • +{earned} XP. All five core tasks are logged. Clean finish is available."
                f"\n\n{self.quote('finished')}"
            )

        next_name = rec["task"]["display"]
        next_minutes = rec["minutes"]
        if self.mode == "Urgent Recovery":
            tone = "One loop is closed."
        elif self.mode == "Momentum Push":
            tone = "Momentum protected."
        else:
            tone = "Clean progress."
        return f"✅ {names} saved • +{earned} XP. {tone} Next: {next_name} for {next_minutes} minutes."

    def task_logged_message(self, canonical, minutes, previous_minutes=0):
        task = get_task(canonical)
        display = task["display"] if task else display_task_name(canonical)
        earned = task_xp(canonical, minutes)
        previous_xp = task_xp(canonical, previous_minutes)
        gained = max(0, earned - previous_xp)
        rec = self.next_move()

        if previous_minutes > 0 and minutes > previous_minutes:
            base = (
                f"Upgraded {display}: {previous_minutes}m → {minutes}m "
                f"• +{gained} XP."
            )
        else:
            base = f"Logged {display}: {DURATION_LABELS.get(minutes, str(minutes) + 'm')} • +{earned} XP."

        if rec and rec.get("is_bonus") and not self.state.get("bonus_round_announced"):
            self.state["bonus_round_announced"] = True
            save_state(self.state)
            return (
                base
                + "\n\nAll minimums are complete. Bonus Round unlocked."
                + f"\nBonus target: {rec['task']['display']} "
                  f"{rec['current_minutes']}m → {rec['minutes']}m "
                  f"for +{rec['xp_gain']} XP."
                + f"\n\n{self.quote('finished')}"
            )

        if not rec:
            if all_energy_minimums_met(self.state):
                return base + " Every available tier is complete. Nothing else is required today."
            return base

        if rec.get("is_bonus"):
            return (
                base
                + f" Next bonus: {rec['task']['display']} "
                  f"{rec['current_minutes']}m → {rec['minutes']}m "
                  f"for +{rec['xp_gain']} XP."
            )

        if rec["canonical"] == canonical:
            return base
        return base + f" Next: {rec['task']['display']} for {rec['minutes']} minutes."

    def end_day_message(self):
        progress = self.snapshot["progress"]
        completed = progress["completed"]
        xp = progress["xp"]
        comparison = self.progress_comparison_line()
        if completed == progress["total"]:
            return f"Day closed. Full loop complete: {completed}/{progress['total']} • {xp} XP. {comparison}"
        if completed == 0:
            return f"Day closed at 0/5. No lecture — tomorrow starts with one small action. {comparison}"
        focus = self.next_move()
        focus_name = focus["task"]["display"] if focus else "the next clean loop"
        if self.mode == "Urgent Recovery":
            return f"Day closed in recovery: {completed}/{progress['total']} • {xp} XP. {comparison} Tomorrow begins with {focus_name}."
        return f"Day closed: {completed}/{progress['total']} • {xp} XP. {comparison} Tomorrow's first target is {focus_name}."

    def core_summary(self):
        progress = self.snapshot["progress"]
        history = self.snapshot["history"]
        rec = self.next_move()
        next_name = rec["task"]["display"] if rec else "Clean finish"
        next_minutes = f"{rec['minutes']} minutes" if rec else "All tasks logged"
        return (
            "COMPANION CORE\n\n"
            f"Mode: {self.mode}\n"
            f"Mood: {self.mood}\n"
            f"Urgency: {self.urgency}\n"
            f"Energy: {self.snapshot['energy']}\n"
            f"Location: {self.snapshot['location']}\n\n"
            f"Progress: {progress['completed']}/{progress['total']}\n"
            f"XP: {progress['xp']}/{progress['xp_possible']}\n"
            f"Completed: {', '.join(progress['completed_tasks']) if progress['completed_tasks'] else 'None'}\n"
            f"Remaining: {', '.join(progress['remaining_tasks']) if progress['remaining_tasks'] else 'None'}\n\n"
            f"Next Move: {next_name} — {next_minutes}\n"
            f"History State: {history.get('current_state')}\n"
            f"Insights Ready: {len(self.insights())}\n"
            f"Bonus Status: {self.snapshot['bonus_status']}\n"
            f"Memory: {self.opening_memory_line()}\n\n"
            f"Updated: {self.snapshot['updated_at']}"
        )


def get_companion_core(state):
    """Create one consistent Core snapshot for the current Streamlit rerun."""
    return CompanionCore(state)

def format_tasks(state):
    lines = []
    for t in DAILY_TASKS:
        c = t["canonical"]
        d = state["durations"].get(c, 0)
        lines.append(f"{'✅' if d else '⭕'} {t['display']} — {DURATION_LABELS.get(d, '0m')}")
    return "\n".join(lines)



def backfill_date_from_text(text):
    """Resolve the intentionally small set of dates supported by the prototype."""
    low = str(text or "").lower()

    if re.search(r"\b(yesterday|last night)\b", low):
        return (momentum_now().date() - timedelta(days=1)).strftime("%Y-%m-%d")

    iso_match = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", low)
    if iso_match:
        try:
            resolved = datetime(
                int(iso_match.group(1)),
                int(iso_match.group(2)),
                int(iso_match.group(3)),
            ).date()
        except ValueError:
            return None

        # Backfill is intentionally history-only. Do not let it replace today's live board.
        if resolved >= momentum_now().date():
            return None
        return resolved.strftime("%Y-%m-%d")

    return None


def extract_backfill_tasks(text):
    """Extract one or more task/minute pairs from a natural backfill sentence."""
    low = str(text or "").lower()
    aliases = {
        "Coding Core Task": [
            "coding","code","coded","programming","programmed","python","worked on python"
        ],
        "Spanish Review": [
            "spanish","español","studied spanish","reviewed spanish"
        ],
        "Complete Workout": [
            "exercise","exercised","workout","worked out","jog","jogged","jogging","run","ran","jump rope",
            "pushups", "push-ups", "push ups", "pullups", "pull-ups",
            "squats", "ran", "running",
        ],
        "Networking / LinkedIn": [
            "networking","linkedin","commented","comment","connected","connection"
        ],
        "Reading": [
            "reading","read","book","finished reading"
        ],
    }

    matches = []
    for canonical, words in aliases.items():
        best = None
        for word in words:
            found = re.search(rf"\b{re.escape(word)}\b", low)
            if found and (best is None or found.start() < best.start()):
                best = found
        if best:
            matches.append((best.start(), best.end(), canonical))

    matches.sort(key=lambda row: row[0])
    results = []

    for index, (start, end, canonical) in enumerate(matches):
        next_start = matches[index + 1][0] if index + 1 < len(matches) else len(low)
        segment = low[end:next_start]

        minute_match = re.search(r"(\d{1,3})\s*(?:m|min|mins|minute|minutes)\b", segment)
        if not minute_match:
            # Also accept compact phrases such as "Spanish 20 and exercise 30".
            minute_match = re.search(r"\b(\d{1,3})\b", segment)

        if minute_match:
            minutes = normalize_task_duration(canonical, int(minute_match.group(1)))
        else:
            minutes = min(duration_options(canonical))

        if minutes > 0:
            results.append((canonical, minutes))

    # Keep only the final mention for each task.
    unique = {}
    for canonical, minutes in results:
        unique[canonical] = minutes
    return list(unique.items())


def is_backfill_request(text):
    low = str(text or "").lower()
    has_past_date = bool(
        re.search(r"\b(yesterday|last night)\b", low)
        or re.search(r"\b20\d{2}-\d{1,2}-\d{1,2}\b", low)
    )
    has_completion_language = any(
        word in low for word in
        ["did","done","finished","completed","logged","add","backfill",
         "coded","programmed","read","reading","exercise","exercised",
         "jogged","ran","spanish","networking","linkedin"]
    )
    return has_past_date and has_completion_language


def update_history_backfill(date_key, task_updates):
    """Merge task updates into one prior history record and recalculate its totals."""
    history = load_json(HISTORY_FILE, {})
    existing = history.get(date_key, {})
    if not isinstance(existing, dict):
        existing = {}

    existing_tasks = {}
    for item in existing.get("tasks", []):
        if not isinstance(item, dict):
            continue
        canonical = normalize_history_task_name(
            item.get("text") or item.get("display", "")
        )
        if canonical in {task["canonical"] for task in DAILY_TASKS}:
            existing_tasks[canonical] = dict(item)

    for canonical, minutes in task_updates:
        task = get_task(canonical)
        existing_tasks[canonical] = {
            "text": canonical,
            "display": task["display"],
            "done": True,
            "duration_minutes": minutes,
            "xp": task_xp(canonical, minutes),
        }

    tasks_payload = []
    missed = []
    completed = 0
    xp = 0

    for task in DAILY_TASKS:
        canonical = task["canonical"]
        item = existing_tasks.get(canonical, {})
        minutes = normalize_task_duration(
            canonical, item.get("duration_minutes", 0)
        )
        done = minutes > 0
        earned = task_xp(canonical, minutes) if done else 0

        if done:
            completed += 1
            xp += earned
        else:
            missed.append(canonical)

        tasks_payload.append({
            "text": canonical,
            "display": task["display"],
            "done": done,
            "duration_minutes": minutes,
            "xp": earned,
        })

    history[date_key] = {
        "date": date_key,
        "saved_at": datetime.now().strftime("%Y-%m-%d %I:%M %p"),
        "location": existing.get("location", "Away"),
        "energy": existing.get("energy", "Normal"),
        "completed": completed,
        "total": len(DAILY_TASKS),
        "finished_all": completed == len(DAILY_TASKS),
        "missed_tasks": missed,
        "tasks": tasks_payload,
        "xp_earned": xp,
        "xp_possible": max_daily_xp(),
        "day_closed": bool(existing.get("day_closed", False)),
        "backfilled": True,
    }
    save_json(HISTORY_FILE, history)
    return history[date_key]



def classify_history_record(record):
    """Apply the mobile closeout labels to a saved history record."""
    if not isinstance(record, dict):
        return "WARNING"

    energy = str(record.get("energy", "Normal") or "Normal").title()
    completed = int(record.get("completed", 0) or 0)
    minimums_met = 0

    for item in record.get("tasks", []):
        if not isinstance(item, dict):
            continue
        canonical = normalize_history_task_name(
            item.get("text") or item.get("display", "")
        )
        if canonical not in {task["canonical"] for task in DAILY_TASKS}:
            continue
        minutes = normalize_task_duration(
            canonical, item.get("duration_minutes", 0)
        )
        if minutes >= minimum_required_minutes(canonical, energy):
            minimums_met += 1

    if completed == len(DAILY_TASKS) and minimums_met == len(DAILY_TASKS):
        return "MISSION COMPLETE"
    if energy == "Low" and completed >= 2:
        return "RECOVERY DAY"
    if completed >= 4 and minimums_met >= 4:
        return "SOLID DAY"
    if completed <= 1:
        return "WARNING"
    return "MORE IN THE TANK"


def load_history_record(date_key):
    history = load_json(HISTORY_FILE, {})
    record = history.get(date_key, {})
    return record if isinstance(record, dict) else {}


def backfill_from_chat(text):
    date_key = backfill_date_from_text(text)
    if not date_key:
        return (
            "I can backfill yesterday or a past date written as YYYY-MM-DD. "
            "I won't guess the date or alter today's live board."
        )

    updates = extract_backfill_tasks(text)
    if not updates:
        return (
            "I found the date, but not a task and duration. Try: "
            "Yesterday I did exercise 20m."
        )

    previous_record = load_history_record(date_key)
    previous_status = classify_history_record(previous_record) if previous_record else None
    previous_completed = int(previous_record.get("completed", 0) or 0) if previous_record else 0

    record = update_history_backfill(date_key, updates)
    new_status = classify_history_record(record)

    date_label = "Yesterday" if date_key == (
        momentum_now().date() - timedelta(days=1)
    ).strftime("%Y-%m-%d") else date_key

    changed_lines = []
    for canonical, minutes in updates:
        task = get_task(canonical)
        duration_label = DURATION_LABELS.get(minutes, str(minutes) + "m")
        changed_lines.append(
            f"✓ {task['display']}\n"
            f"{duration_label} • +{task_xp(canonical, minutes)} XP"
        )

    companion_note = "Good catch. That effort deserves to count."

    if record["completed"] == len(DAILY_TASKS) and previous_completed < len(DAILY_TASKS):
        companion_note = (
            f"Looks like {date_label.lower()} was finished after all. "
            "I'm glad we gave it the ending it deserved."
        )
    elif previous_status and previous_status != new_status:
        companion_note = (
            f"{date_label} moved from {previous_status.title()} "
            f"to {new_status.title()}. Nice save."
        )

    return (
        f"{date_label} updated.\n\n"
        + "\n\n".join(changed_lines)
        + f"\n\n{date_label} is now "
          f"{record['completed']}/{record['total']} tasks • {record['xp_earned']} XP"
        + f"\n\n✦ Companion\n{companion_note}"
    )


def handle_command(text, state):
    cleaned = (text or "").strip()
    if not cleaned:
        return "Type a command or tap a suggestion."
    low = cleaned.lower()

    if "clear chat" in low or "reset chat" in low:
        clear_chat(state)
        return "Chat cleared. Fresh board."

    core = get_companion_core(state)

    if is_backfill_request(cleaned):
        return backfill_from_chat(cleaned)

    if any(x in low for x in ["quote", "motivate", "inspire", "wake me up", "get me going", "don't feel", "dont feel"]):
        return core.inspiration_response(cleaned)

    if low in {"core", "companion core", "core state", "brain core"}:
        return core.core_summary()

    if low in {"memory", "remember", "last session", "what do you remember"}:
        return core.memory_summary()

    if is_history_analysis_request(low):
        return core.history_summary()

    if is_companion_state_request(low):
        return core.companion_state_summary()

    if "alert" in low or "warning" in low or "trend" in low:
        return core.insights_summary()

    if "help" in low or "command" in low:
        return (
            "HELP / COMMANDS\n\n"
            "next — gives your brain-routed next move\n"
            "goal / goals — also gives your next move\n"
            "why — explains the current recommendation\n"
            "tasks — shows today's task status\n"
            "alerts — shows compact trend signals\n"
            "history — analyzes your saved momentum history\n"
            "mode — shows the Companion's current operating state\n"
            "core — shows the single Companion Core snapshot\n"
            "memory — shows the previous session the Core remembers\n"
            "log exercise 20 — logs a task\n"
            "log Spanish 20 — logs Spanish today\n"
            "Yesterday I did exercise 20m — updates prior history\n"
            "2026-07-18 I did reading 10m — backfills a past date\n"
            "wake me up — pulls an inspiration quote\n"
            "end day — closes only after all five tasks are complete\n\n"
            "You can also say it naturally, like: I finished reading for 10 minutes."
        )

    if any(x in low for x in ["start", "open", "launch", "begin"]) and not any(x in low for x in ["done", "did", "finished", "complete", "completed", "logged", "log"]):
        canonical = task_by_words(low)
        if canonical:
            display = get_task(canonical)["display"]
            if canonical in TASK_LINKS:
                return f"Open {display} from the Tasks tab for now. Link is ready there."
            mins = min(duration_options(canonical))
            return f"Start {display} for {mins} minutes. When done, tell me: log {display.lower()} {mins}."


    if "task" in low or "progress" in low:
        return "TODAY'S TASKS\n\n" + format_tasks(state)

    if low in {"why", "why this", "why that", "why this goal", "why this move"}:
        return core.why_summary()

    # Mobile shortcut: any message containing next, goal, or goals routes here.
    if re.search(r"\b(next|goal|goals)\b", low) or any(phrase in low for phrase in [
        "what now", "what should i focus", "recommend a task",
        "give me a mission", "where should i put time"
    ]):
        return core.next_move_summary()

    if "end day" in low or "close day" in low:
        if completed_count(state) < len(DAILY_TASKS):
            return core.quote("early_quit")
        state["day_closed"] = True
        save_state(state)
        save_progress_to_history(state)
        return get_companion_core(state).end_day_message()

    canonical = task_by_words(low)
    if canonical and any(w in low for w in ["done", "did", "finished", "complete", "completed", "logged", "log"]):
        mins = minutes_from_text(low, canonical)
        previous_minutes = normalize_task_duration(
            canonical, state["durations"].get(canonical, 0)
        )
        state["durations"][canonical] = max(previous_minutes, mins)
        final_minutes = state["durations"][canonical]
        save_state(state); save_progress_to_history(state)
        return get_companion_core(state).task_logged_message(
            canonical, final_minutes, previous_minutes
        )

    return "Try: next, why, tasks, history, quote, log Spanish 20, Yesterday I did exercise 20m, or end day."


def add_chat(state, who, msg):
    state.setdefault("chat_log", [])
    state["chat_log"].append({"who": who, "msg": msg, "time": datetime.now().strftime("%I:%M %p")})
    state["chat_log"] = state["chat_log"][-8:]
    save_state(state)



def quick_log_mission(state, recommendation, minutes):
    """Log the current Core-selected mission directly from Home."""
    if not recommendation:
        return

    canonical = recommendation["canonical"]
    minimums_were_complete = all_energy_minimums_met(state)
    previous_minutes = normalize_task_duration(
        canonical, state.get("durations", {}).get(canonical, 0)
    )
    minutes = normalize_task_duration(canonical, minutes)
    if minutes <= 0 or minutes <= previous_minutes:
        return

    state.setdefault("durations", {})[canonical] = minutes
    collapsed = set(state.get("collapsed_tasks", []))
    collapsed.add(canonical)
    state["collapsed_tasks"] = list(collapsed)
    save_state(state)
    save_progress_to_history(state)

    if not minimums_were_complete and all_energy_minimums_met(state):
        st.session_state["bonus_unlock_animation"] = True

    refreshed_core = get_companion_core(state)
    saved_task = get_task(canonical)
    message = refreshed_core.task_logged_message(canonical, minutes, previous_minutes)
    add_chat(state, "Companion", message)

    st.session_state["animate_last_reply"] = True
    gained = task_xp(canonical, minutes) - task_xp(canonical, previous_minutes)
    action_word = "upgraded" if previous_minutes > 0 else "logged"
    st.session_state["quick_mission_flash"] = (
        f"✓ {saved_task['display'] if saved_task else display_task_name(canonical)} "
        f"{action_word} • +{gained} XP"
    )

    next_rec = refreshed_core.next_move()
    if not minimums_were_complete and all_energy_minimums_met(state):
        spoken = spoken_companion_line("minimums_complete")
        event_key = f"minimums_complete_{today_key()}"
    elif next_rec and next_rec.get("is_bonus"):
        spoken = spoken_companion_line(
            "bonus_target",
            task=next_rec["task"]["display"],
            minutes=next_rec.get("extra_minutes", 0),
        )
        event_key = f"bonus_target_{today_key()}_{next_rec['canonical']}_{next_rec['minutes']}"
    elif next_rec:
        spoken = spoken_companion_line(
            "task_logged",
            task=saved_task["display"] if saved_task else display_task_name(canonical),
            next_task=next_rec["task"]["display"],
        )
        event_key = f"task_logged_{today_key()}_{canonical}_{minutes}"
    else:
        spoken = spoken_companion_line(
            "task_logged",
            task=saved_task["display"] if saved_task else display_task_name(canonical),
        )
        event_key = f"task_logged_{today_key()}_{canonical}_{minutes}"
    queue_companion_voice(state, spoken, event_key, autoplay=True)
    st.rerun()


def render_quick_mission_controls(state, recommendation):
    """Compact one-tap duration buttons under the Next Move card."""
    if not recommendation:
        return

    canonical = recommendation["canonical"]
    options = duration_options(canonical)
    if not options:
        return

    with st.container(key="quick_mission_controls"):
        if recommendation.get("is_bonus"):
            extra = recommendation["extra_minutes"]
            target = recommendation["minutes"]
            st.markdown("<div class='quickMissionHint'>Bonus action</div>", unsafe_allow_html=True)
            if st.button(
                f"✨ Add {extra}m • +{recommendation['xp_gain']} XP",
                key=f"quick_bonus_{canonical}_{target}",
                use_container_width=True,
            ):
                quick_log_mission(state, recommendation, target)
            return

        st.markdown("<div class='quickMissionHint'>Quick log this mission</div>", unsafe_allow_html=True)
        columns = st.columns(len(options))
        for column, minutes in zip(columns, options):
            label = DURATION_LABELS.get(minutes, f"{minutes}m")
            with column:
                if st.button(
                    f"✓ {label}",
                    key=f"quick_log_{canonical}_{minutes}",
                    use_container_width=True,
                ):
                    quick_log_mission(state, recommendation, minutes)

def render_header(state, animate_mission=False):
    comp = completed_count(state)
    percent = int((comp / len(DAILY_TASKS)) * 100)
    core = get_companion_core(state)
    mode = core.mode
    urgency = core.urgency
    st.markdown(f"""
    <div class="hero">
      <div class="logoRow"><div class="logo">M</div><div><div class="title">MOMENTUM</div><div class="sub">Your daily system. Your future self.</div></div></div>
    </div>
    """, unsafe_allow_html=True)
    ts = totals()
    st.markdown(f"""
    <div class="statGrid">
      <div class="stat"><div class="t">PROGRESS</div><div class="n">{comp}/5</div></div>
      <div class="stat"><div class="t">STREAK</div><div class="n">{ts['streak']}</div></div>
      <div class="stat"><div class="t">EXP</div><div class="n">{xp_today(state)}</div></div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("<div class='progressWrap'><div class='progressTitle'>TODAY'S PROGRESS</div>", unsafe_allow_html=True)
    st.progress(percent / 100)
    st.markdown(
        f"<div class='progressMeta'><span>{percent}% complete</span><span>{xp_today(state)} / {max_daily_xp()} XP</span></div></div>",
        unsafe_allow_html=True,
    )

    flash = st.session_state.pop("quick_mission_flash", "")
    if flash:
        st.markdown(f"<div class='quickMissionFlash'>{html.escape(flash)}</div>", unsafe_allow_html=True)

    recommendation = core.next_move()

    bonus_unlock = st.session_state.pop("bonus_unlock_animation", False)
    if bonus_unlock and recommendation and recommendation.get("is_bonus"):
        st.markdown(
            "<div class='bonusUnlock'>✨ Bonus Round Unlocked</div>",
            unsafe_allow_html=True,
        )

    if recommendation:
        focus = recommendation["task"]
        focus_minutes = recommendation["minutes"]
        is_bonus = bool(recommendation.get("is_bonus"))
        focus_reward = recommendation.get("xp_gain", task_xp(focus["canonical"], focus_minutes))
        focus_label = "Bonus Target" if is_bonus else "Companion Target"
        focus_time = (
            f"{recommendation['current_minutes']}m → {focus_minutes}m"
            if is_bonus else f"{focus_minutes} minutes"
        )
        st.markdown(
            f"""
            <div class='focusCard {'animateMission' if animate_mission else ''}'>
              <div class='focusLabel'>{focus_label}</div>
              <div class='focusMain'>
                <div>
                  <div class='focusTask'>{'✨' if is_bonus else '🎯'} {focus['display']}</div>
                  <div class='focusTime'>{focus_time}</div>
                </div>
                <div class='focusReward'>+{focus_reward} XP</div>
              </div>
              <div class='missionBadge'>{recommendation_badge(recommendation)}</div>
              <div class='missionStart'>Start: {recommendation.get('start', recommendation_start(focus['canonical']))}</div>
              <div class='missionReason'>{recommendation_reason_short(recommendation)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        render_quick_mission_controls(state, recommendation)
    else:
        bonus_complete = all_energy_minimums_met(state) and all(
            next_duration_tier(
                task["canonical"],
                state.get("durations", {}).get(task["canonical"], 0),
            ) is None
            for task in DAILY_TASKS
        )

        if bonus_complete:
            st.markdown(
                """
                <div class='bonusCompleteCard'>
                  <div class='bonusCompleteLabel'>Final Reward</div>
                  <div class='bonusCompleteTitle'>✨ BONUS COMPLETE</div>
                  <div class='bonusCompleteText'>
                    Every available upgrade has been completed.<br>
                    <strong>Today's journey is complete.</strong>
                  </div>
                </div>
                <div class='bonusFinalWord'>
                  <div class='label'>✦ Companion</div>
                  Every promise was protected.<br>
                  Every available upgrade was earned.<br><br>
                  <b>There's nothing left to prove tonight.</b><br>
                  Go enjoy your evening.<br>
                  We'll continue from here tomorrow.
                </div>
                """,
                unsafe_allow_html=True,
            )

            if st.button(
                "🌙 See You Tomorrow",
                use_container_width=True,
                type="primary",
                key="bonus_complete_see_you_tomorrow",
            ):
                state["day_closed"] = True
                state["last_closeout"] = {
                    "status": "BONUS COMPLETE",
                    "closed_at": datetime.now().isoformat(timespec="seconds"),
                    "tomorrow_focus": analyze_history().get("weakest_habit", "Reading"),
                }
                save_state(state)
                save_progress_to_history(state)
                add_chat(
                    state,
                    "Companion",
                    "Every promise was protected. Every available upgrade was earned. "
                    "There's nothing left to prove tonight. See you tomorrow.",
                )
                queue_companion_voice(
                    state, spoken_companion_line("bonus_complete"),
                    f"bonus_complete_{today_key()}", autoplay=True
                )
                st.success("🌙 See you tomorrow.")
                st.rerun()
        else:
            st.markdown(
                """
                <div class='focusCard'>
                  <div class='focusLabel'>Companion Target</div>
                  <div class='focusMain'>
                    <div>
                      <div class='focusTask'>✅ Core list complete</div>
                      <div class='focusTime'>Clean finish available</div>
                    </div>
                    <div class='focusReward'>All 5 done</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )



def build_opening_message(state):
    return get_companion_core(state).opening_message()


def ensure_opening_chat(state):
    if not state.get("chat_log"):
        state["chat_log"] = [{
            "who": "Companion",
            "msg": build_opening_message(state),
            "time": datetime.now().strftime("%I:%M %p"),
        }]
        save_state(state)

    # Speak the opening once per browser session/day. Browser autoplay rules may
    # require the first tap; Replay Last remains available in Companion settings.
    core = get_companion_core(state)
    rec = core.next_move()
    if rec:
        opening_line = spoken_companion_line(
            "opening", mode=core.mode, task=rec["task"]["display"], minutes=rec["minutes"]
        )
    else:
        opening_line = spoken_companion_line("opening", mode=core.mode)
    queue_companion_voice(state, opening_line, f"opening_{today_key()}", autoplay=True)


def clear_chat(state):
    state["chat_log"] = [{
        "who": "Companion",
        "msg": build_opening_message(state),
        "time": datetime.now().strftime("%I:%M %p"),
    }]
    save_state(state)


def render_chat_log(state):
    rows = []
    chat_items = state.get("chat_log", [])[-9:]
    animate_last = bool(st.session_state.get("animate_last_reply"))

    for index, item in enumerate(chat_items):
        who = item.get("who", "")
        raw_msg = str(item.get("msg", ""))
        cls = "you" if who.lower() == "you" else "companion"

        is_animated_reply = (
            animate_last
            and index == len(chat_items) - 1
            and cls == "companion"
        )

        if is_animated_reply:
            parts = re.split(r"(\s+)", raw_msg)
            animated_parts = []
            word_number = 0

            for part in parts:
                if not part:
                    continue
                if part.isspace():
                    animated_parts.append(part.replace("\n", "<br>"))
                else:
                    delay = min(word_number * 0.045, 1.8)
                    animated_parts.append(
                        f"<span class='word' style='animation-delay:{delay:.3f}s'>"
                        f"{html.escape(part)}</span>"
                    )
                    word_number += 1

            msg = "".join(animated_parts)
            extra_class = " newReply"
        else:
            msg = html.escape(raw_msg).replace("\n", "<br>")
            extra_class = ""

        rows.append(
            f"<div class='chatMsg {cls}{extra_class}'>"
            f"<span class='chatWho'>{html.escape(who)}</span>"
            f"<span class='chatText'>{msg}</span>"
            f"</div>"
        )

    st.markdown(
        "<div class='chatBox' id='momentum-chat-box'>" + "".join(rows) + "</div>",
        unsafe_allow_html=True
    )

    if animate_last:
        st.session_state["animate_last_reply"] = False


def auto_scroll_chat():
    components.html(
        """
        <script>
        (() => {
          const parentDoc = window.parent.document;

          const getChatBox = () => {
            const boxes = parentDoc.querySelectorAll('.chatBox');
            return boxes.length ? boxes[boxes.length - 1] : null;
          };

          const forceBottom = () => {
            const box = getChatBox();
            if (!box) return false;

            box.scrollTop = box.scrollHeight;
            box.scrollTo({
              top: box.scrollHeight,
              behavior: 'auto'
            });
            return true;
          };

          // Streamlit can finish painting after this component loads,
          // so keep checking briefly instead of firing only once.
          const delays = [0, 50, 100, 180, 300, 500, 750, 1000, 1400, 1900];
          delays.forEach(delay => setTimeout(forceBottom, delay));

          // Follow any size/content changes while the newest reply animates.
          const attachObserver = () => {
            const box = getChatBox();
            if (!box) {
              setTimeout(attachObserver, 80);
              return;
            }

            const observer = new MutationObserver(() => {
              requestAnimationFrame(forceBottom);
            });

            observer.observe(box, {
              childList: true,
              subtree: true,
              characterData: true
            });

            const resizeObserver = new ResizeObserver(() => {
              requestAnimationFrame(forceBottom);
            });
            resizeObserver.observe(box);

            // Avoid leaving observers around forever after reruns.
            setTimeout(() => {
              observer.disconnect();
              resizeObserver.disconnect();
            }, 2500);
          };

          attachObserver();
        })();
        </script>
        """,
        height=0,
    )


def render_home(state):
    ensure_opening_chat(state)

    # The old split opening/closing homeShell tags produced the empty purple strip.
    render_chat_log(state)
    auto_scroll_chat()

    with st.form("chat_form", clear_on_submit=True):
        user_msg = st.text_input(
            "Chat",
            placeholder="Try: next • goal • why • log Spanish 20",
            label_visibility="collapsed"
        )
        sent = st.form_submit_button("➤ Send", use_container_width=True, type="primary")

        clear_left, clear_center, clear_right = st.columns([1, 2, 1])
        with clear_center:
            cleared = st.form_submit_button("Clear chat", use_container_width=True)

    if sent and user_msg.strip():
        add_chat(state, "You", user_msg)
        reply = handle_command(user_msg, state)
        add_chat(state, "Companion", reply)

        low = user_msg.lower()
        if any(x in low for x in ["quote", "motivate", "inspire", "wake me up", "get me going", "don't feel", "dont feel"]):
            quote_text = reply.split("\n\n", 1)[-1]
            queue_companion_voice(
                state, spoken_companion_line("quote", quote=quote_text),
                f"quote_{hashlib.sha1(reply.encode('utf-8')).hexdigest()}", autoplay=True
            )
        elif "end day" in low or "close day" in low:
            if completed_count(state) < len(DAILY_TASKS):
                queue_companion_voice(
                    state, spoken_companion_line("early_quit", quote=reply),
                    f"early_quit_{today_key()}_{completed_count(state)}", autoplay=True
                )
            else:
                queue_companion_voice(
                    state, spoken_companion_line("end_day", status="Mission complete"),
                    f"end_day_{today_key()}", autoplay=True
                )
        elif re.search(r"\b(next|goal|goals)\b", low) or "what now" in low:
            rec = get_companion_core(state).next_move()
            if rec:
                queue_companion_voice(
                    state,
                    spoken_companion_line("target", task=rec["task"]["display"], minutes=rec["minutes"]),
                    f"target_{today_key()}_{rec['canonical']}_{rec['minutes']}",
                    autoplay=False,
                )

        st.session_state["animate_last_reply"] = True
        st.rerun()

    if cleared:
        st.session_state["animate_last_reply"] = False
        clear_chat(state)
        st.rerun()



def load_workout_pbs():
    raw = load_json(WORKOUT_PB_FILE, {})
    if not isinstance(raw, dict):
        raw = {}

    cleaned = {}
    for exercise in WORK_EXERCISES:
        name = exercise["name"]
        try:
            cleaned[name] = max(0, int(raw.get(name, 0) or 0))
        except Exception:
            cleaned[name] = 0
    return cleaned


def workout_summary(state):
    rows = state.get("workout", {})
    completed = sum(1 for exercise in WORK_EXERCISES if rows.get(exercise["name"], {}).get("done"))
    return f"{completed} exercise{'s' if completed != 1 else ''} logged" if completed else "Workout not started"


@st.dialog("🏋️ Log workout", width="small")
def render_workout_dialog(state):
    pbs = load_workout_pbs()
    workout = state.setdefault("workout", {})

    header_work, header_s1, header_s2, header_pb = st.columns([1.28, 0.62, 0.62, 0.36])
    with header_work:
        st.markdown("<div class='workoutGridHeader left'>EXERCISE</div>", unsafe_allow_html=True)
    with header_s1:
        st.markdown("<div class='workoutGridHeader'>SET 1</div>", unsafe_allow_html=True)
    with header_s2:
        st.markdown("<div class='workoutGridHeader'>SET 2</div>", unsafe_allow_html=True)
    with header_pb:
        st.markdown("<div class='workoutGridHeader'>PB</div>", unsafe_allow_html=True)

    pending = {}

    for exercise in WORK_EXERCISES:
        name = exercise["name"]
        unit = exercise["unit"]
        icon = exercise.get("icon", "•")
        saved = workout.setdefault(name, {"done": False, "set1": 0, "set2": 0})

        work_col, set1_col, set2_col, pb_col = st.columns(
            [1.28, 0.62, 0.62, 0.36],
            vertical_alignment="center",
        )

        with work_col:
            done = st.checkbox(
                f"{icon}  {name}",
                value=bool(saved.get("done", False)),
                key=f"work_done_{name}",
            )

        with set1_col:
            set1 = st.number_input(
                f"{name} set 1",
                min_value=0,
                max_value=999,
                value=int(saved.get("set1", 0) or 0),
                step=1,
                key=f"work_set1_{name}",
                label_visibility="collapsed",
            )

        with set2_col:
            set2 = st.number_input(
                f"{name} set 2",
                min_value=0,
                max_value=999,
                value=int(saved.get("set2", 0) or 0),
                step=1,
                key=f"work_set2_{name}",
                label_visibility="collapsed",
            )

        with pb_col:
            suffix = "m" if unit == "m" and pbs.get(name, 0) else ""
            pb_value = f"{pbs.get(name, 0)}{suffix}" if pbs.get(name, 0) else "—"
            st.markdown(f"<div class='workoutPB'>{pb_value}</div>", unsafe_allow_html=True)

        pending[name] = {
            "done": done,
            "set1": int(set1),
            "set2": int(set2),
        }

    if st.button("Save workout", key="save_workout_log", use_container_width=True, type="primary"):
        new_pb_count = 0

        for exercise in WORK_EXERCISES:
            name = exercise["name"]
            row = pending[name]
            workout[name] = row

            if row["done"] and row["set1"] > pbs.get(name, 0):
                pbs[name] = row["set1"]
                new_pb_count += 1

        state["workout"] = workout
        save_state(state)
        save_json(WORKOUT_PB_FILE, pbs)

        if new_pb_count:
            st.toast(f"Workout saved • {new_pb_count} new PB{'s' if new_pb_count != 1 else ''}!")
        else:
            st.toast("Workout saved.")

        st.rerun()


def workout_log_button(key):
    if st.button("▾ Log", key=key, use_container_width=True):
        render_workout_dialog(state)



def render_tasks(state):
    st.markdown("<div class='controlLabel'>ENERGY</div>", unsafe_allow_html=True)
    energy_current = state.get("energy", "Normal")
    energy = st.radio(
        "Energy",
        ENERGY_OPTIONS,
        index=ENERGY_OPTIONS.index(energy_current) if energy_current in ENERGY_OPTIONS else 1,
        horizontal=True,
        key="energy_control",
        label_visibility="collapsed",
    )

    st.markdown("<div class='controlLabel'>LOCATION</div>", unsafe_allow_html=True)
    location_current = state.get("location", "Work")
    location = st.radio(
        "Location",
        LOCATION_OPTIONS,
        index=LOCATION_OPTIONS.index(location_current) if location_current in LOCATION_OPTIONS else 0,
        horizontal=True,
        key="location_control",
        label_visibility="collapsed",
    )

    if energy != state.get("energy") or location != state.get("location"):
        state["energy"] = energy
        state["location"] = location
        save_state(state)

    collapsed = set(state.get("collapsed_tasks", []))

    for t in DAILY_TASKS:
        c = t["canonical"]
        current = normalize_task_duration(c, state["durations"].get(c, 0))

        app_link = ""
        if c in TASK_LINKS:
            app_link = (
                f"<a class='taskAppLink' href='{TASK_LINKS[c]}' target='_blank' "
                f"rel='noopener noreferrer'>↗ App</a>"
            )

        # Once Save Progress is pressed, completed tasks become one compact editable row.
        if current > 0 and c in collapsed:
            with st.container(border=True):
                st.markdown("<span class='completedTaskMarker'></span>", unsafe_allow_html=True)

                if c == "Complete Workout":
                    info_col, log_col, edit_col = st.columns([2.5, 0.82, 0.9], vertical_alignment="center")
                elif c in TASK_LINKS:
                    info_col, app_col, edit_col = st.columns([2.6, 0.8, 0.9], vertical_alignment="center")
                else:
                    info_col, edit_col = st.columns([3.4, 1], vertical_alignment="center")
                    app_col = None

                with info_col:
                    extra_summary = ""
                    if c == "Complete Workout":
                        extra_summary = f"<div class='workoutSavedSummary'>{workout_summary(state)}</div>"

                    st.markdown(
                        f"""
                        <div class='completedTaskName'>✅ {t['display']}</div>
                        <div class='completedTaskReceipt'>{DURATION_LABELS.get(current)} • +{task_xp(c, current)} XP</div>
                        {extra_summary}
                        """,
                        unsafe_allow_html=True,
                    )

                if c == "Complete Workout":
                    with log_col:
                        if st.button("▾ Log", key=f"open_workout_saved_{c}", use_container_width=True):
                            render_workout_dialog(state)
                elif app_col is not None:
                    with app_col:
                        st.link_button("↗ App", TASK_LINKS[c], use_container_width=True)

                with edit_col:
                    if st.button("✎ Edit", key=f"edit_{c}", use_container_width=True):
                        state["collapsed_tasks"] = [x for x in state.get("collapsed_tasks", []) if x != c]
                        save_state(state)
                        st.rerun()
            continue

        # Exercise uses the same dark-blue card, with Log aligned right like Spanish App.
        if c == "Complete Workout":
            with st.container(key="exercise_task_card"):
                info_col, log_col = st.columns([3.18, 0.82], vertical_alignment="center")

                with info_col:
                    st.markdown(
                        f"""
                        <div class='taskName'>{'✅' if current else '⭕'} {t['display']}</div>
                        <div class='muted'>{DURATION_LABELS.get(current)} • +{task_xp(c, current)} XP</div>
                        <div class='workoutSavedSummary'>{workout_summary(state)}</div>
                        """,
                        unsafe_allow_html=True,
                    )

                with log_col:
                    if st.button("▾ Log", key=f"open_workout_{c}", use_container_width=True):
                        render_workout_dialog(state)

        else:
            st.markdown(
                f"""
                <div class='taskCard'>
                  <div class='taskTopRow'>
                    <div class='taskName'>{'✅' if current else '⭕'} {t['display']}</div>
                    {app_link}
                  </div>
                  <div class='muted'>{DURATION_LABELS.get(current)} • +{task_xp(c, current)} XP</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        options = [0] + duration_options(c)
        selected = st.radio(
            f"{t['display']} time",
            options,
            index=options.index(current) if current in options else 0,
            format_func=lambda x: DURATION_LABELS.get(x, f"{x}m"),
            horizontal=True,
            key=f"dur_{c}",
            label_visibility="collapsed"
        )

        if selected != current:
            state["durations"][c] = selected
            # Setting a task back to zero always keeps it visible.
            if selected == 0:
                state["collapsed_tasks"] = [x for x in state.get("collapsed_tasks", []) if x != c]
            save_state(state)
            st.rerun()

    col1, col2 = st.columns(2)
    if col1.button("Save progress", use_container_width=True, type="primary"):
        previously_collapsed = set(state.get("collapsed_tasks", []))
        newly_saved = [
            t for t in DAILY_TASKS
            if normalize_task_duration(t["canonical"], state["durations"].get(t["canonical"], 0)) > 0
            and t["canonical"] not in previously_collapsed
        ]

        state["collapsed_tasks"] = [
            t["canonical"] for t in DAILY_TASKS
            if normalize_task_duration(t["canonical"], state["durations"].get(t["canonical"], 0)) > 0
        ]
        save_state(state)
        save_progress_to_history(state)

        core = get_companion_core(state)
        companion_msg = core.task_saved_message(newly_saved)
        if newly_saved:
            saved_names = ", ".join(t["display"] for t in newly_saved)
            add_chat(state, "Companion", companion_msg)
            st.toast(f"{saved_names} saved and tucked away.")
        else:
            st.toast(companion_msg)
        st.rerun()

    if col2.button("End day", use_container_width=True):
        core = get_companion_core(state)
        if completed_count(state) < len(DAILY_TASKS):
            early_message = core.quote("early_quit")
            add_chat(state, "Companion", early_message)
            render_companion_quote_card(early_message)
        else:
            state["day_closed"] = True
            state["collapsed_tasks"] = [
                t["canonical"] for t in DAILY_TASKS
                if normalize_task_duration(t["canonical"], state["durations"].get(t["canonical"], 0)) > 0
            ]
            save_state(state)
            save_progress_to_history(state)
            close_message = get_companion_core(state).end_day_message()
            add_chat(state, "Companion", close_message)
            st.success(close_message)


def render_alerts(state):
    core = get_companion_core(state)
    alerts = core.insights()
    brain = core.snapshot["history"]

    st.markdown(
        f"""
        <div class='trendSummary'>
          <div class='trendSummaryTitle'>Companion Insights</div>
          <div class='trendSummaryText'>{brain.get('current_state')} • {brain.get('logged_session_average', 0)}% logged-session average</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    level_map = {
        "WARNING": ("⚠", "warn", "Needs attention"),
        "UP": ("↑", "up", "Improving"),
        "STRONG": ("✓", "strong", "Strong"),
        "STABLE": ("◆", "stable", "Stable"),
        "INFO": ("•", "", "Building"),
    }

    for alert in alerts:
        icon, badge_class, badge_text = level_map.get(alert.get("level"), ("•", "", "Signal"))
        st.markdown(
            f"""
            <div class='trendCard'>
              <div class='trendTop'>
                <div class='trendHabit'>{icon} {html.escape(str(alert.get('task', 'Trend')))}</div>
                <div class='trendBadge {badge_class}'>{badge_text}</div>
              </div>
              <div class='trendObs'>{html.escape(str(alert.get('message', '')))}</div>
              <div class='trendMeta'>{html.escape(str(alert.get('meta', '')))}</div>
              <div class='trendAction'><span>Recommended</span>{html.escape(str(alert.get('action', trend_recommended_action(alert.get('task', 'Trends')))))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if completed_count(state) == 0:
        st.caption("Nothing is logged today yet. These alerts come from your recent saved sessions.")


def render_stats(state):
    ts = totals()
    st.markdown(f"""
    <div class="card"><div class="label">Quick Stats</div>
      <p>🔥 Current Streak: <b>{ts['streak']} days</b></p>
      <p>☑️ Tasks Completed: <b>{ts['tasks']}</b></p>
      <p>⭐ Total EXP Earned: <b>{ts['xp']:,}</b></p>
      <p>▣ Days Logged: <b>{ts['days']}</b></p>
    </div>
    """, unsafe_allow_html=True)
    with st.expander("Demo safety note"):
        st.write("Before hosting publicly, use sample JSON data or private storage. Do not upload real work/private history files to a public repo.")



def render_help(state):
    render_voice_controls(state)
    st.markdown("""
    <div class="card">
      <div class="label">Companion Guide</div>
      <p><b>what now</b><br><span class="muted">Companion suggests the next unfinished task.</span></p>
      <p><b>tasks</b><br><span class="muted">Shows today's task status.</span></p>
      <p><b>alerts</b><br><span class="muted">Shows compact trend signals from recent saved sessions.</span></p>
      <p><b>history</b><br><span class="muted">Analyzes recent momentum, strongest and weakest habits, and inactive days.</span></p>
      <p><b>log exercise 20</b><br><span class="muted">Logs a task from chat.</span></p>
      <p><b>log Spanish 20</b><br><span class="muted">Logs Spanish from chat.</span></p>
      <p><b>end day</b><br><span class="muted">Saves and closes today.</span></p>
    </div>
    """, unsafe_allow_html=True)

    st.info("Type quote, motivate me, wake me up, or get me going for an inspiration quote. Early quit and clean-finish quotes trigger automatically.")


def render_companion_quote_card(message):
    """Render a quiet Companion speech card instead of a detached warning box."""
    safe = html.escape(str(message or "Keep moving.")).replace("\n", "<br>")
    st.markdown(
        f"""
        <div class='companionQuoteCard'>
          <div class='companionQuoteHead'>✦ Companion</div>
          <div class='companionQuoteText'>{safe}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )




# -----------------------------
# PHASE 6 - BETTER DAY CLOSEOUT
# -----------------------------
TIER_NAMES = {
    "none": "Not started",
    "minimum": "Minimum",
    "growth": "Growth",
    "mastery": "Mastery",
}

DAY_STATUS_STARS = {
    "MISSION COMPLETE": "★★★★★",
    "SOLID DAY": "★★★★☆",
    "RECOVERY DAY": "★★★☆☆",
    "MORE IN THE TANK": "★★☆☆☆",
    "WARNING": "★☆☆☆☆",
}


def minimum_required_minutes(canonical, energy):
    if str(energy or "Normal").title() == "Low":
        return 10
    return {
        "Coding Core Task": 20,
        "Spanish Review": 20,
        "Complete Workout": 20,
        "Networking / LinkedIn": 10,
        "Reading": 10,
    }.get(canonical, 10)


def task_tier(canonical, duration):
    duration = normalize_task_duration(canonical, duration)
    options = duration_options(canonical)
    if not options or duration <= 0:
        return "none"
    minimum = options[0]
    growth = options[1] if len(options) > 1 else minimum
    mastery = options[2] if len(options) > 2 else growth
    if duration >= mastery:
        return "mastery"
    if duration >= growth:
        return "growth"
    if duration >= minimum:
        return "minimum"
    return "none"


def build_day_closeout(state):
    energy = str(state.get("energy", "Normal") or "Normal").title()
    completed = completed_count(state)
    xp = xp_today(state)
    xp_possible = max_daily_xp()
    untouched = []
    below_minimum = []
    minimums_met = 0
    masteries = 0
    task_rows = []

    for task in DAILY_TASKS:
        canonical = task["canonical"]
        duration = normalize_task_duration(canonical, state.get("durations", {}).get(canonical, 0))
        minimum = minimum_required_minutes(canonical, energy)
        tier = task_tier(canonical, duration)
        if duration <= 0:
            untouched.append(task["display"])
        elif duration < minimum:
            below_minimum.append({"display": task["display"], "duration": duration, "minimum": minimum})
        else:
            minimums_met += 1
        if tier == "mastery":
            masteries += 1
        task_rows.append({"display": task["display"], "duration": duration, "minimum": minimum, "tier": tier})

    history = analyze_history()
    weak_canonical = history.get("weakest_habit", "Unknown")
    weak_display = display_task_name(weak_canonical)
    focus = untouched[0] if untouched else (below_minimum[0]["display"] if below_minimum else weak_display)
    if not focus or focus == "Unknown":
        focus = "Reading"

    percent = int(round((xp / xp_possible) * 100)) if xp_possible else 0
    repeated_attention = False
    weak_stats = (history.get("growth_task_stats", {}) or {}).get(weak_canonical, {}) or {}
    if int(weak_stats.get("missed", 0) or 0) >= 2 and focus == weak_display:
        repeated_attention = True

    if completed == len(DAILY_TASKS) and minimums_met == len(DAILY_TASKS):
        status = "MISSION COMPLETE"
    elif energy == "Low" and completed >= 2:
        status = "RECOVERY DAY"
    elif completed >= 4 and minimums_met >= 4:
        status = "SOLID DAY"
    elif completed <= 1 or (repeated_attention and completed <= 2):
        status = "WARNING"
    else:
        status = "MORE IN THE TANK"

    previous = build_lightweight_memory()
    comparison = ""
    if previous.get("available"):
        prior = int(previous.get("last_completed", 0) or 0)
        if completed > prior:
            comparison = "Better than the last session."
        elif completed < prior:
            comparison = "A lighter result than the last session."
        else:
            comparison = "Matched the last session."

    companion_lines = {
        "MISSION COMPLETE": (
            "You protected every promise you made today. "
            "Tomorrow doesn't begin at zero. It begins here. "
            "We'll continue from here."
        ),
        "SOLID DAY": (
            "The main loops moved forward. "
            "You gave tomorrow something solid to build on. "
            "We'll build from here tomorrow."
        ),
        "RECOVERY DAY": (
            "Not perfect. Not necessary. "
            "Momentum survived because you came back. "
            "We'll continue tomorrow."
        ),
        "MORE IN THE TANK": (
            f"The day moved, but {focus} is still asking for attention. "
            "Carry the lesson forward, not the guilt. "
            "We'll pick it up tomorrow."
        ),
        "WARNING": (
            "Today isn't the crash. It's the warning light. "
            f"Tomorrow begins by repairing {focus}. "
            "We'll fix it tomorrow."
        ),
    }

    tomorrow_task = next((t for t in DAILY_TASKS if t["display"] == focus), None)
    if tomorrow_task is None:
        tomorrow_task = get_task(weak_canonical) or get_task("Reading")
    tomorrow_canonical = tomorrow_task["canonical"] if tomorrow_task else "Reading"
    tomorrow_minutes = minimum_required_minutes(tomorrow_canonical, "Normal")
    tomorrow_xp = task_xp(tomorrow_canonical, tomorrow_minutes)

    quote_category = "finished" if status == "MISSION COMPLETE" else "early_quit"
    return {
        "status": status,
        "stars": DAY_STATUS_STARS[status],
        "completed": completed,
        "total": len(DAILY_TASKS),
        "xp": xp,
        "xp_possible": xp_possible,
        "xp_percent": percent,
        "minimums_met": minimums_met,
        "masteries": masteries,
        "protected_count": minimums_met,
        "untouched": untouched,
        "below_minimum": below_minimum,
        "task_rows": task_rows,
        "focus": focus,
        "tomorrow_task": tomorrow_task["display"] if tomorrow_task else focus,
        "tomorrow_minutes": tomorrow_minutes,
        "tomorrow_xp": tomorrow_xp,
        "companion": companion_lines[status],
        "comparison": comparison,
        "quote_category": quote_category,
    }


def render_closeout_debrief(review):
    protected = [
        row["display"] for row in review["task_rows"]
        if int(row.get("duration", 0) or 0) >= int(row.get("minimum", 0) or 0)
    ]
    protected_html = "".join(
        f"<span class='closeoutChip' style='border-color:rgba(98,240,178,.45);background:rgba(98,240,178,.08);color:#bff9df'>✓ {html.escape(name)}</span>"
        for name in protected
    )
    attention_items = list(review["untouched"]) + [item["display"] for item in review["below_minimum"]]
    attention_html = "".join(
        f"<span class='closeoutChip'>• {html.escape(name)}</span>" for name in attention_items
    )

    if not protected_html:
        protected_html = "<span class='muted'>No habits reached their minimum yet.</span>"
    if not attention_html:
        attention_html = "<span class='closeoutGood'>✓ Nothing left exposed today</span>"

    comparison_html = f"<div class='closeoutCompare'>{html.escape(review['comparison'])}</div>" if review["comparison"] else ""
    hero_class = "closeoutHero missionComplete" if review["status"] == "MISSION COMPLETE" else "closeoutHero"
    st.markdown(f"""
    <div class='{hero_class}'>
      <div class='closeoutEyebrow'>Today's Debrief</div>
      <div class='closeoutStars'>{review['stars']}</div>
      <div class='closeoutStatus'>{html.escape(review['status'])}</div>
      <div class='closeoutScore'>{review['completed']}/{review['total']} tasks &nbsp;•&nbsp; {review['xp']}/{review['xp_possible']} XP</div>
      {comparison_html}
    </div>
    <div class='closeoutGrid'>
      <div class='closeoutMetric'><b>{review['minimums_met']}/{review['total']}</b><span>Minimums</span></div>
      <div class='closeoutMetric'><b>{review['protected_count']}</b><span>Habits protected</span></div>
      <div class='closeoutMetric'><b>{review['xp_percent']}%</b><span>XP earned</span></div>
    </div>
    <div class='closeoutPanel'>
      <div class='label'>Day Check</div>
      <div class='closeoutSectionTitle good'>Protected Today</div>
      <div class='closeoutList'>{protected_html}</div>
      <div class='closeoutSectionTitle attention'>Needs Attention</div>
      <div class='closeoutList'>{attention_html}</div>
    </div>
    <div class='closeoutPanel'>
      <div class='label'>Tomorrow's Focus</div>
      <div class='closeoutTomorrow'>🎯 {html.escape(review['tomorrow_task'])}</div>
      <div class='muted'>{review['tomorrow_minutes']} minutes • +{review['tomorrow_xp']} XP</div>
    </div>
    """, unsafe_allow_html=True)

def render_end_day(state):
    review = build_day_closeout(state)
    render_closeout_debrief(review)

    # The comparison already appears in the debrief header. Keep the final
    # Companion word focused, personal, and forward-looking.
    render_companion_quote_card(review["companion"])

    all_bonus_complete = all_energy_minimums_met(state) and all(
        next_duration_tier(
            task["canonical"],
            state.get("durations", {}).get(task["canonical"], 0),
        ) is None
        for task in DAILY_TASKS
    )
    button_label = "🌙 See You Tomorrow" if all_bonus_complete else "Begin Tomorrow"
    if st.button(button_label, use_container_width=True, type="primary"):
        quote = categorized_quote(state, review["quote_category"])
        state["day_closed"] = True
        state["last_closeout"] = {
            "status": review["status"],
            "closed_at": datetime.now().isoformat(timespec="seconds"),
            "tomorrow_focus": review["tomorrow_task"],
        }
        save_state(state)
        save_progress_to_history(state)
        final_message = (
            f"{review['status'].title()}. {review['completed']}/{review['total']} tasks • "
            f"{review['xp']} XP. Tomorrow begins with {review['tomorrow_task']}."
        )
        add_chat(state, "Companion", final_message)
        queue_companion_voice(
            state, spoken_companion_line("end_day", status=review["status"].title()),
            f"closeout_{today_key()}_{review['status']}", autoplay=True
        )
        st.success("Today is sealed. Tomorrow is ready.")
        render_companion_quote_card(quote)
        st.rerun()



def set_page(page_name):
    st.session_state["mobile_page"] = page_name


def render_mobile_nav():
    if "mobile_page" not in st.session_state:
        st.session_state["mobile_page"] = "Home"

    current = st.session_state["mobile_page"]

    def nav_button(column, label, page_name):
        active = current == page_name
        if column.button(
            label,
            use_container_width=True,
            type="primary" if active else "secondary",
            key=f"nav_{page_name}",
        ):
            if not active:
                set_page(page_name)
                st.rerun()

    c1, c2, c3 = st.columns(3)
    nav_button(c1, "🏠 Home", "Home")
    nav_button(c2, "✅ Tasks", "Tasks")
    nav_button(c3, "⚠️ Alerts", "Alerts")

    c4, c5 = st.columns(2)
    nav_button(c4, "🌙 End Day", "End day")
    nav_button(c5, "✦ Companion", "Commands")

    return st.session_state["mobile_page"]



state = load_state()
if "mobile_page" not in st.session_state:
    st.session_state["mobile_page"] = "Home"

current_page = st.session_state.get("mobile_page", "Home")
previous_page = st.session_state.get("_last_rendered_page")
animate_mission = current_page == "Home" and previous_page != "Home"

render_header(state, animate_mission=animate_mission)

tab = render_mobile_nav()

if tab == "Home":
    render_home(state)
elif tab == "Tasks":
    render_tasks(state)
elif tab == "Alerts":
    render_alerts(state)
elif tab == "End day":
    render_end_day(state)
else:
    render_help(state)


# Render any ElevenLabs audio queued during the previous interaction.
# Without this call, voice events are created but never turned into an audio player.
render_pending_companion_voice(state)

# Track page transitions so the mission shine runs once when Home is entered.
st.session_state["_last_rendered_page"] = tab
