import json
import re
import random
import html
from pathlib import Path
from datetime import datetime, timedelta
import streamlit as st
import streamlit.components.v1 as components

DAY_ROLLOVER_HOUR = 2
HISTORY_FILE = Path("momentum_history.json")
TODAY_TASKS_FILE = Path("today_tasks_state.json")
WORKOUT_PB_FILE = Path("workout_personal_bests.json")

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

QUOTES = [
    "Focus on recovery. Progress > perfection.",
    "The standard is not a perfect day. The standard is returning.",
    "One completed loop is enough to keep the system alive.",
    "You do not need the whole mountain. You need the next rep.",
    "Make the check-in easy enough that future you actually uses it.",
]

st.set_page_config(page_title="Momentum Mobile", page_icon="⚡", layout="centered")

st.markdown("""
<style>
:root{
  --bg:#000000; --panel:#070b13; --card:#0d1422; --card2:#111b2d;
  --purple:#8b4dff; --purple2:#b55cff; --text:#f7f4ff; --muted:#a9b5ca;
  --line:#24324c; --gold:#ffd84d; --red:#ff4d57; --green:#62f0b2;
}
.stApp{background:var(--bg); color:var(--text);}
.block-container{padding: .75rem 1rem 5rem 1rem; max-width: 480px;}
[data-testid="stHeader"]{background:rgba(0,0,0,0);}
.hero{border:1px solid var(--purple); border-radius:20px; padding:16px 16px 14px 16px; background:linear-gradient(180deg,#11182a,#05070d); box-shadow:0 0 20px rgba(139,77,255,.20); margin-bottom:12px;}
.logoRow{display:flex; align-items:center; gap:12px;}
.logo{width:48px; height:48px; border-radius:14px; display:flex; align-items:center; justify-content:center; background:#170b2f; color:var(--purple); font-size:32px; font-weight:900;}
.title{font-size:1.25rem; font-weight:900; letter-spacing:.5px; line-height:1.1;}
.sub{color:var(--muted); margin-top:4px; font-size:.9rem;}
.modePill{display:inline-block; margin-top:12px; padding:7px 10px; border-radius:999px; color:#fff; background:rgba(139,77,255,.18); border:1px solid rgba(139,77,255,.55); font-size:.8rem; font-weight:800;}
.card{border:1px solid var(--line); border-radius:16px; padding:14px; background:var(--card); margin:10px 0;}
.companion{border:1px solid rgba(139,77,255,.40); border-radius:18px; padding:16px; background:linear-gradient(180deg,#0e1727,#070b13); margin:12px 0;}
.label{color:var(--purple2); font-size:.78rem; font-weight:900; text-transform:uppercase; letter-spacing:.6px; margin-bottom:8px;}
.big{font-size:1.45rem; font-weight:900;}
.muted{color:var(--muted);}
.statGrid{display:grid; grid-template-columns:1fr 1fr 1fr; gap:10px; margin:12px 0;}
.stat{border:1px solid var(--line); background:#07101f; border-radius:14px; padding:10px; text-align:center;}
.stat .n{font-size:1.35rem; font-weight:900; color:var(--gold);}
.stat .t{font-size:.72rem; color:var(--muted); font-weight:800;}
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
.chatBox{max-height:455px; overflow-y:auto; padding:14px 16px; margin:0 0 10px 0; border:1px solid rgba(139,77,255,.65); border-radius:16px; background:#070b13; box-shadow:0 0 14px rgba(139,77,255,.10);}
.chatMsg{display:block; padding:0; margin:0 0 10px 0; border:0!important; background:transparent!important;}
.chatMsg:last-child{margin-bottom:0;}
.chatMsg.you{border:0!important; background:transparent!important;}
.chatMsg.companion{border:0!important; background:transparent!important;}
.chatWho{display:inline; font-weight:900; margin-right:7px; font-size:.9rem;}
.chatMsg.you .chatWho{color:#9fc0ff;}
.chatMsg.companion .chatWho{color:#b55cff;}
.chatText{display:inline; color:#f1f6ff; line-height:1.45; font-size:.93rem;}
.nextMove{margin-top:12px;}


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

</style>
""", unsafe_allow_html=True)


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
    for t in DAILY_TASKS:
        if state["durations"].get(t["canonical"], 0) == 0:
            return t
    return None


def format_tasks(state):
    lines = []
    for t in DAILY_TASKS:
        c = t["canonical"]
        d = state["durations"].get(c, 0)
        lines.append(f"{'✅' if d else '⭕'} {t['display']} — {DURATION_LABELS.get(d, '0m')}")
    return "\n".join(lines)


