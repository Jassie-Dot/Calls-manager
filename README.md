# AI Phone Booking Agent

A FastAPI phone receptionist that answers Twilio calls, speaks with callers, collects booking details, checks Google Calendar, and confirms appointments using Groq tool calling and Edge TTS.

## 1. Architecture Overview

Twilio sends inbound calls to `/incoming-call`. The app plays an Edge TTS greeting, gathers speech, sends each transcript to Groq, and keeps short per-call state in memory. When Groq has the caller's name, date, time, and party size, it calls the booking tool; the app checks Google Calendar, creates the event if the slot is free, and asks Groq for the final spoken response.

The agent is bilingual for English, Hindi, and Hinglish. It detects the transcript language after each caller turn, switches the next Twilio Gather recognition language, and chooses the matching Edge TTS voice.

## 2. Prerequisites

- Python 3.11+
- A free Twilio account from [twilio.com](https://www.twilio.com) with Account SID, Auth Token, and a trial phone number
- A free Groq account from [console.groq.com](https://console.groq.com) with an API key
- A Google account with Calendar API enabled and a downloaded `credentials.json`
- ngrok for local dev, installed from [ngrok.com](https://ngrok.com) or your package manager

## 3. Setup

```bash
git clone <repo>
cd ai-booking-agent
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in your Twilio, Groq, Google Calendar, and business values in `.env`.

On Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

## 4. Google Calendar Setup

This app supports either a Google OAuth desktop client file or a service-account key file.

For a service account, place the JSON key in the project root as `credentials.json`. Then open Google Calendar settings, share the target calendar with the service account `client_email`, and grant permission to make changes to events. Set `GOOGLE_CALENDAR_ID` in `.env` to the calendar ID or calendar email. Do not leave it as `primary` for service-account deployments.

For an OAuth desktop client, create an OAuth client in Google Cloud Console, download it as `credentials.json`, and place it in the project root.

Then run:

```bash
python -c "
from google_auth_oauthlib.flow import InstalledAppFlow
flow = InstalledAppFlow.from_client_secrets_file(
    'credentials.json',
    ['https://www.googleapis.com/auth/calendar']
)
creds = flow.run_local_server(port=0)
with open('token.json', 'w') as f:
    f.write(creds.to_json())
print('token.json saved!')
"
```

You can also trigger the app's calendar auth helper:

```bash
python -c "from services.calendar_service import get_calendar_service; get_calendar_service()"
```

## 5. Run Locally

Terminal 1:

```bash
uvicorn main:app --reload --port 8000
```

Terminal 2:

```bash
ngrok http 8000
```

Copy the ngrok HTTPS URL, such as `https://abc123.ngrok-free.app`, into `.env` as `BASE_URL`.

## 6. Configure Twilio Webhooks

In the Twilio Console, open Phone Numbers, select your number, then set Voice Configuration:

- A call comes in: `https://your-ngrok-url.ngrok-free.app/incoming-call` with `POST`
- Call Status Callback: `https://your-ngrok-url.ngrok-free.app/call-status` with `POST`

## 7. Test It

Call the Twilio number. Try English, Hindi, and Hinglish examples:

```text
I want to book a table for tomorrow evening.
Kal shaam 7 baje table book karni hai.
मुझे शनिवार को 4 लोगों के लिए बुकिंग चाहिए।
```

## 8. Deploy to Render Free Tier

1. Push this project to GitHub.
2. Go to Render, create a new Blueprint or Web Service, and connect the repo.
3. If using the included `render.yaml`, Render will prompt you for secret values marked with `sync: false`.
4. In the Render service Environment tab, add a Secret File named `credentials.json` and paste the Google service-account JSON contents.
5. Set `GOOGLE_CALENDAR_ID` to the shared Google Calendar ID or calendar email.
6. Deploy.
7. If Render gives the service a different URL than `https://calls-manager.onrender.com`, update `BASE_URL`.
8. Update Twilio webhook URLs to the Render URL.

## 9. Hindi, English, and Auto Switching

This app supports language switching at the conversation level:

- Initial greeting is Hinglish so both English and Hindi callers feel invited.
- After every transcript, `services/language.py` detects English, Hindi, or Hinglish.
- The next `<Gather>` uses `en-IN` for English and `hi-IN` for Hindi or Hinglish.
- TTS switches between `en-IN-NeerjaNeural` and `hi-IN-SwaraNeural`.
- The system prompt tells Groq to respond naturally in the caller's language without announcing the switch.

Important production note: Twilio `<Gather>` uses one recognition `language` per prompt, and its default language is `en-US`. For true audio-level automatic language detection before transcription, Twilio's current `multi` language mode is part of ConversationRelay and requires specific providers. This free-stack version uses transcript-level detection and switches future turns.

## 10. Production Agency Checklist

- Create a separate Twilio number, Google Calendar, `.env`, and Render service per client.
- Use `Asia/Kolkata`, `en-IN`, and `hi-IN` defaults for Indian businesses; change them per market.
- Keep responses short because phone callers interrupt long prompts.
- Replace in-memory state with Redis or a database if you run multiple workers.
- Add Twilio request signature validation before exposing a production endpoint publicly.
- Monitor failed bookings and calendar errors with Render logs.
- Use a paid STT/TTS upgrade if a client needs robust code-switching inside a single sentence.

## 11. Critical Implementation Notes

All Twilio webhooks return `text/xml`. Generated MP3 files are served from `/audio/{filename}` only when the filename is safe, then deleted after 30 seconds. If Edge TTS fails, the app falls back to Twilio `<Say>`. If Groq fails, the caller hears a short retry message. If Calendar fails, the agent tells the caller a human will follow up.

## 12. Optional Phase 2: Fully Free STT With Groq Whisper

To eliminate Twilio Gather transcription and get better language detection:

1. Replace `<Gather input="speech">` with `<Connect><Stream url="wss://{host}/ws/stream"/></Connect>`.
2. Add a FastAPI WebSocket endpoint at `/ws/stream`.
3. Decode Twilio base64 mu-law audio into PCM WAV chunks.
4. Buffer speech, detect silence, and send each chunk to Groq Whisper.
5. Process the transcript through the same LLM and Calendar pipeline.
6. Stream generated audio back to the call.

That path is more complex, but it is the right next step when the agency needs stronger Hindi-English recognition without relying on one Twilio Gather language per turn.
