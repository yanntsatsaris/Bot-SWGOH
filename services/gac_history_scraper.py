import asyncio
import logging
import concurrent.futures
from bs4 import BeautifulSoup
from seleniumbase import SB

logger = logging.getLogger("gac_scraper")

class GACHistoryScraper:
    def __init__(self, db_manager):
        self.db = db_manager
        self.queue = asyncio.Queue()
        self.is_running = False
        self._worker_task = None
        # On utilise un ThreadPool de 1 pour être sûr qu'un seul Chrome tourne à la fois
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    async def start(self):
        """Démarre le worker en arrière-plan."""
        if not self.is_running:
            self.is_running = True
            self._worker_task = asyncio.create_task(self._worker_loop())
            logger.info("🟢 Scraper GAC History démarré.")

    async def stop(self):
        """Arrête proprement le scraper."""
        self.is_running = False
        if self._worker_task:
            self._worker_task.cancel()
        self.executor.shutdown(wait=True)
        logger.info("🔴 Scraper GAC History arrêté.")

    async def queue_scrape(self, ally_code: str, interaction=None):
        """Ajoute un joueur à la file d'attente pour être scrapé."""
        await self.queue.put((ally_code, interaction))
        logger.info(f"Ajout de {ally_code} à la file d'attente de scraping. (Taille: {self.queue.qsize()})")

    async def _worker_loop(self):
        """Boucle principale qui dépile et traite les requêtes."""
        while self.is_running:
            try:
                # Attend qu'un profil soit ajouté à la file
                ally_code, interaction = await self.queue.get()
                
                logger.info(f"⚙️ Démarrage du scraping pour {ally_code}...")
                
                if interaction:
                    try:
                        await interaction.followup.send(f"🔍 Début de l'extraction de l'historique pour {ally_code} (Patientez ~20s)...")
                    except:
                        pass
                
                # Exécute la fonction bloquante SeleniumBase dans le ThreadPool
                # pour ne pas freezer le bot Discord
                result_html = await asyncio.get_event_loop().run_in_executor(
                    self.executor,
                    self._run_selenium_sync,
                    ally_code
                )
                
                if result_html:
                    logger.info(f"✅ Code HTML récupéré pour {ally_code}. Lancement du parsing...")
                    parsed_data = self._parse_html(result_html, ally_code)
                    
                    # Plus tard: insérer parsed_data dans la DB
                    
                    if interaction:
                        try:
                            await interaction.followup.send(f"🏆 Historique de {ally_code} extrait et analysé avec succès ! (Code HTML: {len(result_html)} octets)")
                        except:
                            pass
                else:
                    logger.error(f"❌ Échec de la récupération HTML pour {ally_code}.")
                    if interaction:
                        try:
                            await interaction.followup.send(f"❌ Impossible d'extraire l'historique de {ally_code} (Blocage Cloudflare ou Timeout).")
                        except:
                            pass
                
                self.queue.task_done()
                
                # Petite pause entre chaque profil pour ne pas affoler Cloudflare
                await asyncio.sleep(5)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erreur critique dans le worker GAC Scraper : {e}")
                await asyncio.sleep(5)

    def _run_selenium_sync(self, ally_code_or_url: str) -> str:
        """
        Fonction bloquante exécutée dans un thread séparé.
        Gère SeleniumBase avec le faux écran (Xvfb).
        """
        if ally_code_or_url.startswith("http"):
            target_url = ally_code_or_url
            ally_code = "custom_url"
        else:
            target_url = f"https://swgoh.gg/p/{ally_code_or_url}/gac-history/"
            ally_code = ally_code_or_url
        
        try:
            # uc=True pour tromper Cloudflare, xvfb=True pour créer l'écran virtuel Linux, headless=False obligatoire pour UC
            with SB(uc=True, xvfb=True, headless=False) as sb:
                sb.uc_open_with_reconnect(target_url, reconnect_time=4)
                
                # Contournement Turnstile (l'IA clique sur la case)
                try:
                    sb.uc_gui_click_captcha()
                except Exception as e:
                    logger.warning(f"Pas de captcha ou clic raté pour {ally_code} : {e}")
                
                # On attend de voir si la page charge vraiment
                sb.sleep(8)
                
                page_source = sb.get_page_source()
                
                # Sauvegarde du HTML brut pour analyse !
                safe_name = ally_code.replace("/", "_").replace(":", "")
                with open(f"gac_history_{safe_name}.html", "w", encoding="utf-8") as f:
                    f.write(page_source)
                
                return page_source
        except Exception as e:
            logger.error(f"SeleniumBase a crashé pour {ally_code} : {e}")
            return None

    def _parse_html(self, html: str, ally_code: str) -> dict:
        """
        Analyse l'HTML brut de swgoh.gg pour extraire les rounds et les équipes.
        TODO: A implémenter complètement en regardant le code source d'un profil.
        """
        soup = BeautifulSoup(html, "html.parser")
        
        # Pour le moment on sauvegarde l'HTML dans un fichier pour qu'on puisse
        # l'étudier et écrire le parseur correct
        with open(f"gac_history_{ally_code}.html", "w", encoding="utf-8") as f:
            f.write(soup.prettify())
            
        logger.info(f"Fichier gac_history_{ally_code}.html sauvegardé pour analyse.")
        
        return {}
