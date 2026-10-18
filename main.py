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
        stories.append(f"HLAVNÁ TÉMA #{idx}: {headline}\nSÚVISIACE SPRÁVY: {full_cluster_text}\n")
    return "\n---\n".join(stories)

# 2. Vygenerovanie audia (s opakovaním pri preťažení 503 a záložným hlasom)
def generate_briefing_audio(raw_news, output_file="techmeme_brifing.mp3"):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"].strip())
    today_str = datetime.now().strftime("%d. %m. %Y")
    
    prompt = f"""
    Si profesionálny slovenský technologický moderátor. Dnes je {today_str}.
    Priprav plynulý, pútavý audio brífing v slovenčine na základe týchto správ z Techmeme.com. 
    Ignoruj investície, akvizície, kryptomeny a dátové centrá. Píš čistý súvislý text vhodný na priame prečítanie nahlas, bez odrážok, nadpis
