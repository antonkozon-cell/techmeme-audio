import os, time, json, asyncio, smtplib, imaplib, email, subprocess, urllib.request, urllib.parse
from email.message import EmailMessage
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
import edge_tts
from gtts import gTTS

def get_prefs():
    repo = os.environ.get("REPO", "antonkozon-cell/techmeme-audio")
    token = os.environ.get("GITHUB_TOKEN", "")
    url = "https://api.github.com/repos/" + repo + "/issues?state=all&per_page=50"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    likes, dislikes = [], []
    try:
        data = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))
        for i in data:
            t = i.get("title", "")
            if t.startswith("LIKE:"):
                likes.append(t.replace("LIKE:", "").strip())
            elif t.startswith("DISLIKE:"):
                dislikes.append(t.replace("DISLIKE:", "").strip())
    except Exception as e:
        print("Citanie preferencii preskocene:", e)
    return likes, dislikes

def fetch_techmeme_from_gmail():
    user = os.environ["EMAIL_ADDRESS"].strip()
    pwd = os.environ["EMAIL_APP_PASSWORD"].replace(" ", "").strip()
    try:
        print("Hladam Techmeme newsletter v Gmaile...")
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(user, pwd)
        status, _ = mail.select('"[Gmail]/All Mail"')
        if status != "OK":
            mail.select("INBOX")
        
        _, data = mail.search(None, '(FROM "techmeme")')
        ids = data[0].split()
        if not ids:
            _, data = mail.search(None, '(SUBJECT "Techmeme")')
            ids = data[0].split()
            
        if not ids:
            return None
            
        _, msg_data = mail.fetch(ids[-1], "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])
        print("Najdeny email:", msg.get("Subject"))
        
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == "text/html":
                    raw = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    body = BeautifulSoup(raw, 'html.parser').get_text("\n", strip=True)
                    break
                elif ctype == "text/plain" and not body:
                    body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
        else:
            raw = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
            body = BeautifulSoup(raw, 'html.parser').get_text("\n", strip=True)
            
        mail.logout()
        return body[:45000] if len(body) > 300 else None
    except Exception as e:
        print("Chyba pri citani Gmailu:", e)
        return None

def fetch_web_fallback():
    req = urllib.request.Request("https://www.techmeme.com/", headers={'User-Agent': 'Mozilla/5.0'})
    html = urllib.request.urlopen(req).read().decode('utf-8', errors='ignore')
    soup = BeautifulSoup(html, 'html.parser')
    return "\n\n".join([c.get_text(" ", strip=True) for c in soup.find_all('div', class_='clus')[:75]])

def generate_script_and_topics(news, likes, dislikes):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"].strip())
    pref_text = ""
    if likes:
        pref_text += "UPREDNOSTNI TEMY: " + ", ".join(likes) + ".\n"
    if dislikes:
        pref_text += "VYNECHAJ TEMY: " + ", ".join(dislikes) + ".\n"

    prompt = (
        "Si dynamicky, uderny slovensky technologicky moderator. Posluchac nema rad rozvlacnu vatu a chce ist rovno k veci.\n"
        "Prejdi CELU ponuku sprav nizsie (od zaciatku az po koniec).\n"
        "Striktne VYNECHAJ: mergers, akvizicie, funding rounds, kryptomeny a datove centra.\n"
        + pref_text +
        "PRAVIDLA:\n"
        "- Ziadne dlhe uvody ani omacky. Chod okamzite k faktom.\n"
        "- Vyber 15 az 20 roznych zaujimavych sprav.\n"
        "- Kazdu spravu zhrn uderne v 2 az 3 vetach (co sa stalo a preco na tom zalezi) a prejdi na dalsiu.\n"
        "- Pis cisty text na citanie nahlas (bez odrazok a hviezdiciek). Kazdu spravu oddel novym odsekom.\n\n"
        "Na koniec pridaj oddelovac ===TEMY=== a za nim vypis prebrate temy, kazdu na novy riadok (max 6 slov, bez cislovania).\n\n"
        "SPRAVY:\n" + news
    )
    res = client.models.generate_content(model='gemini-3.8-flash', contents=prompt)
    parts = res.text.split("===TEMY===")
    script = parts[0].strip()
    topics = [line.strip("- *1234567890.") for line in parts[1].strip().split("\n") if line.strip()] if len(parts) > 1 else []
    return script, topics

def split_text(text, max_len=1400):
    chunks, current = [], ""
    for p in text.split("\n"):
        p = p.strip()
        if not p:
            continue
        if len(current) + len(p) < max_len:
            current += p + "\n\n"
        else:
            if current:
                chunks.append(current.strip())
            current = p + "\n\n"
    if current:
        chunks.append(current.strip())
    return chunks

def make_audio(script, mp3="briefing.mp3"):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"].strip())
    clean_script = script.replace("*", "").replace("#", "")
    chunks = split_text(clean_script, 1400)
    print("Generujem nativny hlas Gemini po castiach. Pocet casti:", len(chunks))

    pcm_data = bytearray()
    gemini_success = True

    for idx, chunk in enumerate(chunks):
        part_ok = False
        for attempt in range(3):
            try:
                print("Gemini Audio cast", idx + 1, "pokus", attempt + 1)
                cfg = types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")))
                )
                res = client.models.generate_content(
                    model='gemini-3.8-flash',
                    contents="Precitaj tento spravodajsky prehlad sviznym, prirodzenym slovenskym hlasom presne tak ako je napisany:\n\n" + chunk,
                    config=cfg
                )
                for p in res.candidates[0].content.parts:
                    if p.inline_data and p.inline_data.mime_type.startswith("audio/"):
                        pcm_data.extend(p.inline_data.data)
                        part_ok = True
                        break
                if part_ok:
                    time.sleep(4)
                    break
            except Exception as e:
                print("Chyba pri casti:", e)
                time.sleep(12)
        if not part_ok:
            gemini_success = False
            break

    if gemini_success and len(pcm_data) > 1000:
        print("Spajam Gemini Audio do MP3 cez ffmpeg...")
        open("raw.pcm", "wb").write(pcm_data)
        subprocess.run(["ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", "raw.pcm", "-b:a", "128k", mp3], check=True)
        return "Nativny hlas Gemini AI (Puck)"

    print("Nativny hlas zlyhal, pouzivam zalozny hlas...")
    gTTS(text=clean_script, lang='sk').save(mp3)
    return "Zalozny hlas (gTTS)"

