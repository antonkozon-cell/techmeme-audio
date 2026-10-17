import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
import urllib.request
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

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
    top_section = soup.find('div', id='topcol1') or soup
        
    stories = []
    clusters = top_section.find_all('div', class_='clus')
    for idx, clus in enumerate(clusters[:25], 1):
        main_link = clus.find('a', class_='ourh')
        if not main_link:
            continue
        headline = main_link.get_text(" ", strip=True)
        full_cluster_text = clus.get_text(" ", strip=True)
        stories.append(f"HLAVNÁ TÉMA #{idx}: {headline}\nSÚVISIACE SPRÁVY: {full_cluster_text}\n")
    return "\n---\n".join(stories)

# 2. Vygenerovanie audia priamo cez Gemini API
def generate_gemini_audio(raw_news, output_file="techmeme_brifing.mp3"):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"].strip())
    today_str = datetime.now().strftime("%d. %m. %Y")
    
    prompt = f"""
    Si profesionálny slovenský technologický moderátor. Dnes je {today_str}.
    Priprav plynulý, pútavý audio brífing v slovenčine na základe týchto správ z Techmeme.com. 
    Ignoruj investície, akvizície a dátové centrá. Píš čistý súvislý text vhodný na priame prečítanie nahlas, bez odrážok a markdownu.
    
    SPRÁVY:
    {raw_news}
    """
    
    print("Generujem natívne audio priamo cez Gemini...")
    response = client.models.generate_content(
        model='gemini-3.8-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Puck"  # Na výber sú napr. Puck, Charon, Kore, Fenrir, Aoede
                    )
                )
            )
        )
    )
    
    audio_bytes = None
    for part in response.candidates[0].content.parts:
        if part.inline_data and part.inline_data.mime_type.startswith("audio/"):
            audio_bytes = part.inline_data.data
            break
            
    if audio_bytes:
        with open(output_file, "wb") as f:
            f.write(audio_bytes)
        print("Gemini úspešne vygenerovalo audio súbor!")
        return "Priamy audio brífing vygenerovaný pomocou Gemini AI."
    else:
        raise RuntimeError("Gemini nevrátilo audio dáta.")

# 3. Odoslanie hotoveho MP3 suboru na e-mail
def send_email(mp3_file, script_text):
    sender = os.environ["EMAIL_ADDRESS"].strip()
    password = os.environ["EMAIL_APP_PASSWORD"].replace(" ", "").strip()
    today_str = datetime.now().strftime("%d.%m.%Y")
    
    msg = EmailMessage()
    msg["Subject"] = f"🎧 Ranný Techmeme Audio Brífing (Gemini Audio) ({today_str})"
    msg["From"] = sender
    msg["To"] = sender
    msg.set_content(f"Ahoj,\n\nv prílohe nájdeš dnešný audio prehľad vygenerovaný priamo cez natívne Gemini audio.\n\n{script_text}")
    
    with open(mp3_file, "rb") as f:
        msg.add_attachment(f.read(), maintype="audio", subtype="mp3", filename=f"techmeme_{today_str}.mp3")
        
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)

if __name__ == "__main__":
    print("Sťahujem správy z Techmeme...")
    news = fetch_techmeme_homepage()
    mp3_filename = "techmeme_brifing.mp3"
    info_text = generate_gemini_audio(news, mp3_filename)
    print("Odosielam MP3 na e-mail...")
    send_email(mp3_filename, info_text)
    print("Hotovo!")
