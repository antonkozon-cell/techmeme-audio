import os
import re
import asyncio
import smtplib
from datetime import datetime
from email.message import EmailMessage
import urllib.request
from bs4 import BeautifulSoup
from google import genai
import edge_tts
from gtts import gTTS

# 1. Stiahnutie TOP sprav priamo z homepage Techmeme.com
def fetch_techmeme_homepage():
    url = "https://www.techmeme.com/"
    req = urllib.request.Request(
        url, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    )
    with urllib.request.urlopen(req) as response:
        html = response.read().decode('utf-8', errors='ignore')
    
    soup = BeautifulSoup(html, 'html.parser')
    
    top_section = soup.find('div', id='topcol1')
    if not top_section:
        top_section = soup
        
    stories = []
    clusters = top_section.find_all('div', class_='clus')
    
    for idx, clus in enumerate(clusters[:25], 1):
        main_link = clus.find('a', class_='ourh')
        if not main_link:
            continue
            
        headline = main_link.get_text(" ", strip=True)
        full_cluster_text = clus.get_text(" ", strip=True)
        stories.append(f"HLAVNÁ TÉMA #{idx}: {headline}\nKONTEXT A SÚVISIACE SPRÁVY: {full_cluster_text}\n")
        
    if not stories:
        for idx, link in enumerate(soup.find_all('a', class_='ourh')[:25], 1):
            parent_text = link.parent.parent.get_text(" ", strip=True) if link.parent else link.get_text(" ", strip=True)
            stories.append(f"HLAVNÁ TÉMA #{idx}: {parent_text}")
            
    return "\n---\n".join(stories)

# 2. Vygenerovanie 10-minutoveho slovenskeho scenara cez Gemini
def generate_slovak_script(raw_news):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"].strip())
    today_str = datetime.now().strftime("%d. %m. %Y")
    
    prompt = f"""
    Si profesionálny slovenský technologický moderátor. Dnes je {today_str}.
    Nižšie máš surový výpis hlavných správ (Headlines) priamo z titulnej stránky Techmeme.com, zoradených podľa dôležitosti.
    
    TVOJA ÚLOHA:
    1. PRÍSNE VYNECHAJ všetky správy, ktorých hlavnou témou sú:
       - fúzie a akvizície (mergers & acquisitions, odkúpenia firiem),
       - kryptomeny, blockchain a Web3,
       - výstavba, napájanie alebo financovanie dátových centier (datacenters),
       - investičné kolá startupov a valuácie (funding deals, Series A/B/C, seed kolá).
       Tiež ignoruj prípadné sponzorované príspevky (Sponsor Post).
    2. Zvyšné hlavné správy (AI modely, hardvér, kyberbezpečnosť, čipy, regulácie, súdne spory, veda, softvér, hry) spracuj do plynulého, pútavého rozprávačského audio scenára v slovenčine. Začni tými najdôležitejšími správami z vrchu stránky.
    3. DĹŽKA TEXTU: Scenár musí mať približne 1 250 až 1 400 slov (okolo 8 500 až 9 500 znakov), aby jeho prečítanie trvalo približne 10 minút. Venuj sa každej vybranej téme do hĺbky, vysvetli kontext, mená firiem a technické detaily z priloženého kontextu.
    4. FORMÁT PRE TTS ČÍTANIE: Píš výlučne čistý súvislý text v odsekoch. Nepoužívaj ŽIADNE odrážky, hviezdičky, markdown nadpisy (#), URL odkazy ani zátvorky. Čísla, sumy a skratky píš tak, aby ich slovenský hlas prečítal prirodzene.
    
    HLAVNÉ SPRÁVY Z HOMEPAGE TECHMEME:
    {raw_news}
    """
    
    candidate_models = ["gemini-3.8-flash", "gemini-flash-latest", "gemini-3.0-flash"]
    last_err = None
    for model_name in candidate_models:
        try:
            print(f"Skúšam model: {model_name}...")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            return response.text
        except Exception as e:
            print(f"Model {model_name} nefungoval ({e}), skúšam ďalší...")
            last_err = e
    raise last_err

