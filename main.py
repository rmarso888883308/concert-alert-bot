import os
import time
import json
import requests
import re
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from discord_webhook import DiscordWebhook

# === CONFIGURATION ===
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1400499247907868722/AWr8LD6xS7EtDRvv8O2NUH-kWqSaAm7ZIMEEfSx5ipSAUET3v4V1mE-C3HykPb22HjqY"
TWITTER_USERS = ["TicketmasterFR", "AEGPresentsFR"]
CHECK_INTERVAL = 300  # 5 minutes
STORAGE_FOLDER = "tweets_seen"
PORT = int(os.environ.get('PORT', 10000))

# Headers pour simuler un navigateur
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# Liste d'instances Nitter publiques (plus robuste)
NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.it",
    "https://nitter.privacydev.net",
    "https://nitter.weiler.rocks",
    "https://nitter.poast.org",
    "https://nitter.x86-64-unknown-linux-gnu.zip",
]


# === SETUP DU DOSSIER DE STOCKAGE ===
if not os.path.exists(STORAGE_FOLDER):
    os.makedirs(STORAGE_FOLDER)

# === SERVEUR HTTP MINIMAL POUR RENDER ===
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            # Statistiques du bot
            stats = {
                "status": "running",
                "monitored_accounts": TWITTER_USERS,
                "check_interval": CHECK_INTERVAL,
                "last_check": getattr(self.server, 'last_check', 'Never')
            }
            self.wfile.write(json.dumps(stats).encode())
        else:
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            html = f"""
            <html>
            <head><title>Concert Alert Bot</title></head>
            <body>
                <h1>🎵 Concert Alert Bot</h1>
                <p>Bot de surveillance actif pour :</p>
                <ul>
                    {''.join(f'<li>@{user}</li>' for user in TWITTER_USERS)}
                </ul>
                <p>Vérification toutes les {CHECK_INTERVAL//60} minutes</p>
                <p><a href="/health">Health Check</a></p>
            </body>
            </html>
            """
            self.wfile.write(html.encode())
    
    def log_message(self, format, *args):
        # Supprimer les logs HTTP pour réduire le bruit
        return

def start_web_server():
    """Démarre le serveur web en arrière-plan"""
    server = HTTPServer(('0.0.0.0', PORT), HealthCheckHandler)
    server.last_check = "Starting..."
    print(f"🌐 Serveur web démarré sur le port {PORT}")
    server.serve_forever()

# === FONCTIONS DE SCRAPING (AMÉLIORÉES) ===
def get_latest_tweet_multiple_sources(user):
    """Essaie plusieurs sources pour récupérer les tweets"""
    
    # Méthode 1: RSS via plusieurs instances Nitter
    for instance in NITTER_INSTANCES:
        try:
            print(f"🔄 Tentative avec {instance}")
            nitter_url = f"{instance}/{user}/rss"
            response = requests.get(nitter_url, headers=HEADERS, timeout=10)
            response.raise_for_status() # Lève une exception pour les codes d'erreur HTTP
            
            content = response.text
            tweet_url, tweet_text = parse_rss_content(content, user)
            if tweet_url:
                print(f"✅ Succès avec {instance}")
                return tweet_url, tweet_text
                    
        except requests.exceptions.RequestException as e:
            print(f"❌ Échec avec {instance}: {e}")
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
                    tweet_url = link_match.group(1).replace("nitter.net", "twitter.com") # Remplacer par twitter.com
                    
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


# === FONCTIONS DE STOCKAGE ET DISCORD ===
def read_last_tweet(user):
    path = os.path.join(STORAGE_FOLDER, f"{user}.txt")
    if os.path.exists(path):
        with open(path, "r", encoding='utf-8') as file:
            return file.read().strip()
    return ""

def save_last_tweet(user, tweet_url):
    path = os.path.join(STORAGE_FOLDER, f"{user}.txt")
    with open(path, "w", encoding='utf-8') as file:
        file.write(tweet_url)

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

# === BOUCLE PRINCIPALE DE SURVEILLANCE ===
def monitor_twitter():
    """Fonction principale de surveillance Twitter"""
    print("🟢 Surveillance de @TicketmasterFR et @AEGPresentsFR en cours...")
    print("🔄 Utilisation de sources multiples (Nitter instances)...")
    
    consecutive_failures = {user: 0 for user in TWITTER_USERS}
    
    while True:
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n🕐 {current_time} - Début du cycle de vérification")
        
        for user in TWITTER_USERS:
            print(f"🔍 Vérification de @{user}...")
            
            tweet_url, tweet_text = get_latest_tweet_multiple_sources(user)
            
            if tweet_url and tweet_text:
                consecutive_failures[user] = 0
                
                if tweet_url != read_last_tweet(user):
                    print(f"✅ Nouveau tweet de @{user} détecté : {tweet_url}")
                    send_to_discord(user, tweet_url, tweet_text)
                    save_last_tweet(user, tweet_url)
                else:
                    print(f"⏳ Pas de nouveau tweet pour @{user}")
            else:
                consecutive_failures[user] += 1
                print(f"❌ Impossible de récupérer les tweets pour @{user} (échec #{consecutive_failures[user]})")
                
                if consecutive_failures[user] >= 6:
                    print(f"🚨 ALERTE: {consecutive_failures[user]} échecs consécutifs pour @{user}")
                    try:
                        webhook = DiscordWebhook(
                            url=DISCORD_WEBHOOK_URL,
                            content=f"🚨 **ALERTE BOT** : Impossible de surveiller @{user} depuis {consecutive_failures[user] * 5} minutes"
                        )
                        webhook.execute()
                    except:
                        pass
                    # Ne réinitialise pas le compteur pour que l'alerte ne soit pas envoyée en boucle
        
        print(f"😴 Attente de {CHECK_INTERVAL} secondes...")
        time.sleep(CHECK_INTERVAL)

# === POINT D'ENTRÉE PRINCIPAL ===
if __name__ == "__main__":
    # Démarrer le serveur web en arrière-plan
    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()
    
    # Attendre un peu que le serveur démarre
    time.sleep(2)
    
    # Démarrer la surveillance Twitter
    monitor_twitter()
