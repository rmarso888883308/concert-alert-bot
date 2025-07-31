import os
import time
import json
import subprocess
from discord_webhook import DiscordWebhook

# === CONFIGURATION ===
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1400499247907868722/AWr8LD6xS7EtDRvv8O2NUH-kWqSaAm7ZIMEEfSx5ipSAUET3v4V1mE-C3HykPb22HjqY"
TWITTER_USERS = ["TicketmasterFR", "AEGPresentsFR"]
CHECK_INTERVAL = 300  # 5 minutes
STORAGE_FOLDER = "tweets_seen"

# === SETUP DU DOSSIER DE STOCKAGE ===
if not os.path.exists(STORAGE_FOLDER):
    os.makedirs(STORAGE_FOLDER)

# === SCRAPER LE DERNIER TWEET D'UN COMPTE ===
def get_latest_tweet(user):
    command = f'snscrape --jsonl --max-results 1 twitter-user "{user}"'
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE)
    try:
        tweet = json.loads(result.stdout.decode().splitlines()[0])
        return tweet['url'], tweet['content']
    except Exception:
        return None, None

# === LIRE LE DERNIER TWEET ENVOYÉ POUR UN COMPTE ===
def read_last_tweet(user):
    path = os.path.join(STORAGE_FOLDER, f"{user}.txt")
    if os.path.exists(path):
        with open(path, "r") as file:
            return file.read().strip()
    return ""

# === ENREGISTRER LE NOUVEAU TWEET POUR UN COMPTE ===
def save_last_tweet(user, tweet_url):
    path = os.path.join(STORAGE_FOLDER, f"{user}.txt")
    with open(path, "w") as file:
        file.write(tweet_url)

# === ENVOYER LE TWEET SUR DISCORD ===
def send_to_discord(user, tweet_url, tweet_text):
    webhook = DiscordWebhook(
        url=DISCORD_WEBHOOK_URL,
        content=f"📣 **Nouveau tweet de @{user}** :\n{tweet_text}\n🔗 {tweet_url}"
    )
    webhook.execute()

# === BOUCLE PRINCIPALE ===
def main():
    print("🟢 Surveillance de @TicketmasterFR et @AEGPresentsFR en cours...")
    while True:
        for user in TWITTER_USERS:
            tweet_url, tweet_text = get_latest_tweet(user)
            if tweet_url and tweet_url != read_last_tweet(user):
                print(f"✅ Nouveau tweet de @{user} détecté : {tweet_url}")
                send_to_discord(user, tweet_url, tweet_text)
                save_last_tweet(user, tweet_url)
            else:
                print(f"⏳ Pas de nouveau tweet pour @{user} »")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
