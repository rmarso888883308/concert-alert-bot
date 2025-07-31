import os
import time
import json
import requests
import re
from discord_webhook import DiscordWebhook

# === CONFIGURATION ===
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1400499247907868722/AWr8LD6xS7EtDRvv8O2NUH-kWqSaAm7ZIMEEfSx5ipSAUET3v4V1mE-C3HykPb22HjqY"
TWITTER_USERS = ["TicketmasterFR", "AEGPresentsFR"]
CHECK_INTERVAL = 300  # 5 minutes
STORAGE_FOLDER = "tweets_seen"

# Headers pour simuler un navigateur
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# Liste d'instances Nitter publiques (backup si une ne fonctionne pas)
NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.it", 
    "https://x.owo.si",
    "https://nitter.privacydev.net"
]

# === SETUP DU DOSSIER DE STOCKAGE ===
if not os.path.exists(STORAGE_FOLDER):
    os.makedirs(STORAGE_FOLDER)

# === SCRAPER LE DERNIER TWEET D'UN COMPTE (méthode alternative robuste) ===
def get_latest_tweet_multiple_sources(user):
    """
    Essaie plusieurs sources pour récupérer les tweets
    """
    
    # Méthode 1: RSS via plusieurs instances Nitter
    for instance in NITTER_INSTANCES:
        try:
            print(f"🔄 Tentative avec {instance}")
            nitter_url = f"{instance}/{user}/rss"
            response = requests.get(nitter_url, headers=HEADERS, timeout=15)
            
            if response.status_code == 200:
                content = response.text
                tweet_url, tweet_text = parse_rss_content(content, user)
                if tweet_url:
                    print(f"✅ Succès avec {instance}")
                    return tweet_url, tweet_text
                    
        except Exception as e:
            print(f"❌ Échec avec {instance}: {e}")
            continue
    
    # Méthode 2: Scraping direct de la page Nitter
    for instance in NITTER_INSTANCES:
        try:
            print(f"🔄 Scraping direct avec {instance}")
            page_url = f"{instance}/{user}"
            response = requests.get(page_url, headers=HEADERS, timeout=15)
            
            if response.status_code == 200:
                tweet_url, tweet_text = parse_nitter_page(response.text, user)
                if tweet_url:
                    print(f"✅ Scraping réussi avec {instance}")
                    return tweet_url, tweet_text
                    
        except Exception as e:
            print(f"❌ Scraping échoué avec {instance}: {e}")
            continue
    
    return None, None

def parse_rss_content(content, user):
    """Parse le contenu RSS pour extraire le tweet"""
    try:
        if '<item>' in content:
            item_start = content.find('<item>')
            item_end = content.find('</item>') + 7
            if item_start != -1 and item_end != -1:
                item = content[item_start:item_end]
                
                # Extraire le lien
                link_match = re.search(r'<link>(.*?)</link>', item)
                if link_match:
                    tweet_url = link_match.group(1)
                    
                    # Extraire le contenu
                    desc_match = re.search(r'<description><!\[CDATA\[(.*?)\]\]></description>', item, re.DOTALL)
                    if desc_match:
                        tweet_text = desc_match.group(1)
                        # Nettoyer le HTML
                        tweet_text = re.sub(r'<[^>]+>', '', tweet_text)
                        tweet_text = tweet_text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
                        tweet_text = tweet_text.strip()
                        
                        return tweet_url, tweet_text[:300] + "..." if len(tweet_text) > 300 else tweet_text
        
        return None, None
    except Exception as e:
        print(f"Erreur parsing RSS: {e}")
        return None, None

def parse_nitter_page(html_content, user):
    """Parse la page Nitter pour extraire le dernier tweet"""
    try:
        # Rechercher le premier tweet sur la page
        tweet_pattern = r'<div class="tweet-content media-body"[^>]*>(.*?)</div>'
        tweet_match = re.search(tweet_pattern, html_content, re.DOTALL)
        
        if tweet_match:
            tweet_text = tweet_match.group(1)
            # Nettoyer le HTML
            tweet_text = re.sub(r'<[^>]+>', '', tweet_text)
            tweet_text = tweet_text.strip()
            
            # Rechercher l'ID du tweet dans l'URL
            tweet_id_pattern = r'/status/(\d+)'
            tweet_id_match = re.search(tweet_id_pattern, html_content)
            
            if tweet_id_match:
                tweet_id = tweet_id_match.group(1)
                tweet_url = f"https://twitter.com/{user}/status/{tweet_id}"
                return tweet_url, tweet_text[:300] + "..." if len(tweet_text) > 300 else tweet_text
        
        return None, None
    except Exception as e:
        print(f"Erreur parsing page: {e}")
        return None, None

