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
                
                # Exécute la fonction bloquante SeleniumBase dans un processus séparé isolé !
                # Ça évite tous les deadlocks liés à asyncio / Xvfb
                if ally_code.startswith("http"):
                    target_url = ally_code
                    clean_code = "custom_url"
                else:
                    target_url = f"https://swgoh.gg/p/{ally_code}/gac-history/"
                    clean_code = ally_code
                    
                import sys
                process = await asyncio.create_subprocess_exec(
                    sys.executable, "scripts/sb_worker.py", target_url, clean_code,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                try:
                    # On laisse 60 secondes maximum au navigateur pour faire son travail
                    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60.0)
                    
                    output_log = stdout.decode().strip()
                    error_log = stderr.decode().strip()
                    
                    if process.returncode == 0:
                        logger.info(f"✅ Subprocess a réussi :\n{output_log}")
                        if interaction:
                            try:
                                await interaction.followup.send(f"🏆 Fichier HTML sauvegardé avec succès pour {clean_code} !")
                            except:
                                pass
                    else:
                        logger.error(f"❌ Échec du Subprocess (Code {process.returncode}):\n{error_log}\n{output_log}")
                        if interaction:
                            try:
                                await interaction.followup.send(f"❌ Le scraping a échoué (regarde la console).")
                            except:
                                pass
                except asyncio.TimeoutError:
                    process.kill()
                    logger.error(f"⏰ Timeout: Le processus de scraping a été tué car il a mis plus de 60 secondes.")
                    if interaction:
                        try:
                            await interaction.followup.send(f"❌ Timeout : Cloudflare a fait planter le navigateur.")
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
