import os, time, json, asyncio, smtplib, urllib.request, urllib.parse
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

def fetch_all_news():
    req = urllib.request.Request("https://www.techmeme.com/", headers={'User-Agent': 'Mozilla/5.0'})
    html = urllib.request.urlopen(req).read().decode('utf-8', errors='ignore')
    soup = BeautifulSoup(html, 'html.parser')
    stories = []
    for c in soup.find_all('div', class_='clus'):
        link = c.find('a', class_='ourh')
        if link:
            stories.append(link.get_text(" ", strip=True) + " | " + c.get_text(" ", strip=True))
    return "\n\n".join(stories[:65])

def generate_script_and_topics(news, likes, dislikes):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"].strip())
    pref_text = ""
    if likes:
        pref_text += "Pouzivatela v minulosti zaujali tieto temy (uprednostni podobny typ sprav): " + ", ".join(likes) + ".\n"
    if dislikes:
        pref_text += "Tieto temy pouzivatela nudili (vynechaj ich alebo im venuj minimum casu): " + ", ".join(dislikes) + ".\n"

    prompt = (
        "Si slovensky technologicky moderator. Sprav dlhy, podrobny a putavy rozhlasovy prehlad v slovencine (aspon 1200 slov) zo vsetkych zaujimavych sprav nizsie. "
        "Striktne vynechaj mergers, akvizicie, kryptomeny, datove centra a funding deals. "
        + pref_text +
        "Rozdel prehlad na logicke odseky, vysvetli kontext a rozober spravy do hlbky. Pis cisty suvisly text vhodny na priame citanie nahlas, bez odrazok a bez hviezdiciek.\n"
        "Na uplny koniec tvojej odpovede pridaj presny oddelovac ===TEMY=== a za nim vypis 8 az 12 hlavnych tem z dnesneho prehladu, kazdu na novy riadok ako kratky nazov (max 6 slov, bez cislovania a odrazok).\n\n"
        "SPRAVY:\n" + news
    )
    res = client.models.generate_content(model='gemini-3.8-flash', contents=prompt)
    parts = res.text.split("===TEMY===")
    script = parts[0].strip()
    topics = [line.strip("- *1234567890.") for line in parts[1].strip().split("\n") if line.strip()] if len(parts) > 1 else []
    return script, topics

def split_text(text, max_len=1800):
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

async def edge_chunk_save(chunks, mp3):
    with open(mp3, "wb") as out:
        for idx, c in enumerate(chunks):
            print("Edge-TTS spracovava cast:", idx + 1, "z", len(chunks))
            comm = edge_tts.Communicate(c, "sk-SK-LukasNeural")
            async for msg in comm.stream():
                if msg["type"] == "audio":
                    out.write(msg["data"])

def make_audio(script, mp3="briefing.mp3"):
    clean_script = script.replace("*", "").replace("#", "")
    chunks = split_text(clean_script, 1800)
    print("Text rozdeleny na", len(chunks), "casti pre plynule generovanie audia.")

    # Pokus 1: Edge-TTS po menších častiach (zvládne akúkoľvek dĺžku)
    try:
        print("Generujem dlhe audio cez Edge-TTS po castiach...")
        asyncio.run(edge_chunk_save(chunks, mp3))
        if os.path.exists(mp3) and os.path.getsize(mp3) > 1000:
            print("Edge-TTS uspesne vygenerovalo dlhe audio!")
            return
    except Exception as e:
        print("Edge-TTS zlyhalo:", e)

    # Pokus 2: Nepriestrelná záloha cez gTTS, ak mal Edge-TTS výpadok na GitHub IP
    print("Prepinam na zalozne gTTS pre dlhy text...")
    gTTS(text=clean_script, lang='sk').save(mp3)
    print("Audio uspesne vygenerovane cez gTTS!")

def send_mail(mp3, script, topics):
    user = os.environ["EMAIL_ADDRESS"].strip()
    pwd = os.environ["EMAIL_APP_PASSWORD"].replace(" ", "").strip()
    repo = os.environ.get("REPO", "antonkozon-cell/techmeme-audio")
    
    links_html = "<h3>Ako sa ti pacili dnesne temy? (Klikni pre ulozenie preferencie)</h3><ul>"
    for t in topics:
        like_url = "https://github.com/" + repo + "/issues/new?title=" + urllib.parse.quote("LIKE: " + t) + "&body=" + urllib.parse.quote("Tato tema ma zaujala, zaraduj viac podobnych sprav.")
        dislike_url = "https://github.com/" + repo + "/issues/new?title=" + urllib.parse.quote("DISLIKE: " + t) + "&body=" + urllib.parse.quote("Tato tema ma nezaujala, v buducnosti ju obmedz.")
        links_html += "<li><b>" + t + "</b> &mdash; <a href='" + like_url + "'>[👍 Zaujimave]</a> &nbsp; <a href='" + dislike_url + "'>[👎 Menej takehoto]</a></li><br>"
    links_html += "</ul><hr><p style='white-space: pre-wrap;'>" + script + "</p>"

    msg = EmailMessage()
    msg["Subject"] = "🎧 Dlhy Techmeme Audio Brifing + Dotaznik"
    msg["From"] = user
    msg["To"] = user
    msg.set_content("Pre zobrazenie hlasovacich odkazov si zapni HTML zobrazenie spravy.\n\n" + script)
    msg.add_alternative("<html><body>" + links_html + "</body></html>", subtype="html")
    msg.add_attachment(open(mp3, "rb").read(), maintype="audio", subtype="mp3", filename="techmeme_dlhy.mp3")
    
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pwd)
        s.send_message(msg)

if __name__ == "__main__":
    likes, dislikes = get_prefs()
    print("Nacitane preferencie - Likes:", len(likes), "Dislikes:", len(dislikes))
    news = fetch_all_news()
    script, topics = generate_script_and_topics(news, likes, dislikes)
    make_audio(script)
    send_mail("briefing.mp3", script, topics)
    print("Hotovo")
