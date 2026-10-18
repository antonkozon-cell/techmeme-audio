import os, time, asyncio, smtplib, urllib.request
from datetime import datetime
from email.message import EmailMessage
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
import edge_tts

def fetch_news():
    req = urllib.request.Request("https://www.techmeme.com/", headers={'User-Agent': 'Mozilla/5.0'})
    html = urllib.request.urlopen(req).read().decode('utf-8', errors='ignore')
    soup = BeautifulSoup(html, 'html.parser')
    top = soup.find('div', id='topcol1') or soup
    stories = []
    for c in top.find_all('div', class_='clus')[:20]:
        link = c.find('a', class_='ourh')
        if link:
            stories.append(link.get_text(" ", strip=True) + " - " + c.get_text(" ", strip=True))
    return "\n\n".join(stories)

def make_audio(news, mp3="briefing.mp3"):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"].strip())
    prompt = "Si slovensky moderator. Sprav plynuly audio brifing v slovencine z tychto sprav (vynechaj investicie, akvizicie, krypto a datacentra). Pis cisty text bez odrazok:\n" + news
    
    for i in range(4):
        try:
            print("Skusam Gemini Audio, pokus:", i + 1)
            cfg = types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")))
            )
            res = client.models.generate_content(model='gemini-3.8-flash', contents=prompt, config=cfg)
            for p in res.candidates[0].content.parts:
                if p.inline_data and p.inline_data.mime_type.startswith("audio/"):
                    open(mp3, "wb").write(p.inline_data.data)
                    return "Audio z Gemini AI."
        except Exception as e:
            print("Chyba pokusu:", e)
            time.sleep(20)

    print("Prepinam na zalozny hlas Edge-TTS...")
    res = client.models.generate_content(model='gemini-3.8-flash', contents=prompt)
    asyncio.run(edge_tts.Communicate(res.text, "sk-SK-LukasNeural").save(mp3))
    return res.text

def send_mail(mp3, text):
    user = os.environ["EMAIL_ADDRESS"].strip()
    pwd = os.environ["EMAIL_APP_PASSWORD"].replace(" ", "").strip()
    msg = EmailMessage()
    msg["Subject"] = "Techmeme Audio Brifing"
    msg["From"] = user
    msg["To"] = user
    msg.set_content("Dnesny prehlad:\n\n" + text)
    msg.add_attachment(open(mp3, "rb").read(), maintype="audio", subtype="mp3", filename="techmeme.mp3")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pwd)
        s.send_message(msg)

if __name__ == "__main__":
    n = fetch_news()
    t = make_audio(n)
    send_mail("briefing.mp3", t)
    print("Hotovo")
