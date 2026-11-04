import argparse
import pandas as pd
import os
from src.social_scraping.tiktok_scraper import TikTokScraper
from src.social_scraping.facebook_scraper import FacebookScraper

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Orquestador de Scraping para Redes Sociales - PEU-CD INEI")
    parser.add_argument("--red", type=str, required=True, choices=["tiktok", "facebook"], help="Red social a raspar")
    parser.add_argument("--accion", type=str, default="raspar", choices=["login_fb", "raspar"], help="Acción a realizar")
    args = parser.parse_args()

    # Aseguramos que el directorio Gold (processed) exista
    os.makedirs("data/processed", exist_ok=True)

    if args.red == "tiktok":
        scraper = TikTokScraper(headless=False) # Headless False para monitoreo/CAPTCHAs
        # Busca un hashtag relevante para el mercado inmobiliario del INEI
        datos = scraper.raspar_hashtag("departamentoslima", max_scrolls=3)
        if datos:
            df = pd.DataFrame(datos)
            df.to_csv("data/processed/tiktok_departamentoslima.csv", index=False, encoding="utf-8-sig")
            print("[✓] Dataset de TikTok guardado en data/processed/tiktok_departamentoslima.csv")

    elif args.red == "facebook":
        fb = FacebookScraper()
        if args.accion == "login_fb":
            fb.iniciar_sesion_manual()
        else:
            datos = fb.raspar_pagina_publica("https://www.facebook.com/INEI.Oficial")
            if datos:
                df = pd.DataFrame(datos)
                df.to_csv("data/processed/facebook_inei_posts.csv", index=False, encoding="utf-8-sig")
                print("[✓] Dataset de Facebook guardado en data/processed/facebook_inei_posts.csv")