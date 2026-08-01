# MyHabits

A 21-day habit tracker built around the protocol popularized by Andrew Huberman and the ideas in *Atomic Habits*. Pick six habits, slot them into morning / afternoon / evening, and mark them done each day. After 21 days, review your report and start a new round.

## Features

**21-Day Challenge**
Define up to six habits and assign each to a time phase (morning, afternoon, evening). Track daily completion across a 21-day cycle, with a progress bar showing which day you're on and how many days remain. Each phase auto-collapses once all its habits are done, keeping the view calm and focused.

**AI Evening Planner (Now)**
The standout feature. Open the "Now" page, enter your planned bedtime, and tap "What to do now." The app sends your remaining habits, the current time, and your bedtime to an AI model (HKU Claude API), which returns a concrete time-blocked plan for the evening. It knows to skip habits that would hurt sleep (e.g. an intense workout 60 minutes before bed) and orders activities from energizing to calming so you wind down naturally.

**Bilingual (English / 中文)**
Switch language from the button in the top-right corner. Your preference is remembered across sessions. The AI planner also responds in the selected language.

**Daily Quotes**
Each time you open the Today page, a quote about habits and discipline appears—from Andrew Huberman, James Clear, Carl Jung, David Goggins, and Jocko Willink.

**Completion Report**
After 21 days, a report shows how many days each habit was completed. Use it to decide which habits are solid and which need another cycle, then start fresh.

**Field Guide**
An Info page explains the protocol, suggests sample habits grounded in science (sunlight viewing, meditation, NSDR, etc.), and links to the source material.

## Run Locally

```bash
cd "Habit Tracker"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000 in your browser.

For production, use gunicorn (included in requirements.txt):
```bash
gunicorn app:app
```

The AI planner requires a `.env` file with HKU Claude API credentials:
```
HKU_CLAUDE_API_KEY=your-key
HKU_CLAUDE_ENDPOINT=https://api.hku.hk/claude/student/model
HKU_CLAUDE_MODEL=claude-haiku-4.5
SECRET_KEY=your-random-hex-string
```
The app works without it—only the AI planner feature will be unavailable. `SECRET_KEY` is needed for persistent sessions; without it, all users are logged out on every restart.

## Tech Stack

Flask, SQLite, vanilla HTML/CSS/JS. No frontend framework, no build step.

## Credits

Built by Simon Wang. Protocol design informed by Andrew Huberman's podcast and James Clear's *Atomic Habits*.