def send_mail(mp3, script, topics, source_info, voice_info):
    user = os.environ["EMAIL_ADDRESS"].strip()
    pwd = os.environ["EMAIL_APP_PASSWORD"].replace(" ", "").strip()
    repo = os.environ.get("REPO", "antonkozon-cell/techmeme-audio")
    
    links_html = "<p><i>Zdroj: " + source_info + " | Hlas: " + voice_info + "</i></p>"
    links_html += "<h3>Hlasovanie o temach (Klikni pre ulozenie preferencie):</h3><ul>"
    for t in topics:
        like_url = "https://github.com/" + repo + "/issues/new?title=" + urllib.parse.quote("LIKE: " + t)
        dislike_url = "https://github.com/" + repo + "/issues/new?title=" + urllib.parse.quote("DISLIKE: " + t)
        links_html += "<li><b>" + t + "</b> &mdash; <a href='" + like_url + "'>[👍 Zaujimave]</a> &nbsp; <a href='" + dislike_url + "'>[👎 Menej]</a></li><br>"
    links_html += "</ul><hr><p style='white-space: pre-wrap;'>" + script + "</p>"

    msg = EmailMessage()
    msg["Subject"] = "🎧 Techmeme Rychly Prehlad (" + str(len(topics)) + " tem)"
    msg["From"] = user
    msg["To"] = user
    msg.set_content(script)
    msg.add_alternative("<html><body>" + links_html + "</body></html>", subtype="html")
    msg.add_attachment(open(mp3, "rb").read(), maintype="audio", subtype="mp3", filename="techmeme_prehlad.mp3")
    
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pwd)
        s.send_message(msg)

if __name__ == "__main__":
    likes, dislikes = get_prefs()
    news = fetch_techmeme_from_gmail()
    source_info = "Techmeme Newsletter (Gmail)"
    if not news:
        news = fetch_web_fallback()
        source_info = "Techmeme Web"
    script, topics = generate_script_and_topics(news, likes, dislikes)
    voice_info = make_audio(script)
    send_mail("briefing.mp3", script, topics, source_info, voice_info)
    print("Hotovo")
