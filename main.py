import os
import time
import asyncio
import smtplib
from datetime import datetime
from email.message import EmailMessage
import urllib.request
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
import edge_tts

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
        stories.append(f"HLAVNA TEMA #{idx}: {headline}\nSUVISIACE SPRAVY: {full_cluster_text}\n")
    return "\n---\n".join(stories)

# 2. Vygenerovanie audia (s opakovanim pri pretazeni 503 a zaloznym hlasom)
def generate_briefing_audio(raw_news, output_file="techmeme_brifing.mp3"):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"].strip())
    today_str = datetime.now().strftime("%d. %m. %Y")
    
    prompt = (
        f"Si profesionalny slovensky technologicky moderator. Dnes je {today_str}. "
        "Priprav plynuly, putavy audio brifing v slovencine na zaklade tychto sprav z Techmeme.com. "
        "Ignoruj investicie, akvizicie, kryptomeny a datove centra. "
        "Pis cisty suvisly text vhodny na priame precitanie nahlas, bez odrazok, nadpisov a markdownu.\n\n"
        f"SPRAVY:\n{raw_news}"
    )
    
    # POKUS A: Priame nativne audio cez Gemini (4 pokusy s cakanim)
    for attempt in range(1, 5):
        try:
            print(f"Pokus {attempt}/4: Generujem nativne audio priamo cez Gemini...")
            response = client.models.generate_content(
                model='gemini-3.8-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name="Puck"
                            )
                        )
                    )
                )
            )
            
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.mime_type.startswith("audio/"):
                    with open(output_file, "wb") as f:
                        f.write(part.inline_data.data)
                    print("Gemini uspesne vygenerovalo nativny audio subor!")
                    return "Audio vygenerovane priamo cez nativny hlas Gemini AI."
                    
        except Exception as e:
            print(f"Pokus {