# === ALTERNATIVE : Utiliser l'API Twitter v2 (nécessite des clés API) ===
def get_latest_tweet_api(user, bearer_token=None):
    """
    Utilise l'API Twitter v2 - nécessite un Bearer Token
    À utiliser si vous avez accès à l'API Twitter
    """
    if not bearer_token:
        return None, None
        
    try:
        headers = {'Authorization': f'Bearer {bearer_token}'}
        url = f"https://api.twitter.com/2/users/by/username/{user}"
        
        # Récupérer l'ID utilisateur
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return None, None
            
        user_id = response.json()['data']['id']
        
        # Récupérer les tweets
        tweets_url = f"https://api.twitter.com/2/users/{user_id}/tweets"
        params = {'max_results': 5, 'tweet.fields': 'created_at,text'}
        
        response = requests.get(tweets_url, headers=headers, params=params)
        if response.status_code == 200:
            tweets = response.json()['data']
            if tweets:
                latest_tweet = tweets[0]
                tweet_url = f"https://twitter.com/{user}/status/{latest_tweet['id']}"
                return tweet_url, latest_tweet['text']
        
        return None, None
        
    except Exception as e:
        print(f"Erreur API Twitter pour {user}: {e}")
        return None, None

# === LIRE LE DERNIER TWEET ENVOYÉ POUR UN COMPTE ===
def read_last_tweet(user):
    path = os.path.join(STORAGE_FOLDER, f"{user}.txt")
    if os.path.exists(path):
        with open(path, "r", encoding='utf-8') as file:
            return file.read().strip()
    return ""

# === ENREGISTRER LE NOUVEAU TWEET POUR UN COMPTE ===
def save_last_tweet(user, tweet_url):
    path = os.path.join(STORAGE_FOLDER, f"{user}.txt")
    with open(path, "w", encoding='utf-8') as file:
        file.write(tweet_url)

# === ENVOYER LE TWEET SUR DISCORD ===
def send_to_discord(user, tweet_url, tweet_text):
    try:
        webhook = DiscordWebhook(
            url=DISCORD_WEBHOOK_URL,
            content=f"📣 **Nouveau tweet de @{user}** :\n{tweet_text}\n🔗 {tweet_url}"
        )
        response = webhook.execute()
        if response.status_code == 200:
            print(f"✅ Message Discord envoyé pour @{user}")
        else:
            print(f"❌ Erreur Discord pour @{user}: {response.status_code}")
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi Discord pour @{user}: {e}")

# === BOUCLE PRINCIPALE ===
def main():
    print("🟢 Surveillance de @TicketmasterFR et @AEGPresentsFR en cours...")
    print("🔄 Utilisation de sources multiples (Nitter instances)...")
    
    consecutive_failures = {}
    for user in TWITTER_USERS:
        consecutive_failures[user] = 0
    
    while True:
        for user in TWITTER_USERS:
            print(f"🔍 Vérification de @{user}...")
            
            # Utiliser la méthode multi-sources
            tweet_url, tweet_text = get_latest_tweet_multiple_sources(user)
            
            if tweet_url and tweet_text:
                consecutive_failures[user] = 0  # Reset compteur d'échecs
                
                if tweet_url != read_last_tweet(user):
                    print(f"✅ Nouveau tweet de @{user} détecté : {tweet_url}")
                    send_to_discord(user, tweet_url, tweet_text)
                    save_last_tweet(user, tweet_url)
                else:
                    print(f"⏳ Pas de nouveau tweet pour @{user}")
            else:
                consecutive_failures[user] += 1
                print(f"❌ Impossible de récupérer les tweets pour @{user} (échec #{consecutive_failures[user]})")
                
                # Si trop d'échecs consécutifs, envoyer une alerte
                if consecutive_failures[user] >= 6:  # 30 minutes d'échecs
                    print(f"🚨 ALERTE: {consecutive_failures[user]} échecs consécutifs pour @{user}")
                    try:
                        webhook = DiscordWebhook(
                            url=DISCORD_WEBHOOK_URL,
                            content=f"🚨 **ALERTE BOT** : Impossible de surveiller @{user} depuis {consecutive_failures[user] * 5} minutes"
                        )
                        webhook.execute()
                    except:
                        pass
                    consecutive_failures[user] = 0  # Reset pour éviter le spam
        
        print(f"😴 Attente de {CHECK_INTERVAL} secondes...")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()