# Pomocna funkcia na rozdelenie dlheho textu na mensie odseky (max ~2200 znakov)
def split_text_into_chunks(text, max_chars=2200):
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks = []
    current = ""
    for p in paragraphs:
        if len(current) + len(p) + 2 <= max_chars:
            current = f"{current}\n\n{p}" if current else p
        else:
            if current:
                chunks.append(current)
            # Ak je jeden odsek sam o sebe prilis dlhy, rozdelime ho po vetach
            if len(p) > max_chars:
                sentences = re.split(r'(?<=[.!?])\s+', p)
                sub = ""
                for s in sentences:
                    if len(sub) + len(s) + 1 <= max_chars:
                        sub = f"{sub} {s}" if sub else s
                    else:
                        if sub:
                            chunks.append(sub)
                        sub = s
                current = sub
            else:
                current = p
    if current:
        chunks.append(current)
    return chunks

# 3. Prevod textu na MP3 (po castiach cez Edge-TTS + zaloha cez Google TTS)
async def text_to_mp3(text, output_file="techmeme_brifing.mp3"):
    clean_text = text.replace("*", "").replace("#", "").strip()
    chunks = split_text_into_chunks(clean_text, max_chars=2200)
    voice = "sk-SK-LukasNeural"
    
    try:
        print(f"Skúšam Edge-TTS po častiach ({len(chunks)} častí)...")
        with open(output_file, "wb") as out_f:
            for i, chunk in enumerate(chunks, 1):
                print(f"  Spracúvam časť {i}/{len(chunks)} ({len(chunk)} znakov)...")
                communicate = edge_tts.Communicate(chunk, voice)
                got_audio = False
                async for message in communicate.stream():
                    if message["type"] == "audio":
                        out_f.write(message["data"])
                        got_audio = True
                if not got_audio:
                    raise RuntimeError("Edge-TTS nevrátil zvuk pre túto časť.")
        print("Edge-TTS úspešne vygeneroval MP3!")
    except Exception as e:
        print(f"Edge-TTS zlyhal ({e}). Prepínam na záložný slovenský hlas Google TTS (gTTS)...")
        tts = gTTS(text=clean_text, lang="sk", slow=False)
        tts.save(output_file)
        print("Google TTS (gTTS) úspešne vygeneroval MP3!")

# 4. Odoslanie hotoveho MP3 suboru na e-mail
def send_email(mp3_file, script_text):
    sender = os.environ["EMAIL_ADDRESS"].strip()
    password = os.environ["EMAIL_APP_PASSWORD"].replace(" ", "").strip()
    today_str = datetime.now().strftime("%d.%m.%Y")
    
    msg = EmailMessage()
    msg["Subject"] = f"🎧 Ranný Techmeme Audio Brífing ({today_str})"
    msg["From"] = sender
    msg["To"] = sender
    msg.set_content(f"Ahoj,\n\nv prílohe nájdeš dnešný 10-minútový audio prehľad hlavných správ z homepage Techmeme.\n\n---\nPREPIS SCENÁRA:\n\n{script_text}")
    
    with open(mp3_file, "rb") as f:
        file_data = f.read()
        msg.add_attachment(
            file_data, 
            maintype="audio", 
            subtype="mpeg", 
            filename=f"techmeme_{today_str}.mp3"
        )
        
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)

if __name__ == "__main__":
    print("Sťahujem hlavné správy z homepage Techmeme.com...")
    news = fetch_techmeme_homepage()
    print(f"Stiahnuté dáta ({len(news)} znakov). Generujem slovenský scenár cez Gemini...")
    script = generate_slovak_script(news)
    print(f"Scenár vygenerovaný ({len(script)} znakov). Generujem MP3 audio...")
    mp3_filename = "techmeme_brifing.mp3"
    asyncio.run(text_to_mp3(script, mp3_filename))
    print("Odosielam MP3 na e-mail...")
    send_email(mp3_filename, script)
    print("Hotovo! E-mail s MP3 bol úspešne odoslaný.")