def handle_command(text, state):
    cleaned = (text or "").strip()
    if not cleaned:
        return "Type a command or tap a suggestion."
    low = cleaned.lower()

    if any(x in low for x in ["quote", "motivate", "inspire", "wake me up", "don't feel", "dont feel"]):
        return random.choice(QUOTES)

    if "clear chat" in low or "reset chat" in low:
        clear_chat(state)
        return "Chat cleared. Fresh board."

    if "alert" in low or "warning" in low:
        t = next_task(state)
        if not t:
            return "ALERTS\n\nNo task gap right now. All core tasks are logged."
        return f"ALERTS\n\nPriority gap: {t['display']} is not logged yet.\nSmallest clean version: {min(duration_options(t['canonical']))} minutes."

    if "help" in low or "command" in low:
        return (
            "HELP / COMMANDS\n\n"
            "what now — suggests the next move\n"
            "tasks — shows today's task status\n"
            "alerts — shows the current task gap\n"
            "log exercise 20 — logs a task\n"
            "log Spanish 20 — logs Spanish\n"
            "end day — saves and closes today\n\n"
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

    if "what now" in low or "next" in low or "move" in low:
        t = next_task(state)
        if not t:
            return "Clean finish. All five tasks are logged. End the day or take a bonus round."
        mins = min(duration_options(t["canonical"]))
        return f"NEXT MOVE\n\n{t['display']} — {mins} minutes.\n\nDo the smallest clean version and log it."

    if "end day" in low or "close day" in low:
        state["day_closed"] = True
        save_state(state); save_progress_to_history(state)
        return "Day closed. Progress saved to history."

    canonical = task_by_words(low)
    if canonical and any(w in low for w in ["done", "did", "finished", "complete", "completed", "logged", "log"]):
        mins = minutes_from_text(low, canonical)
        state["durations"][canonical] = mins
        save_state(state); save_progress_to_history(state)
        display = get_task(canonical)["display"]
        return f"Logged {display}: {DURATION_LABELS.get(mins, str(mins)+'m')} • +{task_xp(canonical, mins)} XP."

    return "I can handle: what now, tasks, quote, log exercise 20, log Spanish 20, end day."


def add_chat(state, who, msg):
    state.setdefault("chat_log", [])
    state["chat_log"].append({"who": who, "msg": msg, "time": datetime.now().strftime("%I:%M %p")})
    state["chat_log"] = state["chat_log"][-8:]
    save_state(state)


def render_header(state):
    comp = completed_count(state)
    percent = int((comp / len(DAILY_TASKS)) * 100)
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
    st.progress(percent / 100, text=f"{percent}% complete • {xp_today(state)}/{max_daily_xp()} XP")



def build_opening_message(state):
    comp = completed_count(state)
    t = next_task(state)
    if comp == 0 and t:
        return f"Welcome back, Terrence. Nothing logged yet today — start with {t['display']} for {min(duration_options(t['canonical']))} minutes."
    if t:
        return f"Welcome back. You have {comp}/5 done. Next move: {t['display']} for {min(duration_options(t['canonical']))} minutes."
    return "Welcome back. All five core tasks are logged — clean finish is available."


def ensure_opening_chat(state):
    if not state.get("chat_log"):
        state["chat_log"] = [{
            "who": "Companion",
            "msg": build_opening_message(state),
            "time": datetime.now().strftime("%I:%M %p"),
        }]
        save_state(state)


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
            placeholder="Try: log exercise 20 • what now • tasks • help • end day",
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
    return f"{completed} exercise{'s' if completed != 1 else ''} logged" if completed else "No exercises logged"


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

        if newly_saved:
            saved_names = ", ".join(t["display"] for t in newly_saved)
            saved_xp = sum(
                task_xp(t["canonical"], state["durations"].get(t["canonical"], 0))
                for t in newly_saved
            )
            upcoming = next_task(state)
            if upcoming:
                companion_msg = (
                    f"✅ {saved_names} saved • +{saved_xp} XP. "
                    f"I've tucked it away. Next up: {upcoming['display']} "
                    f"for {min(duration_options(upcoming['canonical']))} minutes."
                )
            else:
                companion_msg = f"✅ {saved_names} saved • +{saved_xp} XP. All five core tasks are logged."
            add_chat(state, "Companion", companion_msg)
            st.toast(f"{saved_names} saved and tucked away.")
        else:
            st.toast("Progress saved.")
        st.rerun()

    if col2.button("End day", use_container_width=True):
        state["day_closed"] = True
        state["collapsed_tasks"] = [
            t["canonical"] for t in DAILY_TASKS
            if normalize_task_duration(t["canonical"], state["durations"].get(t["canonical"], 0)) > 0
        ]
        save_state(state)
        save_progress_to_history(state)
        st.success("Day closed.")


def render_alerts(state):
    t = next_task(state)
    st.markdown("<div class='card'><div class='label'>Alerts</div>", unsafe_allow_html=True)
    if t:
        st.warning(f"Priority gap: {t['display']} is not logged yet. Smallest clean version: {min(duration_options(t['canonical']))} minutes.")
    else:
        st.success("No task gap right now. All core tasks are logged.")
    if completed_count(state) == 0:
        st.info("No progress logged yet today. Use the Home chat bar or the Tasks tab.")
    st.markdown("</div>", unsafe_allow_html=True)


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
    st.markdown("""
    <div class="card">
      <div class="label">Help / Commands</div>
      <p><b>what now</b><br><span class="muted">Companion suggests the next unfinished task.</span></p>
      <p><b>tasks</b><br><span class="muted">Shows today's task status.</span></p>
      <p><b>alerts</b><br><span class="muted">Shows the current task gap.</span></p>
      <p><b>log exercise 20</b><br><span class="muted">Logs a task from chat.</span></p>
      <p><b>log Spanish 20</b><br><span class="muted">Logs Spanish from chat.</span></p>
      <p><b>end day</b><br><span class="muted">Saves and closes today.</span></p>
    </div>
    """, unsafe_allow_html=True)

    st.info("Quotes are still available behind the scenes. Type quote, motivate me, or wake me up in chat.")


def render_end_day(state):
    comp = completed_count(state)
    xp = xp_today(state)
    st.markdown(f"""
    <div class="card">
      <div class="label">End Day</div>
      <div class="big">{comp}/5 complete</div>
      <p class="muted">{xp}/{max_daily_xp()} XP earned today.</p>
    </div>
    """, unsafe_allow_html=True)

    if st.button("Save and close today", use_container_width=True, type="primary"):
        state["day_closed"] = True
        save_state(state)
        save_progress_to_history(state)
        add_chat(state, "Companion", f"Day closed. Final score: {completed_count(state)}/5 • {xp_today(state)} XP.")
        st.success("Day closed and saved.")



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
    nav_button(c5, "❔ Commands", "Commands")

    return st.session_state["mobile_page"]



state = load_state()
render_header(state)

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
